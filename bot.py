#!/usr/bin/env python3
"""
MeetPoll - A Slack bot for meeting scheduling polls, events, and member onboarding.
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
import sheets
import mailer

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

# Scheduler for background jobs
scheduler = BackgroundScheduler()

# Onboarding config from env
SLACK_INVITE_LINK = os.getenv("SLACK_INVITE_LINK", "")
WELCOME_METHOD = os.getenv("WELCOME_METHOD", "email")
ONBOARD_AFTER_DATE = os.getenv("ONBOARD_AFTER_DATE", "")
ONBOARD_SUPER_ADMIN = os.getenv("ONBOARD_SUPER_ADMIN", "")


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
# /event SLASH COMMAND HANDLER
# ============================================================================

@app.command("/event")
def handle_event_command(ack, body, client, logger):
    """Handle the /event slash command with subcommands: create, list."""
    ack()

    text = (body.get("text") or "").strip()
    user_id = body["user_id"]
    channel_id = body.get("channel_id", user_id)

    if text == "create":
        try:
            modal = blocks.build_event_modal()
            modal["private_metadata"] = channel_id
            client.views_open(trigger_id=body["trigger_id"], view=modal)
        except Exception as e:
            logger.error(f"Error opening event modal: {e}")

    elif text == "list":
        try:
            upcoming = db.get_upcoming_events(limit=10)
            if not upcoming:
                client.chat_postEphemeral(
                    channel=channel_id, user=user_id,
                    text="No upcoming events. Use `/event create` to create one!"
                )
                return

            lines = [":calendar: *Upcoming Events:*\n"]
            for ev in upcoming:
                try:
                    dt = datetime.fromisoformat(ev["event_datetime"])
                    dt_str = dt.strftime("%b %d, %Y %I:%M %p")
                except (ValueError, TypeError):
                    dt_str = ev["event_datetime"]
                counts = db.get_rsvp_counts(ev["id"])
                lines.append(
                    f"*{ev['title']}* — {dt_str} "
                    f"({counts['going']} going, {counts['maybe']} maybe)"
                )

            client.chat_postEphemeral(
                channel=channel_id, user=user_id,
                text="\n".join(lines)
            )
        except Exception as e:
            logger.error(f"Error listing events: {e}")
    else:
        client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text="Usage: `/event create` or `/event list`"
        )


# ============================================================================
# /onboard SLASH COMMAND HANDLER
# ============================================================================

def _is_onboard_authorized(user_id: str) -> bool:
    """Check if a user is authorized to use /onboard commands."""
    if ONBOARD_SUPER_ADMIN and user_id == ONBOARD_SUPER_ADMIN:
        return True
    return db.is_onboard_admin(user_id)


@app.command("/onboard")
def handle_onboard_command(ack, body, client, logger):
    """Handle the /onboard slash command with subcommands."""
    ack()

    text = (body.get("text") or "").strip()
    user_id = body["user_id"]
    channel_id = body.get("channel_id", user_id)

    # Admin subcommands (only super admin can manage admins)
    if text.startswith("admin"):
        _handle_onboard_admin(text, channel_id, user_id, client)
        return

    # Check authorization for all other commands
    if not _is_onboard_authorized(user_id):
        client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text=":no_entry: You don't have permission to use `/onboard` commands."
        )
        return

    if text == "status":
        stats = db.get_onboarding_stats()
        status_blocks = blocks.build_onboard_status_message(stats)
        client.chat_postEphemeral(
            channel=channel_id, user=user_id, blocks=status_blocks,
            text="Onboarding status"
        )

    elif text == "list":
        mappings = db.get_all_committee_channels()
        mapping_blocks = blocks.build_onboard_mapping_list(mappings)
        client.chat_postEphemeral(
            channel=channel_id, user=user_id, blocks=mapping_blocks,
            text="Committee channel mappings"
        )

    elif text.startswith("map "):
        logger.info(f"Onboard map raw text: {repr(text)}")
        _handle_onboard_map(text[4:].strip(), channel_id, user_id, client)

    elif text.startswith("unmap "):
        committee = text[6:].strip().strip('"').strip("'")
        if db.delete_committee_channel(committee):
            client.chat_postEphemeral(
                channel=channel_id, user=user_id,
                text=f":white_check_mark: Removed mapping for *{committee}*."
            )
        else:
            client.chat_postEphemeral(
                channel=channel_id, user=user_id,
                text=f":warning: No mapping found for *{committee}*."
            )

    elif text == "run":
        client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text=":hourglass_flowing_sand: Running registration check now..."
        )
        count = check_new_registrations()
        client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text=f":white_check_mark: Done. Processed {count} new registration(s)."
        )

    elif text == "seed":
        client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text=":hourglass_flowing_sand: Seeding existing members (marking as already onboarded)..."
        )
        count = _seed_existing_members()
        client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text=f":white_check_mark: Seeded {count} existing member(s). No emails will be sent to them."
        )

    elif text.startswith("resend-since "):
        date_str = text[len("resend-since "):].strip()
        try:
            cutoff = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            client.chat_postEphemeral(
                channel=channel_id, user=user_id,
                text=":warning: Invalid date format. Use: `/onboard resend-since 2025-11-01`"
            )
            return

        count = db.unseed_members_since(cutoff)
        client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text=f":white_check_mark: Marked {count} member(s) for re-sending. Run `/onboard run` to send emails now, or wait for the next automatic check."
        )

    elif "@" in text and not text.startswith(("map ", "unmap ")):
        _handle_onboard_send_email(text.strip(), channel_id, user_id, client)

    else:
        client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text=(
                "Usage:\n"
                "  `/onboard status` — show onboarding stats\n"
                "  `/onboard list` — show committee→channel mappings\n"
                "  `/onboard map \"Committee\" #channel` — add a mapping\n"
                "  `/onboard unmap \"Committee\"` — remove a mapping\n"
                "  `/onboard run` — manually check for new registrations\n"
                "  `/onboard seed` — import existing members as already onboarded\n"
                "  `/onboard resend-since 2025-11-01` — re-send emails to seeded members after a date\n"
                "  `/onboard user@example.com` — send welcome email to a specific address\n"
                "  `/onboard admin list` — show onboard admins\n"
                "  `/onboard admin add @user` — add an admin\n"
                "  `/onboard admin remove @user` — remove an admin"
            )
        )


def _resolve_user_id(text: str, client) -> str:
    """Resolve a user reference to a Slack user ID.
    Handles: <@U12345>, <@U12345|name>, @username, or raw username.
    """
    # Try <@U12345> format first
    match = re.search(r'<@(\w+)(?:\|[^>]*)?>', text)
    if match:
        return match.group(1)

    # Extract username (strip leading @)
    username = text.strip().lstrip("@").lower()
    if not username:
        return ""

    # Search through workspace users
    try:
        cursor = None
        while True:
            kwargs = {"limit": 200}
            if cursor:
                kwargs["cursor"] = cursor
            result = client.users_list(**kwargs)
            for member in result.get("members", []):
                if member.get("deleted") or member.get("is_bot"):
                    continue
                name = (member.get("name") or "").lower()
                display = (member.get("profile", {}).get("display_name") or "").lower()
                real = (member.get("real_name") or "").lower()
                if username in (name, display, real):
                    return member["id"]
            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
    except Exception as e:
        logger.error(f"Error looking up user '{username}': {e}")

    return ""


def _handle_onboard_admin(text: str, channel_id: str, user_id: str, client):
    """Handle /onboard admin subcommands."""
    logger.info(f"Onboard admin raw text: {repr(text)}")
    # Only super admin can manage admins (add/remove), but any admin can list
    parts_check = text.split(None, 2)
    sub_check = parts_check[1] if len(parts_check) > 1 else ""
    if sub_check in ("add", "remove") and (not ONBOARD_SUPER_ADMIN or user_id != ONBOARD_SUPER_ADMIN):
        client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text=":no_entry: Only the super admin can add or remove onboard admins."
        )
        return
    if sub_check == "list" and not _is_onboard_authorized(user_id):
        client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text=":no_entry: You don't have permission to use this command."
        )
        return

    parts = text.split(None, 2)  # ["admin"] or ["admin", "list"] or ["admin", "add", "<@U123>"]
    sub = parts[1] if len(parts) > 1 else ""

    if sub == "list":
        admins = db.get_all_onboard_admins()
        if ONBOARD_SUPER_ADMIN:
            lines = [f"Super admin: <@{ONBOARD_SUPER_ADMIN}>"]
        else:
            lines = []
        for uid in admins:
            lines.append(f"<@{uid}>")
        client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text=":busts_in_silhouette: *Onboard Admins:*\n" + "\n".join(lines) if lines else ":warning: No admins configured."
        )

    elif sub == "add" and len(parts) > 2:
        target_id = _resolve_user_id(parts[2], client)
        if not target_id:
            client.chat_postEphemeral(
                channel=channel_id, user=user_id,
                text=":warning: Could not find that user. Usage: `/onboard admin add @user`"
            )
            return
        if db.add_onboard_admin(target_id, user_id):
            client.chat_postEphemeral(
                channel=channel_id, user=user_id,
                text=f":white_check_mark: <@{target_id}> is now an onboard admin."
            )
        else:
            client.chat_postEphemeral(
                channel=channel_id, user=user_id,
                text=f"<@{target_id}> is already an onboard admin."
            )

    elif sub == "remove" and len(parts) > 2:
        target_id = _resolve_user_id(parts[2], client)
        if not target_id:
            client.chat_postEphemeral(
                channel=channel_id, user=user_id,
                text=":warning: Could not find that user. Usage: `/onboard admin remove @user`"
            )
            return
        if target_id == ONBOARD_SUPER_ADMIN:
            client.chat_postEphemeral(
                channel=channel_id, user=user_id,
                text=":warning: Cannot remove the super admin."
            )
            return
        if db.remove_onboard_admin(target_id):
            client.chat_postEphemeral(
                channel=channel_id, user=user_id,
                text=f":white_check_mark: <@{target_id}> is no longer an onboard admin."
            )
        else:
            client.chat_postEphemeral(
                channel=channel_id, user=user_id,
                text=f":warning: <@{target_id}> is not an onboard admin."
            )

    else:
        client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text=(
                "Usage:\n"
                "  `/onboard admin list` — show admins\n"
                "  `/onboard admin add @user` — add an admin\n"
                "  `/onboard admin remove @user` — remove an admin"
            )
        )


def _handle_onboard_map(args: str, channel_id: str, user_id: str, client):
    """Parse and handle /onboard map arguments."""
    # Expected formats:
    #   /onboard map "Journal Club" #journal-club
    #   /onboard map "Journal Club" <#C12345|journal-club>
    match = re.match(r'["\'\u201c\u201d\u2018\u2019](.+?)["\'\u201c\u201d\u2018\u2019]\s+(?:<#(\w+)(?:\|[^>]*)?>|#(\S+))', args)
    if not match:
        client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text='Usage: `/onboard map "Committee Name" #channel`'
        )
        return

    committee = match.group(1)
    resolved_id = match.group(2)  # From Slack-formatted <#ID|name>

    # If we got a channel name (not ID), look it up via API
    if not resolved_id:
        channel_name = match.group(3).lstrip("#")
        resolved_id = _find_channel_id_by_name(client, channel_name)
        if not resolved_id:
            client.chat_postEphemeral(
                channel=channel_id, user=user_id,
                text=f':warning: Could not find channel *#{channel_name}*. Make sure the channel exists and the bot is a member.'
            )
            return

    db.set_committee_channel(committee, resolved_id)
    client.chat_postEphemeral(
        channel=channel_id, user=user_id,
        text=f":white_check_mark: Mapped *{committee}* → <#{resolved_id}>"
    )


def _find_channel_id_by_name(client, channel_name: str) -> str:
    """Look up a channel ID by name using the Slack API."""
    try:
        cursor = None
        while True:
            kwargs = {"types": "public_channel,private_channel", "limit": 200}
            if cursor:
                kwargs["cursor"] = cursor
            result = client.conversations_list(**kwargs)
            for ch in result.get("channels", []):
                if ch["name"] == channel_name:
                    return ch["id"]
            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break
    except Exception as e:
        logger.error(f"Error looking up channel '{channel_name}': {e}")
    return ""


def _handle_onboard_send_email(email: str, channel_id: str, user_id: str, client):
    """Send a welcome email to a single specific address."""
    invite_link = os.getenv("SLACK_INVITE_LINK", "")
    if not invite_link:
        client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text=":warning: `SLACK_INVITE_LINK` is not set in .env"
        )
        return

    member = db.get_member_by_email(email.lower())
    if member:
        first_name = member["first_name"] or ""
        last_name = member["last_name"] or ""
    else:
        first_name = ""
        last_name = ""

    ok = mailer.send_welcome_email(email.lower(), first_name, last_name, invite_link)
    if ok:
        if member:
            db.mark_email_sent(email.lower())
        client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text=f":white_check_mark: Welcome email sent to `{email}`."
        )
    else:
        client.chat_postEphemeral(
            channel=channel_id, user=user_id,
            text=f":x: Failed to send email to `{email}`. Check bot logs for details."
        )


# ============================================================================
# MODAL SUBMISSION HANDLERS
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


@app.view("create_event_modal")
def handle_event_creation(ack, body, client, view, logger):
    """Handle event creation modal submission."""
    values = view["state"]["values"]

    title = values["event_title_block"]["event_title_input"]["value"].strip()
    description = (values["event_description_block"]["event_description_input"].get("value") or "").strip()
    event_date = values["event_date_block"]["event_date_input"].get("selected_date")
    event_time = values["event_time_block"]["event_time_input"].get("selected_time")
    location = (values["event_location_block"]["event_location_input"].get("value") or "").strip()
    max_raw = (values["event_max_block"]["event_max_input"].get("value") or "").strip()

    if not event_date or not event_time:
        ack({
            "response_action": "errors",
            "errors": {"event_date_block": "Date and time are required."}
        })
        return

    # Parse max attendees
    max_attendees = None
    if max_raw:
        try:
            max_attendees = int(max_raw)
            if max_attendees < 1:
                raise ValueError
        except ValueError:
            ack({
                "response_action": "errors",
                "errors": {"event_max_block": "Please enter a valid positive number."}
            })
            return

    ack()

    event_datetime = f"{event_date} {event_time}"
    user_id = body["user"]["id"]
    channel_id = view.get("private_metadata") or user_id

    try:
        event_id = db.create_event(
            title=title,
            description=description,
            location=location,
            event_datetime=event_datetime,
            max_attendees=max_attendees,
            creator_id=user_id,
            channel_id=channel_id
        )

        rsvp_counts = db.get_rsvp_counts(event_id)
        event_blocks = blocks.build_event_message(
            event_id=event_id, title=title, description=description,
            location=location, event_datetime=event_datetime,
            creator_id=user_id, rsvp_counts=rsvp_counts,
            going_users=[], maybe_users=[], not_going_users=[],
            max_attendees=max_attendees, status="open"
        )

        response = client.chat_postMessage(
            channel=channel_id, blocks=event_blocks,
            text=f"New event: {title}"
        )

        db.update_event_message_ts(event_id, response["ts"])
        logger.info(f"Event {event_id} created by {user_id} in {channel_id}")

    except Exception as e:
        logger.error(f"Error creating event: {e}")


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
# EVENT RSVP HANDLERS
# ============================================================================

@app.action(re.compile(r"rsvp_going_\d+"))
def handle_rsvp_going(ack, body, client, logger):
    """Handle Going RSVP button."""
    ack()
    _handle_rsvp(body, client, logger, "going")


@app.action(re.compile(r"rsvp_maybe_\d+"))
def handle_rsvp_maybe(ack, body, client, logger):
    """Handle Maybe RSVP button."""
    ack()
    _handle_rsvp(body, client, logger, "maybe")


@app.action(re.compile(r"rsvp_not_going_\d+"))
def handle_rsvp_not_going(ack, body, client, logger):
    """Handle Not Going RSVP button."""
    ack()
    _handle_rsvp(body, client, logger, "not_going")


def _handle_rsvp(body, client, logger, response: str):
    """Common RSVP handler."""
    action = body["actions"][0]
    event_id = int(action["value"])
    user_id = body["user"]["id"]

    try:
        event = db.get_event(event_id)
        if not event or event["status"] != "open":
            client.chat_postEphemeral(
                channel=body["channel"]["id"], user=user_id,
                text=":lock: This event is no longer accepting RSVPs."
            )
            return

        # Check max attendees for "going"
        if response == "going" and event["max_attendees"]:
            current_rsvp = db.get_user_rsvp(event_id, user_id)
            if current_rsvp != "going":
                counts = db.get_rsvp_counts(event_id)
                if counts["going"] >= event["max_attendees"]:
                    client.chat_postEphemeral(
                        channel=body["channel"]["id"], user=user_id,
                        text=":warning: This event is full! You can join the *Maybe* list instead."
                    )
                    return

        # Toggle: if user clicks same response, remove their RSVP
        current = db.get_user_rsvp(event_id, user_id)
        if current == response:
            # Remove RSVP by setting to not_going (or we could delete, but this is simpler)
            # Actually let's just keep it — clicking same button is a no-op for simplicity
            pass
        else:
            db.set_rsvp(event_id, user_id, response)

        _update_event_message(client, event_id)
        logger.info(f"User {user_id} RSVP'd '{response}' for event {event_id}")

    except Exception as e:
        logger.error(f"Error handling RSVP: {e}")


# ============================================================================
# TEAM JOIN HANDLER (Onboarding)
# ============================================================================

@app.event("team_join")
def handle_member_joined(event, client, logger):
    """Handle new member joining the workspace — auto-assign channels and send welcome DM."""
    user_data = event.get("user", {})
    slack_user_id = user_data.get("id")
    if not slack_user_id:
        return

    try:
        # Get the user's email from their profile
        info = client.users_info(user=slack_user_id)
        email = (info["user"].get("profile", {}).get("email") or "").lower()
        if not email:
            logger.warning(f"No email found for user {slack_user_id}")
            return

        # Look up in processed members
        member = db.get_member_by_email(email)
        if not member:
            logger.info(f"User {slack_user_id} ({email}) not found in processed members — skipping onboarding")
            return

        # Link Slack user ID to member record
        db.set_member_slack_user(email, slack_user_id)

        # Auto-add to committee channels
        committees_raw = member.get("committees", "")
        if committees_raw:
            committee_list = [c.strip() for c in committees_raw.split(",") if c.strip()]
            _assign_committee_channels(client, slack_user_id, committee_list, email, logger)

        # Send welcome DM if configured
        welcome_method = WELCOME_METHOD
        if welcome_method in ("slack_dm", "both"):
            committee_list = [c.strip() for c in committees_raw.split(",") if c.strip()] if committees_raw else []
            _send_welcome_dm(client, slack_user_id, member.get("first_name", ""), committee_list, email, logger)

        # Mark as onboarded
        db.mark_onboarded(email)
        logger.info(f"Onboarded user {slack_user_id} ({email})")

    except Exception as e:
        logger.error(f"Error in team_join handler for {slack_user_id}: {e}")


def _assign_committee_channels(client, slack_user_id: str, committees: list[str],
                                email: str, logger):
    """Add a user to their committee channels using fuzzy matching."""
    all_mappings = db.get_all_committee_channels()
    if not all_mappings:
        return

    assigned_any = False
    for committee in committees:
        channel_id = _find_channel_for_committee(committee, all_mappings)
        if channel_id:
            try:
                client.conversations_invite(channel=channel_id, users=slack_user_id)
                assigned_any = True
                logger.info(f"Added {slack_user_id} to channel {channel_id} for committee '{committee}'")
            except Exception as e:
                error_str = str(e)
                if "already_in_channel" in error_str:
                    assigned_any = True
                else:
                    logger.warning(f"Could not add {slack_user_id} to channel {channel_id}: {e}")
        else:
            logger.warning(f"No channel mapping found for committee '{committee}'")

    if assigned_any:
        db.mark_channels_assigned(email)


def _find_channel_for_committee(committee: str, mappings: list[dict]) -> str:
    """Find a channel ID for a committee name using fuzzy matching."""
    committee_lower = committee.lower().strip()

    # Exact match
    for m in mappings:
        if m["committee_name"].lower() == committee_lower:
            return m["channel_id"]

    # Substring match
    for m in mappings:
        if committee_lower in m["committee_name"].lower() or m["committee_name"].lower() in committee_lower:
            return m["channel_id"]

    return ""


def _send_welcome_dm(client, slack_user_id: str, first_name: str,
                      committees: list[str], email: str, logger):
    """Send a welcome DM to a new member."""
    try:
        dm_blocks = blocks.build_welcome_dm_blocks(first_name or "there", committees)
        client.chat_postMessage(
            channel=slack_user_id,
            blocks=dm_blocks,
            text=f"Welcome to NY-RSG Turkiye, {first_name or 'there'}!"
        )
        db.mark_dm_sent(email)
        logger.info(f"Sent welcome DM to {slack_user_id}")
    except Exception as e:
        logger.error(f"Error sending welcome DM to {slack_user_id}: {e}")


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


def _update_event_message(client, event_id: int):
    """Update an existing event message with current RSVPs."""
    try:
        event = db.get_event(event_id)
        if not event or not event["message_ts"]:
            return

        rsvp_counts = db.get_rsvp_counts(event_id)
        going_users = db.get_rsvp_users(event_id, "going")
        maybe_users = db.get_rsvp_users(event_id, "maybe")
        not_going_users = db.get_rsvp_users(event_id, "not_going")

        event_blocks = blocks.build_event_message(
            event_id=event_id,
            title=event["title"],
            description=event.get("description", ""),
            location=event.get("location", ""),
            event_datetime=event["event_datetime"],
            creator_id=event["creator_id"],
            rsvp_counts=rsvp_counts,
            going_users=going_users,
            maybe_users=maybe_users,
            not_going_users=not_going_users,
            max_attendees=event.get("max_attendees"),
            status=event["status"]
        )

        client.chat_update(
            channel=event["channel_id"],
            ts=event["message_ts"],
            blocks=event_blocks,
            text=f"Event: {event['title']}"
        )

    except Exception as e:
        logger.error(f"Error updating event message: {e}")


def check_expired_polls():
    """Background job to auto-close expired polls."""
    try:
        expired = db.get_expired_polls()
        for poll in expired:
            logger.info(f"Auto-closing expired poll {poll['id']}")
            if db.close_poll(poll["id"]):
                close_and_update_poll(app.client, poll["id"])
    except Exception as e:
        logger.error(f"Error checking expired polls: {e}")


def check_new_registrations() -> int:
    """Check Google Sheet for new registrations and send welcome emails."""
    count = 0
    try:
        registrations = sheets.fetch_registrations()
        invite_link = SLACK_INVITE_LINK
        cutoff = ONBOARD_AFTER_DATE

        for reg in registrations:
            email = reg.get("email", "").lower()
            if not email:
                continue

            # Skip if already processed
            if db.is_member_processed(email):
                continue

            # Skip if before cutoff date
            if cutoff and reg.get("sheet_timestamp"):
                try:
                    ts = datetime.strptime(reg["sheet_timestamp"].split(".")[0], "%m/%d/%Y %H:%M:%S")
                    cutoff_dt = datetime.strptime(cutoff, "%Y-%m-%d")
                    if ts < cutoff_dt:
                        continue
                except (ValueError, TypeError):
                    pass

            # Add to database
            if not db.add_processed_member(reg):
                continue

            count += 1

            # Send welcome email if configured
            welcome = WELCOME_METHOD
            if welcome in ("email", "both") and invite_link:
                success = mailer.send_welcome_email(
                    to_email=email,
                    first_name=reg.get("first_name", ""),
                    last_name=reg.get("last_name", ""),
                    invite_link=invite_link
                )
                if success:
                    db.mark_email_sent(email)

        # Retry failed emails
        pending = db.get_pending_email_members()
        welcome = WELCOME_METHOD
        if welcome in ("email", "both") and invite_link:
            for member in pending:
                if member.get("email_sent") == 0 and count == 0:
                    success = mailer.send_welcome_email(
                        to_email=member["email"],
                        first_name=member.get("first_name", ""),
                        last_name=member.get("last_name", ""),
                        invite_link=invite_link
                    )
                    if success:
                        db.mark_email_sent(member["email"])

    except Exception as e:
        logger.error(f"Error checking new registrations: {e}")

    return count


def _seed_existing_members() -> int:
    """Import all current sheet entries as already onboarded (no emails sent)."""
    count = 0
    try:
        registrations = sheets.fetch_registrations()
        for reg in registrations:
            email = reg.get("email", "").lower()
            if not email:
                continue
            reg["email_sent"] = 1
            reg["onboarded"] = 1
            if db.add_processed_member(reg):
                count += 1
    except Exception as e:
        logger.error(f"Error seeding existing members: {e}")
    return count


def check_event_reminders():
    """Background job to send event reminders (24h and 1h before)."""
    try:
        events = db.get_upcoming_events_for_reminders()
        for event in events:
            event_dt = datetime.fromisoformat(event["event_datetime"])
            now = datetime.now()
            hours_until = (event_dt - now).total_seconds() / 3600

            rsvp_counts = db.get_rsvp_counts(event["id"])

            # Determine which reminder to send
            if not event["reminder_1h_sent"] and hours_until <= 1:
                reminder_type = "1h"
            elif not event["reminder_24h_sent"] and hours_until <= 24:
                reminder_type = "24h"
            else:
                continue

            reminder_blocks = blocks.build_event_reminder_blocks(
                event_id=event["id"],
                title=event["title"],
                event_datetime=event["event_datetime"],
                location=event.get("location", ""),
                rsvp_counts=rsvp_counts,
                reminder_type=reminder_type
            )

            # Send reminder to going and maybe users
            users_to_notify = (
                db.get_rsvp_users(event["id"], "going") +
                db.get_rsvp_users(event["id"], "maybe")
            )

            for user_id in users_to_notify:
                try:
                    app.client.chat_postMessage(
                        channel=user_id,
                        blocks=reminder_blocks,
                        text=f"Reminder: {event['title']} is starting soon!"
                    )
                except Exception as e:
                    logger.warning(f"Could not send reminder to {user_id}: {e}")

            db.mark_reminder_sent(event["id"], reminder_type)
            logger.info(f"Sent {reminder_type} reminder for event {event['id']} to {len(users_to_notify)} users")

    except Exception as e:
        logger.error(f"Error checking event reminders: {e}")


def check_past_events():
    """Background job to auto-close past events."""
    try:
        past = db.get_past_open_events()
        for event in past:
            logger.info(f"Auto-closing past event {event['id']}")
            if db.close_event(event["id"]):
                _update_event_message(app.client, event["id"])
    except Exception as e:
        logger.error(f"Error checking past events: {e}")


# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main function to start the bot."""
    # Initialize database
    db.init_db()
    logger.info("Database initialized")

    # Start scheduler for background jobs
    scheduler.add_job(check_expired_polls, "interval", minutes=1)
    scheduler.add_job(check_new_registrations, "interval", hours=1)
    scheduler.add_job(check_event_reminders, "interval", minutes=5)
    scheduler.add_job(check_past_events, "interval", minutes=10)
    scheduler.start()
    logger.info("Scheduler started (polls, registrations, events)")

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
