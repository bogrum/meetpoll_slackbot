"""
Google Groups integration via Admin SDK Directory API.
Requires domain-wide delegation (DWD) configured in Google Workspace Admin Console.

Setup:
1. In Google Workspace Admin Console → Security → API Controls → Domain-wide Delegation,
   add the service account's Client ID with scope:
   https://www.googleapis.com/auth/admin.directory.group.member
2. Set env vars:
   GOOGLE_GROUP_EMAIL  — e.g. members@nyrsg.org
   GOOGLE_ADMIN_EMAIL  — a workspace admin email to impersonate
"""

import os
import logging

logger = logging.getLogger(__name__)

GOOGLE_SERVICE_ACCOUNT_PATH = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "./service_account.json")
GOOGLE_GROUP_EMAIL = os.getenv("GOOGLE_GROUP_EMAIL", "")
GOOGLE_ADMIN_EMAIL = os.getenv("GOOGLE_ADMIN_EMAIL", "")

ADMIN_SCOPE = "https://www.googleapis.com/auth/admin.directory.group.member"


def add_member_to_group(email: str) -> bool:
    """
    Add a member to the configured Google Group via Admin SDK with DWD.

    Returns True on success or if member already exists (idempotent).
    Returns False on failure (logs descriptive error).
    """
    if not GOOGLE_GROUP_EMAIL:
        logger.debug("GOOGLE_GROUP_EMAIL not set — skipping Google Group add")
        return False

    if not GOOGLE_ADMIN_EMAIL:
        logger.error(
            "GOOGLE_ADMIN_EMAIL is not set. "
            "Set it to a workspace admin email to enable domain-wide delegation."
        )
        return False

    if not os.path.exists(GOOGLE_SERVICE_ACCOUNT_PATH):
        logger.error(
            f"Service account file not found at {GOOGLE_SERVICE_ACCOUNT_PATH}. "
            "Cannot add member to Google Group."
        )
        return False

    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError

        credentials = service_account.Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_PATH,
            scopes=[ADMIN_SCOPE],
        )
        delegated_credentials = credentials.with_subject(GOOGLE_ADMIN_EMAIL)

        service = build("admin", "directory_v1", credentials=delegated_credentials)

        service.members().insert(
            groupKey=GOOGLE_GROUP_EMAIL,
            body={"email": email, "role": "MEMBER"},
        ).execute()

        logger.info(f"Added {email} to Google Group {GOOGLE_GROUP_EMAIL}")
        return True

    except Exception as e:
        # Import here to check the type — only available if google-api-python-client installed
        try:
            from googleapiclient.errors import HttpError
            if isinstance(e, HttpError):
                if e.resp.status == 409:
                    logger.info(f"{email} is already a member of {GOOGLE_GROUP_EMAIL}")
                    return True
                elif e.resp.status == 403:
                    logger.error(
                        f"Permission denied adding {email} to Google Group. "
                        "Ensure domain-wide delegation is configured: "
                        "Google Workspace Admin → Security → API Controls → Domain-wide Delegation. "
                        f"Add scope: {ADMIN_SCOPE}"
                    )
                    return False
                elif e.resp.status == 404:
                    logger.error(
                        f"Google Group {GOOGLE_GROUP_EMAIL} not found. "
                        "Check GOOGLE_GROUP_EMAIL env var."
                    )
                    return False
                else:
                    logger.error(f"HTTP error adding {email} to Google Group: {e}")
                    return False
        except ImportError:
            pass

        if "unauthorized_client" in str(e).lower() or "access_denied" in str(e).lower():
            logger.error(
                f"Domain-wide delegation not configured or not authorized. "
                f"Error: {e}. "
                "Go to Google Workspace Admin → Security → API Controls → Domain-wide Delegation "
                f"and add scope: {ADMIN_SCOPE}"
            )
        else:
            logger.error(f"Error adding {email} to Google Group {GOOGLE_GROUP_EMAIL}: {e}")
        return False
