"""
SQLite database module for MeetPoll bot.
Handles poll, option, vote, event, RSVP, and onboarding storage operations.
"""

import sqlite3
import os
from datetime import datetime
from typing import Optional
from contextlib import contextmanager

DATABASE_PATH = os.getenv("DATABASE_PATH", "./meetpoll.db")


def get_connection() -> sqlite3.Connection:
    """Get a database connection with row factory enabled."""
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
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


def init_db():
    """Initialize database with required tables."""
    with get_db() as conn:
        cursor = conn.cursor()

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
                channel_id TEXT NOT NULL
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


def create_poll(question: str, creator_id: str, channel_id: str,
                options: list[str], closes_at: Optional[datetime] = None) -> int:
    """
    Create a new poll with options.
    Returns the poll ID.
    """
    with get_db() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO polls (question, creator_id, channel_id, closes_at)
            VALUES (?, ?, ?, ?)
        """, (question, creator_id, channel_id, closes_at))

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
