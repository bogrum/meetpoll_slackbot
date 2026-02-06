"""
Block Kit UI builders for MeetPoll bot.
Creates interactive Slack message components for polls, events, and onboarding.
"""

from datetime import datetime
from typing import Optional


def build_poll_modal(trigger_id: str = None) -> dict:
    """Build the modal for creating a new poll."""
    return {
        "type": "modal",
        "callback_id": "create_poll_modal",
        "title": {"type": "plain_text", "text": "Create Meeting Poll"},
        "submit": {"type": "plain_text", "text": "Create Poll"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "question_block",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "question_input",
                    "placeholder": {
                        "type": "plain_text",
                        "text": "e.g., When should we have our team standup?"
                    },
                    "max_length": 200
                },
                "label": {"type": "plain_text", "text": "Poll Question"}
            },
            {
                "type": "input",
                "block_id": "options_block",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "options_input",
                    "multiline": True,
                    "placeholder": {
                        "type": "plain_text",
                        "text": "Monday 9:00 AM\nMonday 2:00 PM\nTuesday 10:00 AM\nWednesday 3:00 PM"
                    }
                },
                "label": {"type": "plain_text", "text": "Time Options (one per line, 5-25 options)"},
                "hint": {
                    "type": "plain_text",
                    "text": "Enter each time slot on a new line. Minimum 5, maximum 25 options."
                }
            },
            {
                "type": "input",
                "block_id": "close_date_block",
                "optional": True,
                "element": {
                    "type": "datepicker",
                    "action_id": "close_date_input",
                    "placeholder": {"type": "plain_text", "text": "Select date"}
                },
                "label": {"type": "plain_text", "text": "Close Date (optional)"}
            },
            {
                "type": "input",
                "block_id": "close_time_block",
                "optional": True,
                "element": {
                    "type": "timepicker",
                    "action_id": "close_time_input",
                    "placeholder": {"type": "plain_text", "text": "Select time"}
                },
                "label": {"type": "plain_text", "text": "Close Time (optional)"}
            }
        ]
    }


def build_poll_message(poll_id: int, question: str, creator_id: str,
                       options: list[dict], results: list[dict],
                       closes_at: Optional[datetime], status: str) -> list[dict]:
    """
    Build the poll message with voting checkboxes.

    Args:
        poll_id: The poll database ID
        question: Poll question text
        creator_id: Slack user ID of creator
        options: List of option dicts with id, option_text, option_order
        results: List of result dicts with vote_count, voters
        closes_at: Optional close datetime
        status: 'open' or 'closed'
    """
    blocks = []

    # Header with question
    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": f":calendar: {question}", "emoji": True}
    })

    # Poll info context
    context_elements = [
        {"type": "mrkdwn", "text": f"Created by <@{creator_id}>"}
    ]

    if closes_at:
        close_str = closes_at.strftime("%b %d, %Y at %I:%M %p") if isinstance(closes_at, datetime) else str(closes_at)
        context_elements.append(
            {"type": "mrkdwn", "text": f":clock3: Closes: {close_str}"}
        )

    if status == "closed":
        context_elements.append(
            {"type": "mrkdwn", "text": ":lock: *Poll Closed*"}
        )

    blocks.append({"type": "context", "elements": context_elements})
    blocks.append({"type": "divider"})

    if status == "open":
        # Voting checkboxes for open polls
        # Slack limits checkboxes to 10 options per group, so we split into chunks
        checkbox_options = []
        for opt, res in zip(options, results):
            vote_count = res.get("vote_count", 0)

            # Build option text with vote count
            option_text = f"{opt['option_text']} ({vote_count} vote{'s' if vote_count != 1 else ''})"

            checkbox_options.append({
                "text": {"type": "mrkdwn", "text": option_text},
                "value": str(opt["id"])
            })

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": "*Select your available times:*"}
        })

        # Split options into chunks of 10 (Slack's limit)
        chunk_size = 10
        for i in range(0, len(checkbox_options), chunk_size):
            chunk = checkbox_options[i:i + chunk_size]
            chunk_index = i // chunk_size
            blocks.append({
                "type": "actions",
                "block_id": f"vote_block_{poll_id}_{chunk_index}",
                "elements": [
                    {
                        "type": "checkboxes",
                        "action_id": f"vote_action_{poll_id}_{chunk_index}",
                        "options": chunk
                    }
                ]
            })

    # Action buttons
    blocks.append({"type": "divider"})

    action_elements = [
        {
            "type": "button",
            "text": {"type": "plain_text", "text": ":bar_chart: View Results", "emoji": True},
            "action_id": f"view_results_{poll_id}",
            "value": str(poll_id)
        }
    ]

    if status == "open":
        action_elements.append({
            "type": "button",
            "text": {"type": "plain_text", "text": ":lock: Close Poll", "emoji": True},
            "action_id": f"close_poll_{poll_id}",
            "value": str(poll_id),
            "style": "danger",
            "confirm": {
                "title": {"type": "plain_text", "text": "Close Poll?"},
                "text": {"type": "plain_text", "text": "This will prevent any further voting."},
                "confirm": {"type": "plain_text", "text": "Close"},
                "deny": {"type": "plain_text", "text": "Cancel"}
            }
        })

    blocks.append({
        "type": "actions",
        "block_id": f"poll_actions_{poll_id}",
        "elements": action_elements
    })

    # Footer
    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"Poll ID: {poll_id} | Use `/meetpoll` to create a new poll"}
        ]
    })

    return blocks


def build_results_modal(poll_id: int, question: str, results: list[dict],
                        total_voters: int, status: str) -> dict:
    """Build a modal showing detailed poll results."""
    blocks = []

    # Summary
    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": f"*{question}*\n\nTotal respondents: {total_voters} | Status: {status.upper()}"
        }
    })

    blocks.append({"type": "divider"})

    # Sort results by vote count (descending)
    sorted_results = sorted(results, key=lambda x: x.get("vote_count", 0), reverse=True)

    # Find max votes for highlighting winner
    max_votes = max((r.get("vote_count", 0) for r in sorted_results), default=0)

    for res in sorted_results:
        vote_count = res.get("vote_count", 0)
        voters = res.get("voters", [])
        option_text = res.get("option_text", "Unknown")

        # Highlight top option(s)
        prefix = ":trophy: " if vote_count == max_votes and vote_count > 0 else ""

        # Build vote bar visualization
        bar_length = min(vote_count, 20)
        bar = ":blue_square:" * bar_length if bar_length > 0 else ":white_square:"

        if voters:
            voter_mentions = ", ".join([f"<@{v}>" for v in voters])
            text = f"{prefix}*{option_text}*\n{bar} {vote_count}\n_{voter_mentions}_"
        else:
            text = f"{prefix}*{option_text}*\n{bar} {vote_count}\n_No votes_"

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": text}
        })

    return {
        "type": "modal",
        "title": {"type": "plain_text", "text": "Poll Results"},
        "close": {"type": "plain_text", "text": "Close"},
        "blocks": blocks
    }


def build_closed_poll_message(poll_id: int, question: str, creator_id: str,
                              results: list[dict], total_voters: int) -> list[dict]:
    """Build the final results message for a closed poll."""
    blocks = []

    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": f":ballot_box: Poll Closed: {question}", "emoji": True}
    })

    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"Created by <@{creator_id}> | {total_voters} respondent{'s' if total_voters != 1 else ''}"}
        ]
    })

    blocks.append({"type": "divider"})

    # Sort by votes
    sorted_results = sorted(results, key=lambda x: x.get("vote_count", 0), reverse=True)
    max_votes = max((r.get("vote_count", 0) for r in sorted_results), default=0)

    # Show winner(s) first
    if max_votes > 0:
        winners = [r for r in sorted_results if r.get("vote_count", 0) == max_votes]
        if len(winners) == 1:
            winner = winners[0]
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":trophy: *Winner: {winner['option_text']}* with {max_votes} vote{'s' if max_votes != 1 else ''}"
                }
            })
        else:
            winner_texts = ", ".join([w["option_text"] for w in winners])
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f":trophy: *Tie: {winner_texts}* with {max_votes} vote{'s' if max_votes != 1 else ''} each"
                }
            })

    blocks.append({"type": "divider"})
    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": "*All Results:*"}
    })

    for res in sorted_results:
        vote_count = res.get("vote_count", 0)
        voters = res.get("voters", [])
        option_text = res.get("option_text", "Unknown")

        prefix = ":first_place_medal: " if vote_count == max_votes and vote_count > 0 else ""

        if voters:
            voter_mentions = ", ".join([f"<@{v}>" for v in voters])
            text = f"{prefix}*{option_text}* ({vote_count})\n{voter_mentions}"
        else:
            text = f"*{option_text}* (0)"

        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": text}
        })

    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"Poll ID: {poll_id} | :lock: This poll is closed"}
        ]
    })

    return blocks


def build_error_message(error: str) -> list[dict]:
    """Build an error message block."""
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":warning: *Error:* {error}"
            }
        }
    ]


# ============================================================================
# ONBOARDING BLOCK BUILDERS
# ============================================================================

def build_welcome_dm_blocks(first_name: str, committees: list[str]) -> list[dict]:
    """Build Slack DM welcome message blocks for a new member."""
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ":wave: Welcome to NY-RSG Turkiye!", "emoji": True}
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"Hi {first_name}! Welcome to our Slack workspace. We're glad you're here!"
            }
        },
        {"type": "divider"},
    ]

    if committees:
        committee_list = "\n".join([f"  - {c}" for c in committees])
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f":clipboard: *Your committees:*\n{committee_list}\n\nYou've been automatically added to the corresponding channels."
            }
        })
    else:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Feel free to explore the channels and join any that interest you!"
            }
        })

    blocks.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": "If you have any questions, don't hesitate to ask. Enjoy!"
        }
    })

    return blocks


def build_onboard_status_message(stats: dict) -> list[dict]:
    """Build the /onboard status response."""
    total = stats.get("total", 0)
    emails_sent = stats.get("emails_sent", 0)
    joined = stats.get("joined_slack", 0)
    assigned = stats.get("channels_assigned", 0)
    dms = stats.get("dms_sent", 0)
    onboarded = stats.get("fully_onboarded", 0)

    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ":clipboard: Onboarding Status", "emoji": True}
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Total processed:* {total}\n"
                    f"*Emails sent:* {emails_sent}\n"
                    f"*Joined Slack:* {joined}\n"
                    f"*Channels assigned:* {assigned}\n"
                    f"*DMs sent:* {dms}\n"
                    f"*Fully onboarded:* {onboarded}"
                )
            }
        }
    ]


def build_onboard_mapping_list(mappings: list[dict]) -> list[dict]:
    """Build the /onboard list response showing committee→channel mappings."""
    if not mappings:
        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "No committee→channel mappings configured yet.\nUse `/onboard map \"Committee Name\" #channel` to add one."
                }
            }
        ]

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ":link: Committee Channel Mappings", "emoji": True}
        }
    ]

    lines = []
    for m in mappings:
        lines.append(f"  *{m['committee_name']}* → <#{m['channel_id']}>")

    blocks.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": "\n".join(lines)}
    })

    return blocks


# ============================================================================
# EVENT BLOCK BUILDERS
# ============================================================================

def build_event_modal() -> dict:
    """Build the modal for creating a new event."""
    return {
        "type": "modal",
        "callback_id": "create_event_modal",
        "title": {"type": "plain_text", "text": "Create Event"},
        "submit": {"type": "plain_text", "text": "Create Event"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "event_title_block",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "event_title_input",
                    "placeholder": {"type": "plain_text", "text": "e.g., Monthly Team Meetup"},
                    "max_length": 150
                },
                "label": {"type": "plain_text", "text": "Event Title"}
            },
            {
                "type": "input",
                "block_id": "event_description_block",
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "event_description_input",
                    "multiline": True,
                    "placeholder": {"type": "plain_text", "text": "Describe the event..."}
                },
                "label": {"type": "plain_text", "text": "Description"}
            },
            {
                "type": "input",
                "block_id": "event_date_block",
                "element": {
                    "type": "datepicker",
                    "action_id": "event_date_input",
                    "placeholder": {"type": "plain_text", "text": "Select date"}
                },
                "label": {"type": "plain_text", "text": "Event Date"}
            },
            {
                "type": "input",
                "block_id": "event_time_block",
                "element": {
                    "type": "timepicker",
                    "action_id": "event_time_input",
                    "placeholder": {"type": "plain_text", "text": "Select time"}
                },
                "label": {"type": "plain_text", "text": "Event Time"}
            },
            {
                "type": "input",
                "block_id": "event_location_block",
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "event_location_input",
                    "placeholder": {"type": "plain_text", "text": "e.g., Zoom link or office address"}
                },
                "label": {"type": "plain_text", "text": "Location"}
            },
            {
                "type": "input",
                "block_id": "event_max_block",
                "optional": True,
                "element": {
                    "type": "plain_text_input",
                    "action_id": "event_max_input",
                    "placeholder": {"type": "plain_text", "text": "Leave empty for unlimited"}
                },
                "label": {"type": "plain_text", "text": "Max Attendees (optional)"},
                "hint": {"type": "plain_text", "text": "Enter a number or leave empty for no limit."}
            }
        ]
    }


def build_event_message(event_id: int, title: str, description: str,
                         location: str, event_datetime: str,
                         creator_id: str, rsvp_counts: dict,
                         going_users: list[str], maybe_users: list[str],
                         not_going_users: list[str],
                         max_attendees: Optional[int] = None,
                         status: str = "open") -> list[dict]:
    """Build the event message with RSVP buttons."""
    blocks = []

    # Header
    blocks.append({
        "type": "header",
        "text": {"type": "plain_text", "text": f":calendar: {title}", "emoji": True}
    })

    # Event details context
    context_parts = [{"type": "mrkdwn", "text": f"Created by <@{creator_id}>"}]

    if event_datetime:
        try:
            dt = datetime.fromisoformat(event_datetime)
            dt_str = dt.strftime("%b %d, %Y at %I:%M %p")
        except (ValueError, TypeError):
            dt_str = str(event_datetime)
        context_parts.append({"type": "mrkdwn", "text": f":clock3: {dt_str}"})

    if location:
        context_parts.append({"type": "mrkdwn", "text": f":round_pushpin: {location}"})

    if status != "open":
        context_parts.append({"type": "mrkdwn", "text": f":lock: *Event {status.title()}*"})

    blocks.append({"type": "context", "elements": context_parts})

    if description:
        blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": description}})

    blocks.append({"type": "divider"})

    # RSVP counts
    going_count = rsvp_counts.get("going", 0)
    maybe_count = rsvp_counts.get("maybe", 0)
    not_going_count = rsvp_counts.get("not_going", 0)

    capacity_text = ""
    if max_attendees:
        capacity_text = f" / {max_attendees}"
    is_full = max_attendees and going_count >= max_attendees

    # RSVP summary section
    going_text = f":white_check_mark: *Going ({going_count}{capacity_text})*"
    if is_full:
        going_text += " (FULL)"
    if going_users:
        going_text += "\n" + ", ".join([f"<@{u}>" for u in going_users])

    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": going_text}})

    maybe_text = f":thinking_face: *Maybe ({maybe_count})*"
    if maybe_users:
        maybe_text += "\n" + ", ".join([f"<@{u}>" for u in maybe_users])

    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": maybe_text}})

    not_going_text = f":x: *Not Going ({not_going_count})*"
    if not_going_users:
        not_going_text += "\n" + ", ".join([f"<@{u}>" for u in not_going_users])

    blocks.append({"type": "section", "text": {"type": "mrkdwn", "text": not_going_text}})

    # RSVP buttons (only for open events)
    if status == "open":
        blocks.append({"type": "divider"})

        going_button_text = ":white_check_mark: Going"
        if is_full:
            going_button_text = ":white_check_mark: Going (FULL)"

        blocks.append({
            "type": "actions",
            "block_id": f"event_rsvp_{event_id}",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": going_button_text, "emoji": True},
                    "action_id": f"rsvp_going_{event_id}",
                    "value": str(event_id),
                    "style": "primary"
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": ":thinking_face: Maybe", "emoji": True},
                    "action_id": f"rsvp_maybe_{event_id}",
                    "value": str(event_id)
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": ":x: Not Going", "emoji": True},
                    "action_id": f"rsvp_not_going_{event_id}",
                    "value": str(event_id),
                    "style": "danger"
                }
            ]
        })

    # Footer
    blocks.append({
        "type": "context",
        "elements": [
            {"type": "mrkdwn", "text": f"Event ID: {event_id} | Use `/event create` to create a new event"}
        ]
    })

    return blocks


def build_event_reminder_blocks(event_id: int, title: str,
                                 event_datetime: str, location: str,
                                 rsvp_counts: dict,
                                 reminder_type: str) -> list[dict]:
    """Build event reminder message blocks."""
    if reminder_type == "24h":
        time_text = "in 24 hours"
    else:
        time_text = "in 1 hour"

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f":bell: Event Reminder", "emoji": True}
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*{title}* is starting {time_text}!"
            }
        }
    ]

    details = []
    if event_datetime:
        try:
            dt = datetime.fromisoformat(event_datetime)
            details.append(f":clock3: {dt.strftime('%b %d, %Y at %I:%M %p')}")
        except (ValueError, TypeError):
            details.append(f":clock3: {event_datetime}")
    if location:
        details.append(f":round_pushpin: {location}")

    going = rsvp_counts.get("going", 0)
    maybe = rsvp_counts.get("maybe", 0)
    details.append(f":white_check_mark: {going} going | :thinking_face: {maybe} maybe")

    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": " | ".join(details)}]
    })

    return blocks


def build_event_closed_message(event_id: int, title: str, description: str,
                                location: str, event_datetime: str,
                                creator_id: str, rsvp_counts: dict,
                                going_users: list[str], maybe_users: list[str],
                                not_going_users: list[str],
                                max_attendees: Optional[int] = None) -> list[dict]:
    """Build the final summary message for a closed/past event."""
    return build_event_message(
        event_id=event_id,
        title=title,
        description=description,
        location=location,
        event_datetime=event_datetime,
        creator_id=creator_id,
        rsvp_counts=rsvp_counts,
        going_users=going_users,
        maybe_users=maybe_users,
        not_going_users=not_going_users,
        max_attendees=max_attendees,
        status="closed"
    )
