"""
SQLite database module for MeetPoll bot.
Handles poll, option, vote, event, RSVP, onboarding, and engagement storage operations.
"""

import sqlite3
import os
import shutil
import logging
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

logger = logging.getLogger(__name__)

DATABASE_PATH = os.getenv("DATABASE_PATH", "./meetpoll.db")

# Schema version — increment when adding migrations
SCHEMA_VERSION = 6


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory and foreign keys enabled."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db():
    """Context manager for database connections."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _get_schema_version(conn) -> int:
    """Get the current schema version from the database."""
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        row = cursor.fetchone()
        return row["version"] if row else 0
    except sqlite3.OperationalError:
        return 0


def _run_migrations(conn):
    """Run any pending schema migrations."""
    cursor = conn.cursor()
    current = _get_schema_version(conn)
    if current >= SCHEMA_VERSION:
        return

    # Migration 1: add group_added to processed_members, leader_user_id to committee_channels
    if current < 1:
        try:
            cursor.execute("ALTER TABLE processed_members ADD COLUMN group_added INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        try:
            cursor.execute("ALTER TABLE committee_channels ADD COLUMN leader_user_id TEXT")
        except sqlite3.OperationalError:
            pass
        logger.info("Applied migration 1: group_added, leader_user_id columns")

    # Migration 2: add anonymous column to polls
    if current < 2:
        try:
            cursor.execute("ALTER TABLE polls ADD COLUMN anonymous INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass
        logger.info("Applied migration 2: anonymous polls column")

    # Migration 3: engagement tables (user_activity, engagement_nudges, milestones)
    if current < 3:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_activity (
                user_id TEXT PRIMARY KEY,
                last_poll_vote TIMESTAMP,
                last_rsvp TIMESTAMP,
                last_message TIMESTAMP,
                last_seen TIMESTAMP,
                total_votes INTEGER DEFAULT 0,
                total_rsvps INTEGER DEFAULT 0
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS engagement_nudges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                nudge_type TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS milestones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                milestone_type TEXT NOT NULL,
                milestone_value INTEGER NOT NULL,
                celebrated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_activity_last_seen ON user_activity(last_seen)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_engagement_nudges_user ON engagement_nudges(user_id, nudge_type)")
        logger.info("Applied migration 3: engagement tables")

    # Migration 4: message_log table for full DM audit trail
    if current < 4:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS message_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_id TEXT NOT NULL,
                message_type TEXT NOT NULL,
                message_text TEXT,
                was_edited INTEGER DEFAULT 0,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_message_log_recipient ON message_log(recipient_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_message_log_sent_at ON message_log(sent_at)")
        logger.info("Applied migration 4: message_log table")

    # Migration 5: google_event_id column for calendar sync
    if current < 5:
        try:
            cursor.execute("ALTER TABLE events ADD COLUMN google_event_id TEXT")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_google_id ON events(google_event_id)")
        except sqlite3.OperationalError:
            pass
        logger.info("Applied migration 5: google_event_id column")


    # Migration 6: sheet monitoring tables
    if current < 6:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sheet_rows (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                tab_name        TEXT NOT NULL,
                row_hash        TEXT NOT NULL,
                etkinlik_adi    TEXT,
                tarih           TEXT,
                deadline        TEXT,
                tamamlandi      TEXT DEFAULT '',
                first_seen_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tab_name, row_hash)
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sheet_notifications (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                tab_name            TEXT NOT NULL,
                notification_type   TEXT NOT NULL,
                row_hash            TEXT,
                sent_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS sheet_tab_state (
                tab_name            TEXT PRIMARY KEY,
                last_updated_at     TIMESTAMP,
                last_checked_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sheet_rows_tab "
            "ON sheet_rows(tab_name)"
        )
        cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_sheet_notif_lookup "
            "ON sheet_notifications(tab_name, notification_type, sent_at)"
        )
        logger.info("Applied migration 6: sheet monitoring tables")

    # Record final version
    cursor.execute("INSERT OR REPLACE INTO schema_version (version, applied_at) VALUES (?, CURRENT_TIMESTAMP)",
                   (SCHEMA_VERSION,))
    conn.commit()
    logger.info(f"Schema updated to version {SCHEMA_VERSION}")


def init_db():
    """Initialize database with required tables and run migrations."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Schema version tracking
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS schema_version (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Polls table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS polls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                creator_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                message_ts TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closes_at TIMESTAMP,
                anonymous INTEGER DEFAULT 0,
                status TEXT DEFAULT 'open' CHECK(status IN ('open', 'closed'))
            )
        """)

        # Options table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS options (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id INTEGER NOT NULL,
                option_text TEXT NOT NULL,
                option_order INTEGER NOT NULL,
                FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE
            )
        """)

        # Votes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS votes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                poll_id INTEGER NOT NULL,
                option_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                voted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (poll_id) REFERENCES polls(id) ON DELETE CASCADE,
                FOREIGN KEY (option_id) REFERENCES options(id) ON DELETE CASCADE,
                UNIQUE(poll_id, option_id, user_id)
            )
        """)

        # Processed members table (onboarding)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS processed_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                first_name TEXT,
                last_name TEXT,
                country TEXT,
                education TEXT,
                affiliations TEXT,
                membership_choice TEXT,
                committees TEXT,
                email_sent INTEGER DEFAULT 0,
                slack_user_id TEXT,
                channels_assigned INTEGER DEFAULT 0,
                dm_sent INTEGER DEFAULT 0,
                group_added INTEGER DEFAULT 0,
                onboarded INTEGER DEFAULT 0,
                sheet_timestamp TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Committee channels mapping
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS committee_channels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                committee_name TEXT UNIQUE NOT NULL,
                channel_id TEXT NOT NULL,
                leader_user_id TEXT
            )
        """)

        # Onboard settings (key-value store)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS onboard_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # Events table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                location TEXT,
                event_datetime TIMESTAMP NOT NULL,
                max_attendees INTEGER,
                creator_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                message_ts TEXT,
                status TEXT DEFAULT 'open' CHECK(status IN ('open', 'closed', 'cancelled')),
                reminder_24h_sent INTEGER DEFAULT 0,
                reminder_1h_sent INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # RSVPs table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS rsvps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id INTEGER NOT NULL,
                user_id TEXT NOT NULL,
                response TEXT NOT NULL CHECK(response IN ('going', 'maybe', 'not_going')),
                responded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
                UNIQUE(event_id, user_id)
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS onboard_admins (
                user_id TEXT PRIMARY KEY,
                added_by TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Outreach campaigns table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS outreach_campaigns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                audience_type TEXT NOT NULL CHECK(audience_type IN ('academics', 'clubs')),
                subject TEXT NOT NULL,
                body TEXT NOT NULL,
                sender_user_id TEXT NOT NULL,
                channel_id TEXT NOT NULL,
                total_recipients INTEGER DEFAULT 0,
                sent_count INTEGER DEFAULT 0,
                failed_count INTEGER DEFAULT 0,
                status TEXT DEFAULT 'draft' CHECK(status IN ('draft', 'sending', 'completed', 'failed', 'cancelled')),
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP
            )
        """)

        # Outreach recipients table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS outreach_recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                campaign_id INTEGER NOT NULL,
                email TEXT NOT NULL,
                name TEXT,
                greeting TEXT NOT NULL,
                status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'sent', 'failed')),
                sent_at TIMESTAMP,
                error_message TEXT,
                FOREIGN KEY (campaign_id) REFERENCES outreach_campaigns(id) ON DELETE CASCADE
            )
        """)

        # Posted opportunities table (RSS feed dedup)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS posted_opportunities (
                guid TEXT PRIMARY KEY,
                title TEXT,
                link TEXT,
                posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Pending opportunities queue (fetched, not yet posted)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS pending_opportunities (
                guid TEXT PRIMARY KEY,
                title TEXT,
                link TEXT,
                summary TEXT,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Engagement tables (also created by migration 3 for existing DBs)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_activity (
                user_id TEXT PRIMARY KEY,
                last_poll_vote TIMESTAMP,
                last_rsvp TIMESTAMP,
                last_message TIMESTAMP,
                last_seen TIMESTAMP,
                total_votes INTEGER DEFAULT 0,
                total_rsvps INTEGER DEFAULT 0
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS engagement_nudges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                nudge_type TEXT NOT NULL,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS milestones (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                milestone_type TEXT NOT NULL,
                milestone_value INTEGER NOT NULL,
                celebrated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Indexes for faster lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_options_poll ON options(poll_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_votes_poll ON votes(poll_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_votes_user ON votes(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_polls_status ON polls(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processed_members_email ON processed_members(email)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_processed_members_slack ON processed_members(slack_user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_status ON events(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_events_datetime ON events(event_datetime)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rsvps_event ON rsvps(event_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_rsvps_user ON rsvps(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_outreach_recipients_campaign ON outreach_recipients(campaign_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_outreach_recipients_status ON outreach_recipients(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_outreach_campaigns_status ON outreach_campaigns(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_activity_last_seen ON user_activity(last_seen)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_engagement_nudges_user ON engagement_nudges(user_id, nudge_type)")

        # Message log — full audit trail of every DM the bot sends
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS message_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipient_id TEXT NOT NULL,
                message_type TEXT NOT NULL,
                message_text TEXT,
                was_edited INTEGER DEFAULT 0,
                sent_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_message_log_recipient ON message_log(recipient_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_message_log_sent_at ON message_log(sent_at)")

        # Run any pending migrations for existing databases
        _run_migrations(conn)
        logger.info("Database initialized successfully")


def create_poll(question: str, creator_id: str, channel_id: str,
                options: list[str], closes_at: Optional[datetime] = None,
                anonymous: bool = False) -> int:
    """
    Create a new poll with options.
    Returns the poll ID.
    """
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO polls (question, creator_id, channel_id, closes_at, anonymous)
            VALUES (?, ?, ?, ?, ?)
        """, (question, creator_id, channel_id, closes_at, 1 if anonymous else 0))

        poll_id = cursor.lastrowid

        for order, option_text in enumerate(options, 1):
            cursor.execute("""
                INSERT INTO options (poll_id, option_text, option_order)
                VALUES (?, ?, ?)
            """, (poll_id, option_text.strip(), order))

        return poll_id


def update_poll_message_ts(poll_id: int, message_ts: str):
    """Store the Slack message timestamp for a poll."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE polls SET message_ts = ? WHERE id = ?",
            (message_ts, poll_id)
        )


def get_poll(poll_id: int) -> Optional[dict]:
    """Get poll details by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM polls WHERE id = ?", (poll_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_poll_options(poll_id: int) -> list[dict]:
    """Get all options for a poll."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM options
            WHERE poll_id = ?
            ORDER BY option_order
        """, (poll_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_votes_for_option(option_id: int) -> list[str]:
    """Get all user IDs who voted for an option."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id FROM votes WHERE option_id = ?",
            (option_id,)
        )
        return [row["user_id"] for row in cursor.fetchall()]


def get_user_votes(poll_id: int, user_id: str) -> list[int]:
    """Get option IDs that a user voted for in a poll."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT option_id FROM votes
            WHERE poll_id = ? AND user_id = ?
        """, (poll_id, user_id))
        return [row["option_id"] for row in cursor.fetchall()]


def set_user_votes(poll_id: int, user_id: str, option_ids: list[int]):
    """
    Set a user's votes for a poll (replaces any existing votes).
    This handles both adding new votes and removing deselected ones.
    """
    with get_db() as conn:
        cursor = conn.cursor()

        # Remove all existing votes by this user for this poll
        cursor.execute("""
            DELETE FROM votes
            WHERE poll_id = ? AND user_id = ?
        """, (poll_id, user_id))

        # Add new votes
        for option_id in option_ids:
            cursor.execute("""
                INSERT INTO votes (poll_id, option_id, user_id)
                VALUES (?, ?, ?)
            """, (poll_id, option_id, user_id))


def get_poll_results(poll_id: int) -> list[dict]:
    """
    Get complete poll results with vote counts and voter lists.
    Returns list of options with their votes.
    """
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT
                o.id,
                o.option_text,
                o.option_order,
                COUNT(v.id) as vote_count
            FROM options o
            LEFT JOIN votes v ON o.id = v.option_id
            WHERE o.poll_id = ?
            GROUP BY o.id
            ORDER BY o.option_order
        """, (poll_id,))

        results = []
        for row in cursor.fetchall():
            result = dict(row)
            result["voters"] = get_votes_for_option(row["id"])
            results.append(result)

        return results


def close_poll(poll_id: int) -> bool:
    """Close a poll. Returns True if successful."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE polls SET status = 'closed' WHERE id = ? AND status = 'open'",
            (poll_id,)
        )
        return cursor.rowcount > 0


def get_expired_polls() -> list[dict]:
    """Get all open polls that have passed their close date."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM polls
            WHERE status = 'open'
            AND closes_at IS NOT NULL
            AND closes_at <= datetime('now')
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_total_voters(poll_id: int) -> int:
    """Get count of unique voters for a poll."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(DISTINCT user_id) as count
            FROM votes WHERE poll_id = ?
        """, (poll_id,))
        row = cursor.fetchone()
        return row["count"] if row else 0


# ============================================================================
# ONBOARDING FUNCTIONS
# ============================================================================

def is_member_processed(email: str) -> bool:
    """Check if a member email has already been processed."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM processed_members WHERE email = ?", (email.lower(),))
        return cursor.fetchone() is not None


def add_processed_member(data: dict) -> bool:
    """Add a new processed member. Returns True if inserted, False if already exists."""
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute("""
                INSERT INTO processed_members
                    (email, first_name, last_name, country, education,
                     affiliations, membership_choice, committees,
                     email_sent, onboarded, sheet_timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                data.get("email", "").lower(),
                data.get("first_name"),
                data.get("last_name"),
                data.get("country"),
                data.get("education"),
                data.get("affiliations"),
                data.get("membership_choice"),
                data.get("committees"),
                data.get("email_sent", 0),
                data.get("onboarded", 0),
                data.get("sheet_timestamp"),
            ))
            return True
        except sqlite3.IntegrityError:
            return False


def get_member_by_email(email: str) -> Optional[dict]:
    """Get a processed member by email."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM processed_members WHERE email = ?", (email.lower(),))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_member_by_slack_user(slack_user_id: str) -> Optional[dict]:
    """Get a processed member by Slack user ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM processed_members WHERE slack_user_id = ?", (slack_user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def mark_email_sent(email: str):
    """Mark that a welcome email was sent to this member."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE processed_members SET email_sent = 1 WHERE email = ?", (email.lower(),))


def mark_dm_sent(email: str):
    """Mark that a welcome DM was sent to this member."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE processed_members SET dm_sent = 1 WHERE email = ?", (email.lower(),))


def mark_channels_assigned(email: str):
    """Mark that committee channels were assigned to this member."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE processed_members SET channels_assigned = 1 WHERE email = ?", (email.lower(),))


def mark_onboarded(email: str):
    """Mark a member as fully onboarded."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE processed_members SET onboarded = 1 WHERE email = ?", (email.lower(),))


def set_member_slack_user(email: str, slack_user_id: str):
    """Associate a Slack user ID with a processed member."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE processed_members SET slack_user_id = ? WHERE email = ?",
            (slack_user_id, email.lower())
        )


def set_committee_channel(committee_name: str, channel_id: str):
    """Set or update a committee→channel mapping."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO committee_channels (committee_name, channel_id)
            VALUES (?, ?)
            ON CONFLICT(committee_name) DO UPDATE SET channel_id = ?
        """, (committee_name, channel_id, channel_id))


def get_committee_channel(committee_name: str) -> Optional[str]:
    """Get the channel ID for a committee name."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT channel_id FROM committee_channels WHERE committee_name = ?",
            (committee_name,)
        )
        row = cursor.fetchone()
        return row["channel_id"] if row else None


def get_all_committee_channels() -> list[dict]:
    """Get all committee→channel mappings."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM committee_channels ORDER BY committee_name")
        return [dict(row) for row in cursor.fetchall()]


def delete_committee_channel(committee_name: str) -> bool:
    """Delete a committee→channel mapping. Returns True if deleted."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM committee_channels WHERE committee_name = ?", (committee_name,))
        return cursor.rowcount > 0


def set_committee_leader(committee_name: str, leader_user_id: Optional[str]) -> bool:
    """Set or clear the leader for a committee. Returns True if the committee exists."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE committee_channels SET leader_user_id = ? WHERE committee_name = ?",
            (leader_user_id, committee_name)
        )
        return cursor.rowcount > 0


def get_committee_leader(committee_name: str) -> Optional[str]:
    """Get the leader Slack user ID for a committee, or None if not set."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT leader_user_id FROM committee_channels WHERE committee_name = ?",
            (committee_name,)
        )
        row = cursor.fetchone()
        return row["leader_user_id"] if row else None


def get_setting(key: str) -> Optional[str]:
    """Get an onboard setting value."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM onboard_settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row["value"] if row else None


def set_setting(key: str, value: str):
    """Set an onboard setting value."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO onboard_settings (key, value)
            VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = ?
        """, (key, value, value))


def get_onboarding_stats() -> dict:
    """Get onboarding statistics."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                SUM(email_sent) as emails_sent,
                SUM(CASE WHEN slack_user_id IS NOT NULL THEN 1 ELSE 0 END) as joined_slack,
                SUM(channels_assigned) as channels_assigned,
                SUM(dm_sent) as dms_sent,
                SUM(onboarded) as fully_onboarded
            FROM processed_members
        """)
        row = cursor.fetchone()
        return dict(row) if row else {}


def unseed_members_since(cutoff_date: datetime) -> int:
    """Reset email_sent and onboarded flags for seeded members registered after a date.
    Returns the number of members affected."""
    with get_db() as conn:
        cursor = conn.cursor()
        # Get all seeded members (onboarded=1, no slack user yet)
        cursor.execute("""
            SELECT email, sheet_timestamp FROM processed_members
            WHERE onboarded = 1 AND email_sent = 1 AND slack_user_id IS NULL
        """)
        count = 0
        for row in cursor.fetchall():
            ts = row["sheet_timestamp"]
            if not ts:
                continue
            try:
                member_date = datetime.strptime(ts.split(".")[0], "%m/%d/%Y %H:%M:%S")
            except ValueError:
                try:
                    member_date = datetime.strptime(ts.split(".")[0], "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    continue
            if member_date >= cutoff_date:
                cursor.execute("""
                    UPDATE processed_members
                    SET email_sent = 0, onboarded = 0
                    WHERE email = ?
                """, (row["email"],))
                count += 1
        return count


def get_pending_email_members() -> list[dict]:
    """Get members who need welcome emails (not yet sent, not pre-seeded as onboarded)."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM processed_members
            WHERE email_sent = 0 AND onboarded = 0
        """)
        return [dict(row) for row in cursor.fetchall()]


# ============================================================================
# ONBOARD ADMIN FUNCTIONS
# ============================================================================

def add_onboard_admin(user_id: str, added_by: str) -> bool:
    """Add a user as onboard admin. Returns True if newly added."""
    with get_db() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                "INSERT INTO onboard_admins (user_id, added_by) VALUES (?, ?)",
                (user_id, added_by)
            )
            return True
        except sqlite3.IntegrityError:
            return False


def remove_onboard_admin(user_id: str) -> bool:
    """Remove a user from onboard admins. Returns True if removed."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM onboard_admins WHERE user_id = ?", (user_id,))
        return cursor.rowcount > 0


def is_onboard_admin(user_id: str) -> bool:
    """Check if a user is an onboard admin."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM onboard_admins WHERE user_id = ?", (user_id,))
        return cursor.fetchone() is not None


def get_all_onboard_admins() -> list[str]:
    """Get all onboard admin user IDs."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT user_id FROM onboard_admins ORDER BY added_at")
        return [row["user_id"] for row in cursor.fetchall()]


# ============================================================================
# EVENT FUNCTIONS
# ============================================================================

def create_event(title: str, description: str, location: str,
                 event_datetime: str, max_attendees: Optional[int],
                 creator_id: str, channel_id: str) -> int:
    """Create a new event. Returns the event ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO events (title, description, location, event_datetime,
                                max_attendees, creator_id, channel_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (title, description, location, event_datetime,
              max_attendees, creator_id, channel_id))
        return cursor.lastrowid


def get_event(event_id: int) -> Optional[dict]:
    """Get event details by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM events WHERE id = ?", (event_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def update_event_message_ts(event_id: int, message_ts: str):
    """Store the Slack message timestamp for an event."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE events SET message_ts = ? WHERE id = ?",
            (message_ts, event_id)
        )


def set_rsvp(event_id: int, user_id: str, response: str):
    """Set or update a user's RSVP for an event."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO rsvps (event_id, user_id, response)
            VALUES (?, ?, ?)
            ON CONFLICT(event_id, user_id) DO UPDATE SET
                response = ?, responded_at = CURRENT_TIMESTAMP
        """, (event_id, user_id, response, response))


def get_event_rsvps(event_id: int) -> list[dict]:
    """Get all RSVPs for an event."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM rsvps WHERE event_id = ?
            ORDER BY responded_at
        """, (event_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_rsvp_counts(event_id: int) -> dict:
    """Get RSVP counts by response type."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT response, COUNT(*) as count
            FROM rsvps WHERE event_id = ?
            GROUP BY response
        """, (event_id,))
        counts = {"going": 0, "maybe": 0, "not_going": 0}
        for row in cursor.fetchall():
            counts[row["response"]] = row["count"]
        return counts


def get_user_rsvp(event_id: int, user_id: str) -> Optional[str]:
    """Get a user's RSVP response for an event."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT response FROM rsvps WHERE event_id = ? AND user_id = ?",
            (event_id, user_id)
        )
        row = cursor.fetchone()
        return row["response"] if row else None


def get_rsvp_users(event_id: int, response: str) -> list[str]:
    """Get user IDs for a specific RSVP response."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT user_id FROM rsvps WHERE event_id = ? AND response = ?",
            (event_id, response)
        )
        return [row["user_id"] for row in cursor.fetchall()]


def close_event(event_id: int) -> bool:
    """Close an event. Returns True if successful."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE events SET status = 'closed' WHERE id = ? AND status = 'open'",
            (event_id,)
        )
        return cursor.rowcount > 0


def cancel_event(event_id: int) -> bool:
    """Cancel an event. Returns True if successful."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE events SET status = 'cancelled' WHERE id = ? AND status = 'open'",
            (event_id,)
        )
        return cursor.rowcount > 0


def get_upcoming_events_for_reminders() -> list[dict]:
    """Get open events that need reminders sent."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM events
            WHERE status = 'open'
            AND (
                (reminder_24h_sent = 0 AND event_datetime <= datetime('now', '+24 hours')
                    AND event_datetime > datetime('now'))
                OR
                (reminder_1h_sent = 0 AND event_datetime <= datetime('now', '+1 hour')
                    AND event_datetime > datetime('now'))
            )
        """)
        return [dict(row) for row in cursor.fetchall()]


def mark_reminder_sent(event_id: int, reminder_type: str):
    """Mark a reminder as sent. reminder_type is '24h' or '1h'."""
    col = "reminder_24h_sent" if reminder_type == "24h" else "reminder_1h_sent"
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE events SET {col} = 1 WHERE id = ?", (event_id,))


def get_past_open_events() -> list[dict]:
    """Get open events whose datetime has passed."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM events
            WHERE status = 'open'
            AND event_datetime <= datetime('now')
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_upcoming_events(limit: int = 10) -> list[dict]:
    """Get upcoming open events."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM events
            WHERE status = 'open'
            AND event_datetime > datetime('now')
            ORDER BY event_datetime ASC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


def upsert_calendar_event(ev: dict):
    """Insert or update an event from Google Calendar."""
    with get_db() as conn:
        cursor = conn.cursor()
        # Try to find existing event by google_event_id
        cursor.execute("SELECT id FROM events WHERE google_event_id = ?", (ev["gcal_id"],))
        row = cursor.fetchone()

        if row:
            # Update existing
            cursor.execute("""
                UPDATE events SET
                    title = ?, description = ?, location = ?,
                    event_datetime = ?, status = 'open'
                WHERE google_event_id = ?
            """, (ev["title"], ev["description"], ev["location"],
                  ev["start_datetime"], ev["gcal_id"]))
        else:
            # Insert new
            # creator_id and channel_id are required; we use 'system' or similar if unknown
            cursor.execute("""
                INSERT INTO events
                    (title, description, location, event_datetime,
                     creator_id, channel_id, google_event_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (ev["title"], ev["description"], ev["location"],
                  ev["start_datetime"], "system", "system", ev["gcal_id"]))


def prune_stale_calendar_events():
    """Close events that were synced from Google but are no longer in the latest sync.
    Actually, we just close them if they are in the past or were deleted from GCal.
    For simplicity in this bot, we'll just close open events that have passed.
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE events
            SET status = 'closed'
            WHERE status = 'open'
            AND google_event_id IS NOT NULL
            AND event_datetime < datetime('now')
        """)


# ============================================================================
# OUTREACH FUNCTIONS
# ============================================================================

def create_outreach_campaign(audience_type: str, subject: str, body: str,
                              sender_user_id: str, channel_id: str) -> int:
    """Create a new outreach campaign. Returns the campaign ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO outreach_campaigns
                (audience_type, subject, body, sender_user_id, channel_id)
            VALUES (?, ?, ?, ?, ?)
        """, (audience_type, subject, body, sender_user_id, channel_id))
        return cursor.lastrowid


def add_outreach_recipients(campaign_id: int, recipients: list[dict]):
    """Bulk insert recipients and update campaign total count.
    Each recipient dict: {email, name, greeting}
    """
    with get_db() as conn:
        cursor = conn.cursor()
        for r in recipients:
            cursor.execute("""
                INSERT INTO outreach_recipients (campaign_id, email, name, greeting)
                VALUES (?, ?, ?, ?)
            """, (campaign_id, r["email"], r.get("name", ""), r["greeting"]))
        cursor.execute(
            "UPDATE outreach_campaigns SET total_recipients = ? WHERE id = ?",
            (len(recipients), campaign_id)
        )


def get_outreach_campaign(campaign_id: int) -> Optional[dict]:
    """Get an outreach campaign by ID."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM outreach_campaigns WHERE id = ?", (campaign_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_outreach_recipients(campaign_id: int) -> list[dict]:
    """Get all recipients for a campaign."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM outreach_recipients
            WHERE campaign_id = ?
            ORDER BY id
        """, (campaign_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_pending_outreach_recipients(campaign_id: int) -> list[dict]:
    """Get all pending recipients for a campaign."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM outreach_recipients
            WHERE campaign_id = ? AND status = 'pending'
            ORDER BY id
        """, (campaign_id,))
        return [dict(row) for row in cursor.fetchall()]


def mark_outreach_recipient_sent(recipient_id: int):
    """Mark a recipient as successfully sent."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE outreach_recipients
            SET status = 'sent', sent_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (recipient_id,))


def mark_outreach_recipient_failed(recipient_id: int, error: str):
    """Mark a recipient as failed with error message."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE outreach_recipients
            SET status = 'failed', error_message = ?
            WHERE id = ?
        """, (error, recipient_id))


def update_outreach_campaign_counts(campaign_id: int):
    """Recalculate sent/failed counts from recipients table."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed
            FROM outreach_recipients WHERE campaign_id = ?
        """, (campaign_id,))
        row = cursor.fetchone()
        cursor.execute("""
            UPDATE outreach_campaigns
            SET sent_count = ?, failed_count = ?
            WHERE id = ?
        """, (row["sent"] or 0, row["failed"] or 0, campaign_id))


def update_outreach_campaign_status(campaign_id: int, status: str,
                                     completed: bool = False):
    """Update a campaign's status. Optionally set completed_at."""
    with get_db() as conn:
        cursor = conn.cursor()
        if completed:
            cursor.execute("""
                UPDATE outreach_campaigns
                SET status = ?, completed_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (status, campaign_id))
        else:
            cursor.execute(
                "UPDATE outreach_campaigns SET status = ? WHERE id = ?",
                (status, campaign_id)
            )


def get_outreach_stats() -> dict:
    """Get aggregate outreach statistics."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as total_campaigns,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'sending' THEN 1 ELSE 0 END) as in_progress,
                SUM(CASE WHEN status = 'cancelled' THEN 1 ELSE 0 END) as cancelled,
                SUM(sent_count) as total_sent,
                SUM(failed_count) as total_failed
            FROM outreach_campaigns
        """)
        row = cursor.fetchone()
        return dict(row) if row else {}


def get_recent_outreach_campaigns(limit: int = 10) -> list[dict]:
    """Get recent outreach campaigns ordered by creation date."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM outreach_campaigns
            ORDER BY created_at DESC
            LIMIT ?
        """, (limit,))
        return [dict(row) for row in cursor.fetchall()]


# ============================================================================
# GOOGLE GROUPS FUNCTIONS
# ============================================================================

def mark_group_added(email: str):
    """Mark that a member has been added to the Google Group."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE processed_members SET group_added = 1 WHERE email = ?",
            (email.lower(),)
        )


def get_pending_group_members() -> list[dict]:
    """Get members who received a welcome email but haven't been added to the Google Group yet."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM processed_members
            WHERE email_sent = 1 AND group_added = 0
        """)
        return [dict(row) for row in cursor.fetchall()]


# ============================================================================
# RSS OPPORTUNITIES FUNCTIONS
# ============================================================================

def is_opportunity_posted(guid: str) -> bool:
    """Check if an RSS opportunity has already been posted to Slack."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM posted_opportunities WHERE guid = ?", (guid,))
        return cursor.fetchone() is not None


def mark_opportunity_posted(guid: str, title: str, link: str):
    """Record that an RSS opportunity has been posted to Slack."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO posted_opportunities (guid, title, link)
            VALUES (?, ?, ?)
        """, (guid, title, link))


def count_opportunities_posted_today() -> int:
    """Return how many opportunities have been posted today."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM posted_opportunities
            WHERE date(posted_at) = date('now')
        """)
        row = cursor.fetchone()
        return row["cnt"] if row else 0


def is_opportunity_pending(guid: str) -> bool:
    """Check if an opportunity is already in the pending queue."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM pending_opportunities WHERE guid = ?", (guid,))
        return cursor.fetchone() is not None


def add_pending_opportunity(opp: dict):
    """Add an opportunity to the pending queue."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR IGNORE INTO pending_opportunities (guid, title, link, summary)
            VALUES (?, ?, ?, ?)
        """, (opp["guid"], opp["title"], opp["link"], opp.get("summary", "")))


def get_pending_opportunity(guid: str) -> Optional[dict]:
    """Get a single pending opportunity by guid."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pending_opportunities WHERE guid = ?", (guid,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_pending_opportunities() -> list[dict]:
    """Get all pending opportunities ordered by when they were added."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM pending_opportunities ORDER BY added_at")
        return [dict(row) for row in cursor.fetchall()]


def count_pending_opportunities() -> int:
    """Return the number of items currently in the pending queue."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM pending_opportunities")
        return cursor.fetchone()[0]


def remove_pending_opportunity(guid: str):
    """Remove an opportunity from the pending queue."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM pending_opportunities WHERE guid = ?", (guid,))


# ============================================================================
# RSVP TOGGLE (Phase 2)
# ============================================================================

def delete_rsvp(event_id: int, user_id: str) -> bool:
    """Remove a user's RSVP entirely. Returns True if deleted."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM rsvps WHERE event_id = ? AND user_id = ?", (event_id, user_id))
        return cursor.rowcount > 0


# ============================================================================
# DATABASE OPERATIONS (Phase 4)
# ============================================================================

def get_db_size() -> str:
    """Get the database file size as a human-readable string."""
    try:
        size = os.path.getsize(DATABASE_PATH)
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        else:
            return f"{size / (1024 * 1024):.1f} MB"
    except OSError:
        return "unknown"


def get_db_stats() -> dict:
    """Get row counts per table for health monitoring."""
    tables = ["polls", "votes", "events", "rsvps", "processed_members",
              "outreach_campaigns", "posted_opportunities", "pending_opportunities",
              "user_activity"]
    stats = {}
    with get_db() as conn:
        cursor = conn.cursor()
        for table in tables:
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                stats[table] = cursor.fetchone()[0]
            except Exception:
                stats[table] = 0
    return stats


def backup_database() -> Optional[str]:
    """Create a timestamped backup of the database. Returns backup path or None on failure."""
    try:
        if not os.path.exists(DATABASE_PATH):
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"{DATABASE_PATH}.bak.{timestamp}"
        shutil.copy2(DATABASE_PATH, backup_path)
        logger.info(f"Database backed up to {backup_path}")

        # Keep only the last 7 backups
        import glob
        backups = sorted(glob.glob(f"{DATABASE_PATH}.bak.*"))
        while len(backups) > 7:
            oldest = backups.pop(0)
            try:
                os.remove(oldest)
                logger.info(f"Removed old backup {oldest}")
            except OSError:
                pass

        return backup_path
    except Exception as e:
        logger.error(f"Database backup failed: {e}")
        return None


# ============================================================================
# ANALYTICS (Phase 5)
# ============================================================================

def get_poll_analytics() -> dict:
    """Get poll engagement analytics."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as total_polls,
                SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as closed_polls,
                SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as open_polls
            FROM polls
        """)
        row = cursor.fetchone()
        result = dict(row) if row else {}

        cursor.execute("SELECT COUNT(*) as total_votes FROM votes")
        result["total_votes"] = cursor.fetchone()["total_votes"]

        cursor.execute("SELECT COUNT(DISTINCT user_id) as unique_voters FROM votes")
        result["unique_voters"] = cursor.fetchone()["unique_voters"]

        total_polls = result.get("total_polls", 0) or 0
        total_votes = result.get("total_votes", 0) or 0
        result["avg_votes_per_poll"] = round(total_votes / total_polls, 1) if total_polls > 0 else 0

        return result


def get_event_analytics() -> dict:
    """Get event engagement analytics."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                COUNT(*) as total_events,
                SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) as upcoming_events,
                SUM(CASE WHEN status = 'closed' THEN 1 ELSE 0 END) as past_events
            FROM events
        """)
        row = cursor.fetchone()
        result = dict(row) if row else {}

        cursor.execute("SELECT COUNT(*) as total_rsvps FROM rsvps")
        result["total_rsvps"] = cursor.fetchone()["total_rsvps"]

        cursor.execute("""
            SELECT COUNT(*) as total_going FROM rsvps WHERE response = 'going'
        """)
        result["total_going"] = cursor.fetchone()["total_going"]

        total_events = result.get("total_events", 0) or 0
        total_rsvps = result.get("total_rsvps", 0) or 0
        result["avg_rsvps_per_event"] = round(total_rsvps / total_events, 1) if total_events > 0 else 0

        return result


def get_onboarding_trends() -> dict:
    """Get onboarding trends."""
    with get_db() as conn:
        cursor = conn.cursor()
        # Members this month
        cursor.execute("""
            SELECT COUNT(*) as this_month FROM processed_members
            WHERE created_at >= date('now', 'start of month')
        """)
        this_month = cursor.fetchone()["this_month"]

        # Members last month
        cursor.execute("""
            SELECT COUNT(*) as last_month FROM processed_members
            WHERE created_at >= date('now', 'start of month', '-1 month')
            AND created_at < date('now', 'start of month')
        """)
        last_month = cursor.fetchone()["last_month"]

        # Conversion rate (email sent → joined slack)
        cursor.execute("""
            SELECT
                SUM(email_sent) as emails_sent,
                SUM(CASE WHEN slack_user_id IS NOT NULL THEN 1 ELSE 0 END) as joined
            FROM processed_members
        """)
        row = cursor.fetchone()
        emails_sent = row["emails_sent"] or 0
        joined = row["joined"] or 0
        conversion = round(joined / emails_sent * 100, 1) if emails_sent > 0 else 0

        return {
            "this_month": this_month,
            "last_month": last_month,
            "conversion_rate": conversion,
            "emails_sent": emails_sent,
            "joined_slack": joined,
        }


# ============================================================================
# ENGAGEMENT SYSTEM (Phase 6)
# ============================================================================

def record_user_activity(user_id: str, activity_type: str):
    """Record a user's activity. activity_type: 'poll_vote', 'rsvp', 'message'."""
    with get_db() as conn:
        cursor = conn.cursor()
        now = datetime.now().isoformat()

        # Upsert user_activity row
        cursor.execute("""
            INSERT INTO user_activity (user_id, last_seen)
            VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET last_seen = ?
        """, (user_id, now, now))

        if activity_type == "poll_vote":
            cursor.execute("""
                UPDATE user_activity
                SET last_poll_vote = ?, total_votes = total_votes + 1
                WHERE user_id = ?
            """, (now, user_id))
        elif activity_type == "rsvp":
            cursor.execute("""
                UPDATE user_activity
                SET last_rsvp = ?, total_rsvps = total_rsvps + 1
                WHERE user_id = ?
            """, (now, user_id))
        elif activity_type == "message":
            cursor.execute("""
                UPDATE user_activity SET last_message = ? WHERE user_id = ?
            """, (now, user_id))


def get_inactive_users(days: int = 30) -> list[dict]:
    """Get Slack members who haven't been active in N days (or have no activity at all)."""
    with get_db() as conn:
        cursor = conn.cursor()
        # Members with stale activity
        cursor.execute("""
            SELECT ua.user_id, ua.last_seen, ua.total_votes, ua.total_rsvps,
                   pm.first_name, pm.last_name, pm.email
            FROM user_activity ua
            LEFT JOIN processed_members pm ON pm.slack_user_id = ua.user_id
            WHERE ua.last_seen < datetime('now', ? || ' days')
            ORDER BY ua.last_seen ASC
        """, (f"-{days}",))
        stale = [dict(row) for row in cursor.fetchall()]

        # Members on Slack who have never interacted with the bot
        cursor.execute("""
            SELECT pm.slack_user_id as user_id, NULL as last_seen, 0 as total_votes, 0 as total_rsvps,
                   pm.first_name, pm.last_name, pm.email
            FROM processed_members pm
            WHERE pm.slack_user_id IS NOT NULL
            AND pm.slack_user_id NOT IN (SELECT user_id FROM user_activity)
        """)
        never_active = [dict(row) for row in cursor.fetchall()]

        return stale + never_active


def get_user_engagement_stats() -> dict:
    """Get aggregate engagement statistics for admin view."""
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("SELECT COUNT(*) as total FROM user_activity")
        total = cursor.fetchone()["total"]

        # Active: seen in last 7 days
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM user_activity
            WHERE last_seen >= datetime('now', '-7 days')
        """)
        active = cursor.fetchone()["cnt"]

        # Semi-active: seen 7-30 days ago
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM user_activity
            WHERE last_seen < datetime('now', '-7 days')
            AND last_seen >= datetime('now', '-30 days')
        """)
        semi_active = cursor.fetchone()["cnt"]

        # Inactive: not seen in 30+ days
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM user_activity
            WHERE last_seen < datetime('now', '-30 days')
        """)
        inactive = cursor.fetchone()["cnt"]

        # Never interacted (on Slack but no activity rows)
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM processed_members
            WHERE slack_user_id IS NOT NULL
            AND slack_user_id NOT IN (SELECT user_id FROM user_activity)
        """)
        never_tracked = cursor.fetchone()["cnt"]

        # Total Slack members
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM processed_members
            WHERE slack_user_id IS NOT NULL
        """)
        total_slack = cursor.fetchone()["cnt"]

        return {
            "total_tracked": total,
            "total_slack": total_slack,
            "active_7d": active,
            "semi_active_30d": semi_active,
            "inactive_30d": inactive + never_tracked,
            "never_tracked": never_tracked,
        }


def record_nudge_sent(user_id: str, nudge_type: str):
    """Record that a nudge DM was sent."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO engagement_nudges (user_id, nudge_type)
            VALUES (?, ?)
        """, (user_id, nudge_type))


def was_nudge_sent_recently(user_id: str, nudge_type: str, days: int = 14) -> bool:
    """Check if a nudge was sent to a user within the cooldown period."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM engagement_nudges
            WHERE user_id = ? AND nudge_type = ?
            AND sent_at >= datetime('now', ? || ' days')
        """, (user_id, nudge_type, f"-{days}"))
        return cursor.fetchone() is not None


def is_nudge_dismissed(user_id: str) -> bool:
    """Check if a user has been permanently dismissed from nudging."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 1 FROM engagement_nudges
            WHERE user_id = ? AND nudge_type = 'dismissed'
        """, (user_id,))
        return cursor.fetchone() is not None


def mark_nudge_dismissed(user_id: str):
    """Permanently dismiss a user from the nudge system."""
    record_nudge_sent(user_id, "dismissed")


def find_member_by_name(query: str) -> Optional[dict]:
    """Find a processed member by partial first/last name match. Prefers linked Slack users."""
    query = query.strip()
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM processed_members
            WHERE first_name LIKE ? OR last_name LIKE ?
               OR (first_name || ' ' || last_name) LIKE ?
            ORDER BY (slack_user_id IS NOT NULL) DESC
            LIMIT 1
        """, (f"%{query}%", f"%{query}%", f"%{query}%"))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_next_milestone() -> Optional[int]:
    """Check if member count crossed a milestone (50, 100, 150, ...).
    Returns the milestone value if uncelebrated, None otherwise."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) as cnt FROM processed_members WHERE slack_user_id IS NOT NULL")
        member_count = cursor.fetchone()["cnt"]

        if member_count < 50:
            return None

        # Find the highest milestone that applies
        milestone = (member_count // 50) * 50

        # Check if already celebrated
        cursor.execute("""
            SELECT 1 FROM milestones
            WHERE milestone_type = 'member_count' AND milestone_value = ?
        """, (milestone,))
        if cursor.fetchone():
            return None

        return milestone


def record_milestone(milestone_type: str, milestone_value: int):
    """Record that a milestone was celebrated."""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO milestones (milestone_type, milestone_value)
            VALUES (?, ?)
        """, (milestone_type, milestone_value))


def get_weekly_digest_data() -> dict:
    """Gather data for the weekly community digest."""
    with get_db() as conn:
        cursor = conn.cursor()

        # Upcoming events (next 14 days)
        cursor.execute("""
            SELECT id, title, event_datetime FROM events
            WHERE status = 'open'
            AND event_datetime > datetime('now')
            AND event_datetime <= datetime('now', '+14 days')
            ORDER BY event_datetime ASC LIMIT 5
        """)
        upcoming_events = [dict(row) for row in cursor.fetchall()]

        # Active polls
        cursor.execute("""
            SELECT id, question FROM polls
            WHERE status = 'open' LIMIT 5
        """)
        active_polls = [dict(row) for row in cursor.fetchall()]

        # New members this week
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM processed_members
            WHERE created_at >= datetime('now', '-7 days')
        """)
        new_members = cursor.fetchone()["cnt"]

        # Opportunities posted this week
        cursor.execute("""
            SELECT COUNT(*) as cnt FROM posted_opportunities
            WHERE posted_at >= datetime('now', '-7 days')
        """)
        opportunities_this_week = cursor.fetchone()["cnt"]

        # Total member count
        cursor.execute("SELECT COUNT(*) as cnt FROM processed_members WHERE slack_user_id IS NOT NULL")
        total_members = cursor.fetchone()["cnt"]

        return {
            "upcoming_events": upcoming_events,
            "active_polls": active_polls,
            "new_members": new_members,
            "opportunities_this_week": opportunities_this_week,
            "total_members": total_members,
        }


# ============================================================================
# MESSAGE LOG
# ============================================================================

def log_message(recipient_id: str, message_type: str, message_text: str,
                was_edited: bool = False):
    """Log every DM the bot sends for full audit trail.

    Args:
        recipient_id: Slack user ID of the recipient
        message_type: Type of message ('welcome_dm', 'nudge', 'committee_leader_notification',
                      'event_reminder', 'weekly_digest', 'milestone')
        message_text: Plain-text content of the message
        was_edited: True if an admin edited the draft before sending
    """
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO message_log (recipient_id, message_type, message_text, was_edited)
            VALUES (?, ?, ?, ?)
        """, (recipient_id, message_type, message_text, 1 if was_edited else 0))


def get_message_log(recipient_id: str = None, message_type: str = None,
                    days: int = 30, limit: int = 50) -> list[dict]:
    """Query the message log. Optionally filter by recipient, type, or recency."""
    with get_db() as conn:
        cursor = conn.cursor()
        conditions = ["sent_at >= datetime('now', ? || ' days')"]
        params = [f"-{days}"]

        if recipient_id:
            conditions.append("recipient_id = ?")
            params.append(recipient_id)
        if message_type:
            conditions.append("message_type = ?")
            params.append(message_type)

        where = " AND ".join(conditions)
        params.append(limit)
        cursor.execute(f"""
            SELECT * FROM message_log
            WHERE {where}
            ORDER BY sent_at DESC
            LIMIT ?
        """, params)
        return [dict(row) for row in cursor.fetchall()]
