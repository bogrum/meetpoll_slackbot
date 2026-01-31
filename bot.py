#!/usr/bin/env python3
"""
MeetPoll - A Slack bot for meeting scheduling polls.
Uses Socket Mode for easy deployment without a public URL.
"""

import os
import re
import logging
from datetime import datetime
from dotenv import load_dotenv
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from apscheduler.schedulers.background import BackgroundScheduler

import database as db
import blocks

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Initialize the Slack app
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

# Scheduler for auto-closing polls
scheduler = BackgroundScheduler()


# ============================================================================
# SLASH COMMAND HANDLER
# ============================================================================

@app.command("/meetpoll")
def handle_meetpoll_command(ack, body, client, logger):
    """Handle the /meetpoll slash command - opens the poll creation modal."""
    ack()

    try:
        modal = blocks.build_poll_modal()
        # Store channel_id in private_metadata so we know where to post the poll
        modal["private_metadata"] = body.get("channel_id", body["user_id"])
        client.views_open(
            trigger_id=body["trigger_id"],
            view=modal
        )
    except Exception as e:
        logger.error(f"Error opening modal: {e}")


# ============================================================================
# MODAL SUBMISSION HANDLER
# ============================================================================

@app.view("create_poll_modal")
def handle_poll_creation(ack, body, client, view, logger):
    """Handle poll creation modal submission."""
    values = view["state"]["values"]

    # Extract form values
    question = values["question_block"]["question_input"]["value"].strip()
    options_raw = values["options_block"]["options_input"]["value"]
    close_date = values["close_date_block"]["close_date_input"].get("selected_date")
    close_time = values["close_time_block"]["close_time_input"].get("selected_time")

    # Parse options (one per line)
    options = [opt.strip() for opt in options_raw.split("\n") if opt.strip()]

    # Validate option count
    if len(options) < 5:
        ack({
            "response_action": "errors",
            "errors": {
                "options_block": "Please provide at least 5 time options (one per line)."
            }
        })
        return

    if len(options) > 25:
        ack({
            "response_action": "errors",
            "errors": {
                "options_block": "Maximum 25 options allowed. Please reduce the number of options."
            }
        })
        return

    # Check for duplicate options
    if len(options) != len(set(options)):
        ack({
            "response_action": "errors",
            "errors": {
                "options_block": "Duplicate options found. Each time slot must be unique."
            }
        })
        return

    ack()

    # Parse close datetime
    closes_at = None
    if close_date:
        if close_time:
            closes_at = datetime.strptime(f"{close_date} {close_time}", "%Y-%m-%d %H:%M")
        else:
            closes_at = datetime.strptime(f"{close_date} 23:59", "%Y-%m-%d %H:%M")

    # Get user and channel info
    user_id = body["user"]["id"]
    # Get channel_id from private_metadata (set when modal was opened)
    channel_id = view.get("private_metadata") or user_id

    try:
        # Create poll in database
        poll_id = db.create_poll(
            question=question,
            creator_id=user_id,
            channel_id=channel_id,
            options=options,
            closes_at=closes_at
        )

        # Get fresh data for building message
        poll = db.get_poll(poll_id)
        poll_options = db.get_poll_options(poll_id)
        results = db.get_poll_results(poll_id)

        # Build and post poll message
        poll_blocks = blocks.build_poll_message(
            poll_id=poll_id,
            question=question,
            creator_id=user_id,
            options=poll_options,
            results=results,
            closes_at=closes_at,
            status="open"
        )

        # Post to channel
        response = client.chat_postMessage(
            channel=channel_id,
            blocks=poll_blocks,
            text=f"New poll: {question}"
        )

        # Store message timestamp for updates
        db.update_poll_message_ts(poll_id, response["ts"])

        logger.info(f"Poll {poll_id} created by {user_id} in {channel_id}")

    except Exception as e:
        logger.error(f"Error creating poll: {e}")
        # Note: Error message shown via Slack's built-in error handling


# ============================================================================
# VOTING HANDLER
# ============================================================================

@app.action(re.compile(r"vote_action_\d+_\d+"))
def handle_vote(ack, body, client, logger):
    """Handle checkbox vote selections."""
    ack()

    user_id = body["user"]["id"]

    # Collect all selected options from all checkbox groups in this message
    # action_id format: vote_action_{poll_id}_{chunk_index}
    action = body["actions"][0]
    action_id = action["action_id"]
    parts = action_id.split("_")
    poll_id = int(parts[2])  # vote_action_{poll_id}_{chunk}

    # Get the current user's existing votes
    existing_votes = set(db.get_user_votes(poll_id, user_id))

    # Get all option IDs for this poll to know which chunks they belong to
    poll_options = db.get_poll_options(poll_id)
    chunk_size = 10

    # Determine which chunk was just modified
    chunk_index = int(parts[3])
    chunk_start = chunk_index * chunk_size
    chunk_end = chunk_start + chunk_size
    chunk_option_ids = set(opt["id"] for opt in poll_options[chunk_start:chunk_end])

    # Get newly selected options from this action
    selected_options = action.get("selected_options", [])
    new_chunk_selections = set(int(opt["value"]) for opt in selected_options)

    # Remove old votes for this chunk, add new selections
    updated_votes = (existing_votes - chunk_option_ids) | new_chunk_selections
    selected_ids = list(updated_votes)

    try:
        # Check if poll is still open
        poll = db.get_poll(poll_id)
        if not poll or poll["status"] != "open":
            client.chat_postEphemeral(
                channel=body["channel"]["id"],
                user=user_id,
                text=":lock: This poll is closed and no longer accepting votes."
            )
            return

        # Update votes in database
        db.set_user_votes(poll_id, user_id, selected_ids)

        # Refresh poll message
        update_poll_message(client, poll_id)

        logger.info(f"User {user_id} voted on poll {poll_id}: {selected_ids}")

    except Exception as e:
        logger.error(f"Error recording vote: {e}")


# ============================================================================
# BUTTON ACTION HANDLERS
# ============================================================================

@app.action(re.compile(r"view_results_\d+"))
def handle_view_results(ack, body, client, logger):
    """Handle View Results button click - opens results modal."""
    ack()

    action = body["actions"][0]
    poll_id = int(action["value"])

    try:
        poll = db.get_poll(poll_id)
        if not poll:
            return

        results = db.get_poll_results(poll_id)
        total_voters = db.get_total_voters(poll_id)

        modal = blocks.build_results_modal(
            poll_id=poll_id,
            question=poll["question"],
            results=results,
            total_voters=total_voters,
            status=poll["status"]
        )

        client.views_open(
            trigger_id=body["trigger_id"],
            view=modal
        )

    except Exception as e:
        logger.error(f"Error showing results: {e}")


@app.action(re.compile(r"close_poll_\d+"))
def handle_close_poll(ack, body, client, logger):
    """Handle Close Poll button click."""
    ack()

    action = body["actions"][0]
    poll_id = int(action["value"])
    user_id = body["user"]["id"]

    try:
        poll = db.get_poll(poll_id)
        if not poll:
            return

        # Only creator can close the poll
        if poll["creator_id"] != user_id:
            client.chat_postEphemeral(
                channel=body["channel"]["id"],
                user=user_id,
                text=":warning: Only the poll creator can close this poll."
            )
            return

        # Close the poll
        if db.close_poll(poll_id):
            close_and_update_poll(client, poll_id)
            logger.info(f"Poll {poll_id} closed by {user_id}")

    except Exception as e:
        logger.error(f"Error closing poll: {e}")


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def update_poll_message(client, poll_id: int):
    """Update an existing poll message with current results."""
    try:
        poll = db.get_poll(poll_id)
        if not poll or not poll["message_ts"]:
            return

        poll_options = db.get_poll_options(poll_id)
        results = db.get_poll_results(poll_id)

        closes_at = None
        if poll["closes_at"]:
            closes_at = datetime.fromisoformat(poll["closes_at"])

        poll_blocks = blocks.build_poll_message(
            poll_id=poll_id,
            question=poll["question"],
            creator_id=poll["creator_id"],
            options=poll_options,
            results=results,
            closes_at=closes_at,
            status=poll["status"]
        )

        client.chat_update(
            channel=poll["channel_id"],
            ts=poll["message_ts"],
            blocks=poll_blocks,
            text=f"Poll: {poll['question']}"
        )

    except Exception as e:
        logger.error(f"Error updating poll message: {e}")


def close_and_update_poll(client, poll_id: int):
    """Close a poll and post final results."""
    try:
        poll = db.get_poll(poll_id)
        if not poll:
            return

        results = db.get_poll_results(poll_id)
        total_voters = db.get_total_voters(poll_id)

        # Build closed poll message
        closed_blocks = blocks.build_closed_poll_message(
            poll_id=poll_id,
            question=poll["question"],
            creator_id=poll["creator_id"],
            results=results,
            total_voters=total_voters
        )

        # Update original message
        if poll["message_ts"]:
            client.chat_update(
                channel=poll["channel_id"],
                ts=poll["message_ts"],
                blocks=closed_blocks,
                text=f"Poll Closed: {poll['question']}"
            )

    except Exception as e:
        logger.error(f"Error closing poll: {e}")


def check_expired_polls():
    """Background job to auto-close expired polls."""
    try:
        expired = db.get_expired_polls()
        for poll in expired:
            logger.info(f"Auto-closing expired poll {poll['id']}")
            if db.close_poll(poll["id"]):
                # We need a client instance - get from app
                close_and_update_poll(app.client, poll["id"])
    except Exception as e:
        logger.error(f"Error checking expired polls: {e}")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main function to start the bot."""
    # Initialize database
    db.init_db()
    logger.info("Database initialized")

    # Start scheduler for auto-closing polls
    scheduler.add_job(check_expired_polls, "interval", minutes=1)
    scheduler.start()
    logger.info("Scheduler started")

    # Get app-level token for Socket Mode
    app_token = os.environ.get("SLACK_APP_TOKEN")
    if not app_token:
        logger.error("SLACK_APP_TOKEN not found. Please set it in your .env file.")
        return

    # Start the bot
    handler = SocketModeHandler(app, app_token)
    logger.info("MeetPoll bot starting in Socket Mode...")
    handler.start()


if __name__ == "__main__":
    main()
