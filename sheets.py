"""
Google Sheets API client for reading registration form responses.
Uses a service account for authentication (free, no billing needed).
"""

import os
import logging
import re

from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]

# Committee name mapping: form values (with emojis) → normalized English keys
COMMITTEE_MAP = {
    "Makale Kulübü / Journal Club": "Journal Club",
    "Journal Club": "Journal Club",
    "Üyelik / Membership": "Membership",
    "Membership": "Membership",
    "Dış İlişkiler / Outreach": "Outreach",
    "Outreach": "Outreach",
    "Sosyal Medya / Social Media": "Social Media",
    "Social Media": "Social Media",
    "Sponsorluk / Sponsorship": "Sponsorship",
    "Sponsorship": "Sponsorship",
    "Sempozyum / Symposium": "Symposium",
    "Symposium": "Symposium",
    "Çeviri / Translation": "Translation",
    "Translation": "Translation",
    "Webinar": "Webinar",
    "Website": "Website",
    "Grafik Tasarım / Graphic Design": "Graphic Design",
    "Graphic Design": "Graphic Design",
}


def _strip_emojis(text: str) -> str:
    """Remove emoji characters from a string."""
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "\U0001F900-\U0001F9FF"
        "\U0001FA00-\U0001FA6F"
        "\U0001FA70-\U0001FAFF"
        "\U00002600-\U000026FF"
        "\U0000FE00-\U0000FE0F"
        "\U0000200D"
        "\U00002B50"
        "\U000023F0-\U000023FF"
        "\U0000270A-\U0000270D"
        "\U000025A0-\U000025FF"
        "]+",
        flags=re.UNICODE,
    )
    return emoji_pattern.sub("", text).strip()


def normalize_committee(raw: str) -> str:
    """Normalize a committee name from form data to a standard key."""
    stripped = _strip_emojis(raw).strip()
    # Exact match first
    if stripped in COMMITTEE_MAP:
        return COMMITTEE_MAP[stripped]
    # Try matching the English portion after " / "
    for form_key, normalized in COMMITTEE_MAP.items():
        if " / " in form_key:
            english_part = form_key.split(" / ", 1)[1]
            if english_part.lower() == stripped.lower():
                return normalized
    # Substring match
    stripped_lower = stripped.lower()
    for form_key, normalized in COMMITTEE_MAP.items():
        if stripped_lower in form_key.lower() or form_key.lower() in stripped_lower:
            return normalized
    # Return cleaned version as-is if no match
    return stripped


def _get_service():
    """Build the Google Sheets API service."""
    creds_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "./service_account.json")
    creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


def fetch_registrations() -> list[dict]:
    """
    Fetch all registration rows from the Google Sheet.
    Returns a list of dicts with normalized keys.
    """
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    sheet_name = os.getenv("GOOGLE_SHEET_NAME", "Form Responses 1")

    if not sheet_id:
        logger.error("GOOGLE_SHEET_ID not set")
        return []

    try:
        service = _get_service()
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range=sheet_name)
            .execute()
        )

        rows = result.get("values", [])
        if len(rows) < 2:
            return []

        headers = rows[0]
        registrations = []

        for row in rows[1:]:
            # Pad row to match header length
            padded = row + [""] * (len(headers) - len(row))
            raw = dict(zip(headers, padded))
            normalized = _normalize_row(raw)
            if normalized and normalized.get("email"):
                registrations.append(normalized)

        logger.info(f"Fetched {len(registrations)} registrations from Google Sheet")
        return registrations

    except Exception as e:
        logger.error(f"Error fetching registrations: {e}")
        return []


def fetch_outreach_academics() -> list[dict]:
    """
    Fetch academic contacts from the outreach academics Google Sheet.
    Returns list of dicts: {first_name, last_name, email, title, institution}
    """
    sheet_id = os.getenv("OUTREACH_ACADEMICS_SHEET_ID")
    sheet_name = os.getenv("OUTREACH_ACADEMICS_SHEET_NAME", "Sheet1")

    if not sheet_id:
        logger.error("OUTREACH_ACADEMICS_SHEET_ID not set")
        return []

    try:
        service = _get_service()
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range=sheet_name)
            .execute()
        )

        rows = result.get("values", [])
        if len(rows) < 2:
            return []

        headers = rows[0]
        contacts = []
        for row in rows[1:]:
            padded = row + [""] * (len(headers) - len(row))
            raw = dict(zip(headers, padded))
            normalized = _normalize_academic_row(raw)
            if normalized and normalized.get("email"):
                contacts.append(normalized)

        logger.info(f"Fetched {len(contacts)} academic contacts from Google Sheet")
        return contacts

    except Exception as e:
        logger.error(f"Error fetching academic contacts: {e}")
        return []


def fetch_outreach_clubs() -> list[dict]:
    """
    Fetch club contacts from the outreach clubs Google Sheet.
    Returns list of dicts: {club_name, contact_person, email}
    """
    sheet_id = os.getenv("OUTREACH_CLUBS_SHEET_ID")
    sheet_name = os.getenv("OUTREACH_CLUBS_SHEET_NAME", "Sheet1")

    if not sheet_id:
        logger.error("OUTREACH_CLUBS_SHEET_ID not set")
        return []

    try:
        service = _get_service()
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=sheet_id, range=sheet_name)
            .execute()
        )

        rows = result.get("values", [])
        if len(rows) < 2:
            return []

        headers = rows[0]
        contacts = []
        for row in rows[1:]:
            padded = row + [""] * (len(headers) - len(row))
            raw = dict(zip(headers, padded))
            normalized = _normalize_club_row(raw)
            if normalized and normalized.get("email"):
                contacts.append(normalized)

        logger.info(f"Fetched {len(contacts)} club contacts from Google Sheet")
        return contacts

    except Exception as e:
        logger.error(f"Error fetching club contacts: {e}")
        return []


def _normalize_academic_row(raw: dict) -> dict:
    """Normalize an academic contact row. Handles Turkish/English column names.
    Supports both combined 'Ad Soyad' and separate 'Ad'/'Soyad' columns.
    """
    normalized = {}
    for key, value in raw.items():
        key_lower = key.lower().strip()
        val = str(value).strip() if value else ""
        if not val:
            continue

        if key_lower in ("e-posta", "email", "e-mail", "mail"):
            normalized["email"] = val.lower()
        elif key_lower in ("ad soyad", "ad-soyad", "isim", "name", "full name"):
            normalized["full_name"] = val
        elif key_lower in ("ad", "first name", "first_name"):
            normalized["first_name"] = val
        elif key_lower in ("soyad", "last name", "last_name", "family name", "soyisim"):
            normalized["last_name"] = val
        elif key_lower in ("unvan", "\u00fcnvan", "title", "academic title"):
            normalized["title"] = val
        elif key_lower in ("\u00fcniversite", "kurum", "institution", "university"):
            normalized["institution"] = val

    # If we have a combined full_name but no separate first/last, keep full_name as-is
    # If we have separate first/last but no full_name, combine them
    if "full_name" not in normalized and "first_name" in normalized:
        parts = [normalized.get("first_name", ""), normalized.get("last_name", "")]
        normalized["full_name"] = " ".join(p for p in parts if p)

    return normalized


def _normalize_club_row(raw: dict) -> dict:
    """Normalize a club contact row. Handles Turkish/English column names."""
    normalized = {}
    for key, value in raw.items():
        key_lower = key.lower().strip()
        val = str(value).strip() if value else ""
        if not val:
            continue

        if "email" in key_lower:
            normalized["email"] = val.lower()
        elif key_lower in ("kul\u00fcp ad\u0131", "club name", "club", "kul\u00fcp"):
            normalized["club_name"] = val
        elif key_lower in ("ileti\u015fim ki\u015fisi", "contact person", "contact", "ki\u015fi"):
            normalized["contact_person"] = val

    return normalized


def _normalize_row(raw: dict) -> dict:
    """Normalize a raw sheet row into a standard dict."""
    # Actual column headers from the form:
    #   [0] Timestamp
    #   [1] Email Address
    #   [2] İsim / Name
    #   [3] Soyisim / Family Name
    #   [4] Ülke / Country
    #   [5] Eğitim seviyesi / Education level
    #   [6] Tüm okul bilgileri / All affiliations
    #   [7] Üyelik seçimi / Membership choice (...)
    #   [8] Hangi aktif üye grubuna/gruplarına... (committees)
    normalized = {}

    for key, value in raw.items():
        key_lower = key.lower().strip()
        val = str(value).strip() if value else ""

        if key_lower == "timestamp":
            normalized["sheet_timestamp"] = val
        elif "email" in key_lower and "name" not in key_lower:
            normalized["email"] = val.lower()
        elif ("/ name" in key_lower and "family" not in key_lower
              and "last" not in key_lower):
            normalized["first_name"] = val
        elif ("family name" in key_lower or "soyisim" in key.lower().replace("i̇", "i")
              or "soyad" in key_lower or "last name" in key_lower):
            normalized["last_name"] = val
        elif "ülke" in key_lower or "country" in key_lower:
            normalized["country"] = val
        elif "eğitim" in key_lower or "education" in key_lower:
            normalized["education"] = val
        elif ("affiliation" in key_lower or "okul bilgileri" in key_lower
              or "bağlılık" in key_lower or "kuruluş" in key_lower):
            normalized["affiliations"] = val
        elif "üyelik" in key_lower or "membership" in key_lower:
            normalized["membership_choice"] = val
        elif ("grup" in key_lower or "group" in key_lower
              or "komite" in key_lower or "committee" in key_lower):
            # Committees are comma-separated or semicolon-separated
            if val:
                raw_committees = re.split(r"[;,]", val)
                committees = [normalize_committee(c.strip()) for c in raw_committees if c.strip()]
                normalized["committees"] = ", ".join(committees)

    return normalized
