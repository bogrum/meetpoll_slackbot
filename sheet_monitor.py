"""
Sheet monitor for RSG Türkiye committee tracking.

Monitors the shared Google Sheet (3 tabs: Grafik Tasarım, Sosyal Medya, Sponsorluk)
and sends targeted DMs to team leaders and a weekly digest to the admin.

Triggered by scheduled jobs in bot.py — never called by users directly.

Required env vars:
  COMMITTEE_SHEET_ID   — the shared spreadsheet ID
  ADMIN_USER_ID        — Emre's Slack user ID (for Friday digest)
"""

import os
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional

import database as db
from sheets import _get_service

logger = logging.getLogger(__name__)

COMMITTEE_SHEET_ID = os.getenv("COMMITTEE_SHEET_ID", "")
ADMIN_USER_ID = os.getenv("ADMIN_USER_ID", "")
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{COMMITTEE_SHEET_ID}"

# Sheet tab name → committee name in DB (must match committee_channels table)
MONITORED_TABS = {
    "Grafik Tasarım": "Graphic Design",
    "Sosyal Medya": "Social Media",
    "Sponsorluk": "Sponsorship",
}

# Expected column order after header row
COL_ETKINLIK    = 0
COL_TARIH       = 1
COL_DEADLINE    = 2
COL_TAMAMLANDI  = 3


# ---------------------------------------------------------------------------
# Sheet reading
# ---------------------------------------------------------------------------

def _fetch_tab(tab_name: str) -> list[dict]:
    """Read all non-empty data rows from a specific tab of the committee sheet."""
    if not COMMITTEE_SHEET_ID:
        logger.error("COMMITTEE_SHEET_ID not set — sheet monitor is disabled")
        return []

    try:
        service = _get_service()
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=COMMITTEE_SHEET_ID, range=f"'{tab_name}'")
            .execute()
        )
        raw_rows = result.get("values", [])
        if len(raw_rows) < 2:
            return []

        rows = []
        for raw in raw_rows[1:]:
            padded = raw + [""] * (4 - len(raw))
            row = {
                "etkinlik_adi": padded[COL_ETKINLIK].strip(),
                "tarih":        padded[COL_TARIH].strip(),
                "deadline":     padded[COL_DEADLINE].strip(),
                "tamamlandi":   padded[COL_TAMAMLANDI].strip().upper(),
            }
            if row["etkinlik_adi"]:  # skip blank rows
                rows.append(row)

        return rows

    except Exception as e:
        logger.error(f"Error reading tab '{tab_name}': {e}")
        return []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_hash(row: dict) -> str:
    """Stable hash identifying a row by its core fields (not completion status)."""
    key = f"{row['etkinlik_adi']}|{row['tarih']}|{row['deadline']}"
    return hashlib.md5(key.encode()).hexdigest()


def _parse_deadline(deadline_str: str) -> Optional[datetime]:
    """Parse a deadline string. Tries common Turkish and ISO date formats."""
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%y", "%d/%m/%y"):
        try:
            return datetime.strptime(deadline_str.strip(), fmt)
        except ValueError:
            continue
    return None


def _was_notified(tab_name: str, notif_type: str,
                  row_hash: Optional[str], within_hours: int) -> bool:
    """Return True if this notification was already sent within the given window."""
    with db.get_db() as conn:
        cursor = conn.cursor()
        if row_hash is not None:
            cursor.execute(
                """SELECT sent_at FROM sheet_notifications
                   WHERE tab_name=? AND notification_type=? AND row_hash=?
                   ORDER BY sent_at DESC LIMIT 1""",
                (tab_name, notif_type, row_hash),
            )
        else:
            cursor.execute(
                """SELECT sent_at FROM sheet_notifications
                   WHERE tab_name=? AND notification_type=? AND row_hash IS NULL
                   ORDER BY sent_at DESC LIMIT 1""",
                (tab_name, notif_type),
            )
        record = cursor.fetchone()
        if not record:
            return False
        sent_at = datetime.fromisoformat(record["sent_at"])
        return datetime.utcnow() - sent_at < timedelta(hours=within_hours)


def _record_notification(tab_name: str, notif_type: str, row_hash: Optional[str]):
    """Record that a notification was sent."""
    with db.get_db() as conn:
        conn.execute(
            """INSERT INTO sheet_notifications (tab_name, notification_type, row_hash, sent_at)
               VALUES (?, ?, ?, CURRENT_TIMESTAMP)""",
            (tab_name, notif_type, row_hash),
        )


def _upsert_row(tab_name: str, row: dict, row_hash: str) -> bool:
    """
    Insert the row if it's new; update tamamlandi + last_seen if it exists.
    Returns True if this is a brand-new row.
    """
    with db.get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM sheet_rows WHERE tab_name=? AND row_hash=?",
            (tab_name, row_hash),
        )
        if cursor.fetchone():
            conn.execute(
                """UPDATE sheet_rows
                   SET tamamlandi=?, last_seen_at=CURRENT_TIMESTAMP
                   WHERE tab_name=? AND row_hash=?""",
                (row["tamamlandi"], tab_name, row_hash),
            )
            return False
        else:
            conn.execute(
                """INSERT INTO sheet_rows
                       (tab_name, row_hash, etkinlik_adi, tarih, deadline, tamamlandi)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (tab_name, row_hash,
                 row["etkinlik_adi"], row["tarih"], row["deadline"], row["tamamlandi"]),
            )
            return True


def _touch_tab_state(tab_name: str, updated: bool):
    """Update the tab state record. Sets last_updated_at only when new rows appeared."""
    with db.get_db() as conn:
        if updated:
            conn.execute(
                """INSERT INTO sheet_tab_state (tab_name, last_updated_at, last_checked_at)
                   VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                   ON CONFLICT(tab_name) DO UPDATE SET
                       last_updated_at=CURRENT_TIMESTAMP,
                       last_checked_at=CURRENT_TIMESTAMP""",
                (tab_name,),
            )
        else:
            conn.execute(
                """INSERT INTO sheet_tab_state (tab_name, last_checked_at)
                   VALUES (?, CURRENT_TIMESTAMP)
                   ON CONFLICT(tab_name) DO UPDATE SET
                       last_checked_at=CURRENT_TIMESTAMP""",
                (tab_name,),
            )


def _send_dm(client, user_id: str, text: str):
    """Open a DM channel and send a plain-text message."""
    try:
        resp = client.conversations_open(users=user_id)
        channel_id = resp["channel"]["id"]
        client.chat_postMessage(channel=channel_id, text=text)
        logger.info(f"DM sent to {user_id} ({text[:60].strip()}…)")
    except Exception as e:
        logger.error(f"Failed to DM {user_id}: {e}")


# ---------------------------------------------------------------------------
# Scheduled jobs (called from bot.py)
# ---------------------------------------------------------------------------

def check_for_new_rows(client):
    """
    Detect new rows in all monitored tabs.
    Sends an acknowledgment DM to the responsible leader when a new entry appears.
    Run every 4 hours.
    """
    for tab_name, committee_name in MONITORED_TABS.items():
        try:
            rows = _fetch_tab(tab_name)
            leader_id = db.get_committee_leader(committee_name)
            had_new = False

            for row in rows:
                h = _row_hash(row)
                is_new = _upsert_row(tab_name, row, h)
                if is_new:
                    had_new = True
                    if leader_id and not _was_notified(tab_name, "ack", h, within_hours=24):
                        deadline_display = row["deadline"] or "belirtilmemiş"
                        _send_dm(
                            client, leader_id,
                            f"✅ *{tab_name}* tablosuna yeni giriş eklendi.\n\n"
                            f"*Etkinlik:* {row['etkinlik_adi']}\n"
                            f"*Tarih:* {row['tarih'] or 'belirtilmemiş'}\n"
                            f"*Deadline:* {deadline_display}\n\n"
                            f"Deadline yaklaşınca seni tekrar haberdar edeceğim. "
                            f"Tamamlandığında 'Tamamlandı' sütununa *X* yazmayı unutma."
                        )
                        _record_notification(tab_name, "ack", h)

            _touch_tab_state(tab_name, had_new)

        except Exception as e:
            logger.error(f"check_for_new_rows failed for tab '{tab_name}': {e}")


def check_deadline_alerts(client):
    """
    Send a 3-day warning DM for rows whose deadline is within 3 days and not yet completed.
    Run every 4 hours (deduplication prevents repeat sends within 48 hours).
    """
    now = datetime.utcnow()

    for tab_name, committee_name in MONITORED_TABS.items():
        leader_id = db.get_committee_leader(committee_name)
        if not leader_id:
            continue

        try:
            with db.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT row_hash, etkinlik_adi, deadline
                       FROM sheet_rows
                       WHERE tab_name=? AND tamamlandi != 'X' AND deadline != ''""",
                    (tab_name,),
                )
                rows = cursor.fetchall()

            for row in rows:
                dl = _parse_deadline(row["deadline"])
                if dl is None:
                    continue
                days_left = (dl.date() - now.date()).days
                if 0 <= days_left <= 3:
                    if not _was_notified(tab_name, "deadline_3day", row["row_hash"], within_hours=48):
                        days_label = "bugün" if days_left == 0 else f"{days_left} gün sonra"
                        _send_dm(
                            client, leader_id,
                            f"⏰ *Deadline yaklaşıyor!*\n\n"
                            f"*{tab_name}* — {row['etkinlik_adi']}\n"
                            f"Deadline: *{row['deadline']}* ({days_label})\n\n"
                            f"Tamamlandığında tablodaki 'Tamamlandı' sütununa *X* yaz."
                        )
                        _record_notification(tab_name, "deadline_3day", row["row_hash"])

        except Exception as e:
            logger.error(f"check_deadline_alerts failed for tab '{tab_name}': {e}")


def check_missed_deadlines(client):
    """
    Send a DM when a deadline has passed but the task is not marked complete.
    Re-sends at most every 72 hours per row.
    Run daily.
    """
    now = datetime.utcnow()

    for tab_name, committee_name in MONITORED_TABS.items():
        leader_id = db.get_committee_leader(committee_name)
        if not leader_id:
            continue

        try:
            with db.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """SELECT row_hash, etkinlik_adi, deadline
                       FROM sheet_rows
                       WHERE tab_name=? AND tamamlandi != 'X' AND deadline != ''""",
                    (tab_name,),
                )
                rows = cursor.fetchall()

            for row in rows:
                dl = _parse_deadline(row["deadline"])
                if dl is None:
                    continue
                if dl.date() < now.date():
                    if not _was_notified(tab_name, "deadline_missed", row["row_hash"], within_hours=72):
                        _send_dm(
                            client, leader_id,
                            f"❗ *Deadline geçti*\n\n"
                            f"*{tab_name}* — {row['etkinlik_adi']}\n"
                            f"Deadline *{row['deadline']}* tarihindeydi ve henüz tamamlanmadı.\n\n"
                            f"Tamamlandıysa tabloya *X* yaz. "
                            f"Tamamlanmadıysa ne yapmamız gerek?"
                        )
                        _record_notification(tab_name, "deadline_missed", row["row_hash"])

        except Exception as e:
            logger.error(f"check_missed_deadlines failed for tab '{tab_name}': {e}")


def check_empty_tabs(client):
    """
    Warn a team leader if their tab hasn't had a new entry in 2 days.
    Re-sends at most every 48 hours per tab.
    Run every 4 hours.
    """
    now = datetime.utcnow()

    for tab_name, committee_name in MONITORED_TABS.items():
        leader_id = db.get_committee_leader(committee_name)
        if not leader_id:
            continue

        try:
            with db.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT last_updated_at FROM sheet_tab_state WHERE tab_name=?",
                    (tab_name,),
                )
                state = cursor.fetchone()

            last_updated = (
                datetime.fromisoformat(state["last_updated_at"])
                if state and state["last_updated_at"]
                else None
            )
            is_stale = last_updated is None or (now - last_updated) > timedelta(days=2)

            if is_stale and not _was_notified(tab_name, "empty_tab", None, within_hours=48):
                _send_dm(
                    client, leader_id,
                    f"📋 *{tab_name}* tablosu 2 gündür güncellenmedi.\n\n"
                    f"Yaklaşan bir etkinlik, görev ya da deadline var mı? "
                    f"Varsa şuraya ekleyebilirsin: {SHEET_URL}"
                )
                _record_notification(tab_name, "empty_tab", None)

        except Exception as e:
            logger.error(f"check_empty_tabs failed for tab '{tab_name}': {e}")


def send_weekly_prompt(client):
    """
    Monday morning: DM each team leader to prompt sheet updates for the week.
    """
    for tab_name, committee_name in MONITORED_TABS.items():
        leader_id = db.get_committee_leader(committee_name)
        if not leader_id:
            continue
        try:
            _send_dm(
                client, leader_id,
                f"☀️ Yeni haftaya başlarken hatırlatma!\n\n"
                f"*{tab_name}* ekibi için bu haftaya ait eklemek istediğin "
                f"etkinlik, görev ya da deadline var mı?\n"
                f"Varsa tabloya ekleyebilirsin: {SHEET_URL}"
            )
        except Exception as e:
            logger.error(f"send_weekly_prompt failed for tab '{tab_name}': {e}")


def send_friday_digest(client):
    """
    Friday afternoon: Send a full status summary to the admin (president only).
    """
    if not ADMIN_USER_ID:
        logger.warning("ADMIN_USER_ID not set — Friday digest skipped")
        return

    now = datetime.utcnow()
    lines = ["📊 *Haftalık Tablo Özeti*\n"]

    for tab_name, committee_name in MONITORED_TABS.items():
        try:
            with db.get_db() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT row_hash, etkinlik_adi, deadline, tamamlandi FROM sheet_rows WHERE tab_name=?",
                    (tab_name,),
                )
                all_rows = cursor.fetchall()

                cursor.execute(
                    "SELECT last_updated_at FROM sheet_tab_state WHERE tab_name=?",
                    (tab_name,),
                )
                state = cursor.fetchone()

            total   = len(all_rows)
            done    = sum(1 for r in all_rows if r["tamamlandi"] == "X")
            pending = total - done

            overdue_names = []
            for r in all_rows:
                if r["tamamlandi"] == "X":
                    continue
                dl = _parse_deadline(r["deadline"])
                if dl and dl.date() < now.date():
                    overdue_names.append(r["etkinlik_adi"])

            if state and state["last_updated_at"]:
                lu = datetime.fromisoformat(state["last_updated_at"])
                days_ago = (now.date() - lu.date()).days
                last_upd = "bugün" if days_ago == 0 else f"{days_ago} gün önce"
            else:
                last_upd = "hiç güncellenmedi"

            icon = "✅" if not overdue_names else "❗"
            lines.append(f"{icon} *{tab_name}*")
            lines.append(f"  • Toplam: {total}  |  Tamamlanan: {done}  |  Bekleyen: {pending}")
            if overdue_names:
                lines.append(f"  • ⚠️ Deadline geçmiş: {', '.join(overdue_names)}")
            lines.append(f"  • Son yeni giriş: {last_upd}\n")

        except Exception as e:
            logger.error(f"send_friday_digest failed for tab '{tab_name}': {e}")
            lines.append(f"⚠️ *{tab_name}* okunamadı.\n")

    try:
        _send_dm(client, ADMIN_USER_ID, "\n".join(lines))
    except Exception as e:
        logger.error(f"send_friday_digest: failed to DM admin: {e}")
