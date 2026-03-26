"""
Block Kit UI builders for MeetPoll bot.
Creates interactive Slack message components for polls, events, onboarding,
analytics, and engagement features.
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
            },
            {
                "type": "input",
                "block_id": "anonymous_block",
                "optional": True,
                "element": {
                    "type": "checkboxes",
                    "action_id": "anonymous_input",
                    "options": [
                        {
                            "text": {"type": "plain_text", "text": "Make poll anonymous (voter names hidden)"},
                            "value": "anonymous"
                        }
                    ]
                },
                "label": {"type": "plain_text", "text": "Privacy"}
            }
        ]
    }


def build_poll_message(poll_id: int, question: str, creator_id: str,
                       options: list[dict], results: list[dict],
                       closes_at: Optional[datetime], status: str,
                       anonymous: bool = False) -> list[dict]:
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
        anonymous: If True, hide voter names in results
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

    if anonymous:
        context_elements.append(
            {"type": "mrkdwn", "text": ":detective: *Anonymous Poll*"}
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
                        total_voters: int, status: str,
                        anonymous: bool = False) -> dict:
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

        if anonymous:
            text = f"{prefix}*{option_text}*\n{bar} {vote_count}"
        elif voters:
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
                              results: list[dict], total_voters: int,
                              anonymous: bool = False) -> list[dict]:
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

        if voters and not anonymous:
            voter_mentions = ", ".join([f"<@{v}>" for v in voters])
            text = f"{prefix}*{option_text}* ({vote_count})\n{voter_mentions}"
        else:
            text = f"{prefix}*{option_text}* ({vote_count})"

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

def build_welcome_dm_blocks(first_name: str,
                             committees_with_channels: list[dict],
                             membership_choice: str,
                             upcoming_events: list[dict],
                             general_channel_id: str = "") -> list[dict]:
    """Build Slack DM welcome message blocks for a new member.

    Args:
        first_name: Member's first name
        committees_with_channels: List of {"name": str, "channel_id": str|None}
        membership_choice: Raw membership choice string from form (active or passive)
        upcoming_events: List of upcoming event dicts from DB
        general_channel_id: Optional Slack channel ID for #general mentions
    """
    is_active = "aktif" in membership_choice.lower() or "active" in membership_choice.lower()

    result = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ":tada: RSG-Türkiye'ye Hoş Geldiniz! / Welcome!", "emoji": True}
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"Merhaba{' ' + first_name if first_name else ''}! Topluluğumuza katıldığın için çok mutluyuz.\n"
                    f"Hi{' ' + first_name if first_name else ''}! We're so glad you joined our community."
                )
            }
        },
        {"type": "divider"},
    ]

    if is_active and committees_with_channels:
        lines = []
        for c in committees_with_channels:
            if c.get("channel_id"):
                lines.append(f"• {c['name']} → <#{c['channel_id']}>")
            else:
                lines.append(f"• {c['name']}")
        result.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    ":clipboard: *Komiteleriniz / Your committees:*\n"
                    + "\n".join(lines) + "\n\n"
                    "Komite kanallarına gidip kendinizi kısaca tanıtabilirsiniz — sizi bekliyoruz! :wave:\n"
                    "Head over to your committee channels and say hi — we're waiting for you!"
                )
            }
        })
    elif is_active:
        result.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    ":clipboard: Aktif üye olarak komite kanallarını keşfedebilir, "
                    "istediğin birine katılabilirsin.\n"
                    "As an active member, feel free to explore the committee channels "
                    "and join whichever interests you."
                )
            }
        })
    else:
        general_mention = f"<#{general_channel_id}>" if general_channel_id else "#general"
        result.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    ":eyes: Pasif üye olarak etkinlikleri takip edebilir, ilgini çekenlere "
                    "katılabilirsin — herhangi bir organizasyon sorumluluğun yok.\n"
                    "As a passive member, you can follow along and join any events that "
                    "interest you — no pressure to organize anything.\n\n"
                    f":pushpin: Tüm duyurular {general_mention} kanalından paylaşılıyor, takipte kal!\n"
                    f"All announcements go through {general_mention} — keep an eye on it!"
                )
            }
        })

    if upcoming_events:
        event_lines = []
        for e in upcoming_events[:2]:
            dt = (e.get("event_datetime") or "")[:16]
            event_lines.append(f"• *{e['title']}* — {dt}")
        result.append({"type": "divider"})
        result.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    ":calendar: *Yaklaşan Etkinlikler / Upcoming Events:*\n"
                    + "\n".join(event_lines)
                )
            }
        })

    general_ref = f"<#{general_channel_id}>" if general_channel_id else "#general"
    result.append({"type": "divider"})
    result.append({
        "type": "section",
        "text": {
            "type": "mrkdwn",
            "text": (
                ":compass: *Topluluk Kanalları / Community Channels:*\n"
                f"• {general_ref} — Duyurular / Announcements\n"
                "• #chit_chat-geyik — Sohbet, gündelik konuşmalar / Casual chat\n"
                "• #jobs_internship — İş & staj ilanları, paylaşabilirsin de / Jobs & internships, feel free to share\n"
                "• #networking — Bağlantı kur, tanış / Connect with others\n"
                "• #scientific_events — Bilimsel etkinlikler / Scientific events\n"
                "• #help_discussion — Akademik destek & sorular / Academic help & questions\n"
                "• #articles__resources — Makale & kaynak paylaşımı / Articles & resources"
            )
        }
    })

    result.append({"type": "divider"})
    result.append({
        "type": "context",
        "elements": [{
            "type": "mrkdwn",
            "text": (
                "Herhangi bir sorun olursa bu DM üzerinden bize ulaşabilirsin. :slightly_smiling_face:\n"
                "Feel free to reach out here anytime. — *RSG-Türkiye*"
            )
        }]
    })

    return result


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
        leader = m.get("leader_user_id")
        leader_str = f" · leader: <@{leader}>" if leader else ""
        lines.append(f"  *{m['committee_name']}* → <#{m['channel_id']}>{leader_str}")

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


# ============================================================================
# OUTREACH BLOCK BUILDERS
# ============================================================================

def build_outreach_compose_modal(audience_type: str) -> dict:
    """Build the modal for composing an outreach email campaign."""
    if audience_type == "academics":
        greeting_hint = "Auto-greeting: \"Say\u0131n {Ad Soyad} Hocam,\""
    else:
        greeting_hint = "Auto-greeting: \"Sevgili {Kul\u00fcp Ad\u0131},\""

    return {
        "type": "modal",
        "callback_id": "outreach_compose_modal",
        "title": {"type": "plain_text", "text": "Compose Outreach"},
        "submit": {"type": "plain_text", "text": "Preview"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "private_metadata": "",
        "blocks": [
            {
                "type": "input",
                "block_id": "audience_block",
                "element": {
                    "type": "static_select",
                    "action_id": "audience_select",
                    "initial_option": {
                        "text": {"type": "plain_text", "text": "Academics" if audience_type == "academics" else "Clubs"},
                        "value": audience_type
                    },
                    "options": [
                        {
                            "text": {"type": "plain_text", "text": "Academics"},
                            "value": "academics"
                        },
                        {
                            "text": {"type": "plain_text", "text": "Clubs"},
                            "value": "clubs"
                        }
                    ]
                },
                "label": {"type": "plain_text", "text": "Audience"}
            },
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f":envelope: {greeting_hint}"}
                ]
            },
            {
                "type": "input",
                "block_id": "subject_block",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "subject_input",
                    "placeholder": {"type": "plain_text", "text": "Email subject line"},
                    "max_length": 200
                },
                "label": {"type": "plain_text", "text": "Subject"}
            },
            {
                "type": "input",
                "block_id": "body_block",
                "element": {
                    "type": "plain_text_input",
                    "action_id": "body_input",
                    "multiline": True,
                    "placeholder": {"type": "plain_text", "text": "Email body (greeting is auto-prepended)"},
                    "max_length": 3000
                },
                "label": {"type": "plain_text", "text": "Body"}
            }
        ]
    }


def build_outreach_preview_blocks(campaign_id: int, audience_type: str,
                                   subject: str, samples: list[dict],
                                   total: int) -> list[dict]:
    """Build ephemeral preview blocks with sample emails and confirm/cancel buttons."""
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ":email: Outreach Preview", "emoji": True}
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"*Audience:* {audience_type.title()} | *Recipients:* {total} | *Subject:* {subject}"}
            ]
        },
        {"type": "divider"}
    ]

    if total > 450:
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": ":warning: *Warning:* More than 450 recipients. Gmail's daily send limit is ~500. The campaign may not complete in one day."
            }
        })
        blocks.append({"type": "divider"})

    # Show sample emails
    for i, sample in enumerate(samples[:3], 1):
        preview_body = sample.get("body_preview", "")
        if len(preview_body) > 200:
            preview_body = preview_body[:200] + "..."
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Sample {i}:* `{sample['email']}`\n>{sample['greeting']}\n>{preview_body}"
            }
        })

    blocks.append({"type": "divider"})

    blocks.append({
        "type": "actions",
        "block_id": f"outreach_actions_{campaign_id}",
        "elements": [
            {
                "type": "button",
                "text": {"type": "plain_text", "text": ":white_check_mark: Confirm Send", "emoji": True},
                "action_id": f"outreach_confirm_{campaign_id}",
                "value": str(campaign_id),
                "style": "primary"
            },
            {
                "type": "button",
                "text": {"type": "plain_text", "text": ":x: Cancel", "emoji": True},
                "action_id": f"outreach_cancel_{campaign_id}",
                "value": str(campaign_id),
                "style": "danger"
            }
        ]
    })

    return blocks


def build_outreach_status_blocks(stats: dict) -> list[dict]:
    """Build outreach statistics display."""
    total = stats.get("total_campaigns", 0) or 0
    completed = stats.get("completed", 0) or 0
    in_progress = stats.get("in_progress", 0) or 0
    cancelled = stats.get("cancelled", 0) or 0
    total_sent = stats.get("total_sent", 0) or 0
    total_failed = stats.get("total_failed", 0) or 0

    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ":bar_chart: Outreach Statistics", "emoji": True}
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*Total campaigns:* {total}\n"
                    f"*Completed:* {completed}\n"
                    f"*In progress:* {in_progress}\n"
                    f"*Cancelled:* {cancelled}\n"
                    f"*Total emails sent:* {total_sent}\n"
                    f"*Total failures:* {total_failed}"
                )
            }
        }
    ]


def build_outreach_history_blocks(campaigns: list[dict]) -> list[dict]:
    """Build recent outreach campaigns list."""
    if not campaigns:
        return [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "No outreach campaigns yet. Use `/outreach academics` or `/outreach clubs` to start one."}
            }
        ]

    status_emoji = {
        "draft": ":pencil2:",
        "sending": ":hourglass_flowing_sand:",
        "completed": ":white_check_mark:",
        "failed": ":x:",
        "cancelled": ":no_entry_sign:"
    }

    result_blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ":scroll: Recent Outreach Campaigns", "emoji": True}
        }
    ]

    for c in campaigns:
        emoji = status_emoji.get(c["status"], ":question:")
        created = c.get("created_at", "")[:16] if c.get("created_at") else "?"
        result_blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"{emoji} *#{c['id']}* — {c['subject']}\n"
                    f"_{c['audience_type'].title()}_ | "
                    f"{c['sent_count']}/{c['total_recipients']} sent | "
                    f"{c['status']} | {created}"
                )
            },
            "accessory": {
                "type": "button",
                "text": {"type": "plain_text", "text": "Details", "emoji": True},
                "action_id": f"outreach_details_{c['id']}",
                "value": str(c["id"])
            }
        })

    return result_blocks


def build_outreach_detail_blocks(campaign: dict, recipients: list[dict]) -> list[dict]:
    """Build detailed view of a single outreach campaign."""
    status_emoji = {
        "draft": ":pencil2:",
        "sending": ":hourglass_flowing_sand:",
        "completed": ":white_check_mark:",
        "failed": ":x:",
        "cancelled": ":no_entry_sign:"
    }

    emoji = status_emoji.get(campaign["status"], ":question:")
    created = campaign.get("created_at", "")[:16] if campaign.get("created_at") else "?"

    result_blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{campaign['subject']}", "emoji": True}
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": (
                    f"{emoji} {campaign['status'].title()} | "
                    f"_{campaign['audience_type'].title()}_ | "
                    f"Sent by <@{campaign['sender_user_id']}> | {created}"
                )}
            ]
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Email body:*\n>>>{campaign['body']}"
            }
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*Recipients ({campaign['sent_count']}/{campaign['total_recipients']} sent, {campaign['failed_count']} failed):*"
            }
        }
    ]

    recipient_emoji = {"sent": ":white_check_mark:", "failed": ":x:", "pending": ":hourglass:"}

    # Show recipients in batches to stay under Slack's block limit
    lines = []
    for r in recipients:
        r_emoji = recipient_emoji.get(r["status"], ":question:")
        line = f"{r_emoji} {r['name']} — `{r['email']}`"
        if r.get("error_message"):
            line += f" — _{r['error_message']}_"
        lines.append(line)

    # Slack limits section text to 3000 chars, split if needed
    chunk = ""
    for line in lines:
        if len(chunk) + len(line) + 1 > 2900:
            result_blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": chunk}
            })
            chunk = ""
        chunk += line + "\n"

    if chunk:
        result_blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": chunk}
        })

    return result_blocks


# ============================================================================
# HELP — Phase 3
# ============================================================================

def build_help_blocks() -> list[dict]:
    """Build a help message listing all available bot commands."""
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ":robot_face: MeetPoll Bot — Commands", "emoji": True}
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*:calendar: Polls & Events*\n"
                    "• `/meetpoll` — Create a new meeting poll\n"
                    "• `/event` — Create a new event with RSVPs\n"
                    "• `/mypolls` — View your active polls\n"
                    "• `/myevents` — View your active events"
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*:busts_in_silhouette: Onboarding*\n"
                    "• `/onboard status` — Check onboarding status\n"
                    "• `/onboard run` — Manually trigger onboarding\n"
                    "• `/onboard mappings` — View committee channel mappings"
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*:email: Outreach*\n"
                    "• `/outreach academics` — Email outreach to academics\n"
                    "• `/outreach clubs` — Email outreach to clubs\n"
                    "• `/outreach status` — View outreach statistics\n"
                    "• `/outreach history` — View past campaigns"
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*:chart_with_upwards_trend: Analytics & Engagement*\n"
                    "• `/analytics` — View community analytics\n"
                    "• `/engage stats` — Engagement breakdown\n"
                    "• `/engage inactive` — List inactive members\n"
                    "• `/engage nudge` — Send re-engagement nudges\n"
                    "• `/engage digest` — Trigger weekly digest"
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*:wrench: Admin*\n"
                    "• `/status` — Bot health check\n"
                    "• `/help` — Show this help message"
                )
            }
        },
    ]


# ============================================================================
# STATUS — Phase 4
# ============================================================================

def build_status_blocks(uptime: str, db_size: str, db_stats: dict,
                        scheduler_jobs: int, pending_queue: int) -> list[dict]:
    """Build a health check status message."""
    stats_lines = "\n".join([f"• `{table}`: {count}" for table, count in db_stats.items()])
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ":heartbeat: Bot Health Check", "emoji": True}
        },
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Uptime:*\n{uptime}"},
                {"type": "mrkdwn", "text": f"*Database:*\n{db_size}"},
                {"type": "mrkdwn", "text": f"*Scheduler Jobs:*\n{scheduler_jobs}"},
                {"type": "mrkdwn", "text": f"*Pending Opportunities:*\n{pending_queue}"},
            ]
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Table Row Counts:*\n{stats_lines}"}
        }
    ]


# ============================================================================
# ANALYTICS — Phase 5
# ============================================================================

def build_analytics_blocks(poll_stats: dict, event_stats: dict,
                           onboarding: dict) -> list[dict]:
    """Build the analytics dashboard display."""
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ":bar_chart: Community Analytics", "emoji": True}
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    ":ballot_box: *Polls*\n"
                    f"• Total: {poll_stats.get('total_polls', 0)} ({poll_stats.get('open_polls', 0)} open)\n"
                    f"• Total votes: {poll_stats.get('total_votes', 0)}\n"
                    f"• Unique voters: {poll_stats.get('unique_voters', 0)}\n"
                    f"• Avg votes/poll: {poll_stats.get('avg_votes_per_poll', 0)}"
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    ":date: *Events*\n"
                    f"• Total: {event_stats.get('total_events', 0)} ({event_stats.get('upcoming_events', 0)} upcoming)\n"
                    f"• Total RSVPs: {event_stats.get('total_rsvps', 0)}\n"
                    f"• Going RSVPs: {event_stats.get('total_going', 0)}\n"
                    f"• Avg RSVPs/event: {event_stats.get('avg_rsvps_per_event', 0)}"
                )
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    ":wave: *Onboarding*\n"
                    f"• This month: {onboarding.get('this_month', 0)}\n"
                    f"• Last month: {onboarding.get('last_month', 0)}\n"
                    f"• Emails sent → Joined Slack: {onboarding.get('emails_sent', 0)} → {onboarding.get('joined_slack', 0)}\n"
                    f"• Conversion rate: {onboarding.get('conversion_rate', 0)}%"
                )
            }
        }
    ]


# ============================================================================
# ENGAGEMENT — Phase 6
# ============================================================================

def build_engagement_stats_blocks(stats: dict) -> list[dict]:
    """Build engagement statistics for admin view."""
    total = stats.get("total_tracked", 0)
    total_slack = stats.get("total_slack", 0)
    active = stats.get("active_7d", 0)
    semi = stats.get("semi_active_30d", 0)
    inactive = stats.get("inactive_30d", 0)
    never = stats.get("never_tracked", 0)

    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ":people_holding_hands: Engagement Dashboard", "emoji": True}
        },
        {"type": "divider"},
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*:green_circle: Active (7d):*\n{active}"},
                {"type": "mrkdwn", "text": f"*:yellow_circle: Semi-active (7-30d):*\n{semi}"},
                {"type": "mrkdwn", "text": f"*:red_circle: Inactive / Never engaged:*\n{inactive}"},
            ]
        },
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"Total Slack members: {total_slack} — {never} have never interacted with the bot"}
            ]
        }
    ]


def build_inactive_users_blocks(users: list[dict]) -> list[dict]:
    """Build a list of inactive users for admin view."""
    if not users:
        return [{
            "type": "section",
            "text": {"type": "mrkdwn", "text": ":tada: No inactive users! Everyone has been active in the last 30 days."}
        }]

    result = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ":zzz: Inactive Members (30+ days)", "emoji": True}
        },
        {"type": "divider"}
    ]

    lines = []
    for u in users[:20]:  # Cap at 20 to stay under Slack limits
        raw_last_seen = u.get("last_seen")
        last_seen = raw_last_seen[:10] if raw_last_seen else "never"
        first_name = u.get("first_name") or ""
        display = f"{first_name} (<@{u['user_id']}>)" if first_name else f"<@{u['user_id']}>"
        lines.append(f"• {display} — last seen: _{last_seen}_")

    result.append({
        "type": "section",
        "text": {"type": "mrkdwn", "text": "\n".join(lines)}
    })

    if len(users) > 20:
        result.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"_...and {len(users) - 20} more_"}]
        })

    return result


def build_review_card(member: dict, score: float, message_text: str, index: int) -> list[dict]:
    """Build an admin review card for a nudge candidate."""
    user_id = member.get("user_id") or member.get("slack_user_id", "")
    full_name = member.get("full_name") or (
        f"{member.get('first_name', '')} {member.get('last_name', '')}".strip()
    ) or f"<@{user_id}>"
    education = member.get("education_level") or member.get("education") or "—"
    membership = member.get("membership_choice") or "—"
    committees = member.get("committees") or "—"
    preview = message_text[:300] + ("…" if len(message_text) > 300 else "")

    mention = f"<@{user_id}>" if user_id else full_name

    return [
        {"type": "divider"},
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"*#{index} — {full_name}* ({mention})\n"
                    f"Score: `{score}` | Education: _{education}_ | Membership: _{membership}_\n"
                    f"Committees: _{committees}_"
                )
            }
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"```{preview}```"}
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Send", "emoji": True},
                    "style": "primary",
                    "action_id": f"nudge_send_{user_id}",
                    "value": message_text,
                    "confirm": {
                        "title": {"type": "plain_text", "text": "Send this nudge?"},
                        "text": {"type": "mrkdwn", "text": f"This will DM *{full_name}* the draft message."},
                        "confirm": {"type": "plain_text", "text": "Send"},
                        "deny": {"type": "plain_text", "text": "Cancel"},
                    }
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Edit & Send", "emoji": True},
                    "action_id": f"nudge_edit_{user_id}",
                    "value": message_text,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Skip 30d", "emoji": True},
                    "action_id": f"nudge_skip_{user_id}",
                    "value": user_id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "Dismiss", "emoji": True},
                    "style": "danger",
                    "action_id": f"nudge_dismiss_{user_id}",
                    "value": user_id,
                    "confirm": {
                        "title": {"type": "plain_text", "text": "Dismiss permanently?"},
                        "text": {"type": "mrkdwn", "text": f"*{full_name}* will never be suggested again."},
                        "confirm": {"type": "plain_text", "text": "Dismiss"},
                        "deny": {"type": "plain_text", "text": "Cancel"},
                    }
                },
            ]
        }
    ]


def build_review_card_sent(full_name: str) -> list[dict]:
    return [
        {"type": "divider"},
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f":white_check_mark: Nudge sent to *{full_name}*."}]
        }
    ]


def build_review_card_skipped(full_name: str, days: int = 30) -> list[dict]:
    return [
        {"type": "divider"},
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f":next_track_button: Skipped *{full_name}* for {days} days."}]
        }
    ]


def build_review_card_dismissed(full_name: str) -> list[dict]:
    return [
        {"type": "divider"},
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f":wastebasket: Dismissed *{full_name}* permanently."}]
        }
    ]


def build_nudge_edit_modal(user_id: str, full_name: str, message_text: str) -> dict:
    """Modal for editing a nudge message before sending."""
    return {
        "type": "modal",
        "callback_id": f"nudge_edit_submit_{user_id}",
        "private_metadata": user_id,
        "title": {"type": "plain_text", "text": "Edit Nudge Message"},
        "submit": {"type": "plain_text", "text": "Send"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"Editing message for *{full_name}*"}
            },
            {
                "type": "input",
                "block_id": "nudge_message_block",
                "label": {"type": "plain_text", "text": "Message"},
                "element": {
                    "type": "plain_text_input",
                    "action_id": "nudge_message_input",
                    "multiline": True,
                    "initial_value": message_text,
                }
            }
        ]
    }


def build_weekly_digest_blocks(data: dict) -> list[dict]:
    """Build the weekly community digest message."""
    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": ":newspaper: Weekly Community Digest", "emoji": True}
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f":busts_in_silhouette: *{data.get('total_members', 0)}* total members | *{data.get('new_members', 0)}* joined this week"}]
        },
        {"type": "divider"}
    ]

    # Upcoming events
    events = data.get("upcoming_events", [])
    if events:
        event_lines = []
        for e in events:
            dt = e.get("event_datetime", "")[:16]
            event_lines.append(f"• *{e['title']}* — {dt}")
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": ":date: *Upcoming Events*\n" + "\n".join(event_lines)}
        })
    else:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": ":date: *Upcoming Events*\nNo upcoming events — why not create one with `/event`?"}
        })

    # Active polls
    polls = data.get("active_polls", [])
    if polls:
        poll_lines = [f"• {p['question']}" for p in polls]
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": ":ballot_box: *Active Polls*\n" + "\n".join(poll_lines)}
        })

    # Opportunities
    opp_count = data.get("opportunities_this_week", 0)
    if opp_count:
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": f":briefcase: *{opp_count}* new opportunities posted this week"}
        })

    blocks.append({"type": "divider"})
    blocks.append({
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": "_Posted automatically by MeetPoll Bot every Monday_"}]
    })

    return blocks


def build_nudge_dm_blocks(first_name: str, digest_data: dict) -> list[dict]:
    """Build a friendly re-engagement DM."""
    name = first_name or "there"
    event_count = len(digest_data.get("upcoming_events", []))
    poll_count = len(digest_data.get("active_polls", []))
    opp_count = digest_data.get("opportunities_this_week", 0)

    highlights = []
    if event_count:
        highlights.append(f":date: {event_count} upcoming event{'s' if event_count != 1 else ''}")
    if poll_count:
        highlights.append(f":ballot_box: {poll_count} active poll{'s' if poll_count != 1 else ''}")
    if opp_count:
        highlights.append(f":briefcase: {opp_count} new opportunity posts this week")

    highlights_text = "\n".join(highlights) if highlights else "Check out the latest discussions!"

    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"Hey {name}! :wave:\n\n"
                    f"We haven't seen you around in a while and we miss you! "
                    f"Here's what's been happening in the community:\n\n"
                    f"{highlights_text}\n\n"
                    f"Come say hi! :blush:"
                )
            }
        }
    ]


def build_milestone_blocks(milestone_value: int, total_members: int) -> list[dict]:
    """Build a milestone celebration message."""
    return [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f":tada: {milestone_value} Members Milestone!", "emoji": True}
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    f"We just crossed *{milestone_value} members*! :partying_face:\n\n"
                    f"Our community now has *{total_members}* members and growing. "
                    f"Thank you all for being part of this journey! :heart:"
                )
            }
        }
    ]
