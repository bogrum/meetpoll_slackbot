"""
Block Kit UI builders for MeetPoll bot.
Creates interactive Slack message components.
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
