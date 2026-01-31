"""
SQLite database module for MeetPoll bot.
Handles all poll, option, and vote storage operations.
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

        # Indexes for faster lookups
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_options_poll ON options(poll_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_votes_poll ON votes(poll_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_votes_user ON votes(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_polls_status ON polls(status)")


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
