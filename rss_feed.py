"""
RSS feed fetcher for bioinformatics opportunities.
Sources:
  - jobrxiv.org/bioinfo  : bioinformatics-specific job listings
  - opportunitydesk.org  : fellowships, scholarships, grants
  - tess.elixir-europe.org: European training events, summer schools, workshops (ELIXIR)

Note: TUBITAK (Turkey) has no RSS feed for scholarship/call announcements.
Monitor https://tubitak.gov.tr/en/announcements manually for BIDEB calls (2205, 2209, 2247-C).
"""

import re
import logging
from html import unescape
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Job/internship boards
JOB_FEEDS = [
    "https://jobrxiv.org/job-category/bioinfo/feed/",  # bioinformatics-specific (was: all jobs)
]

# Scholarships, fellowships, grants
SCHOLARSHIP_FEEDS = [
    "https://opportunitydesk.org/feed/",
]

# Training events, summer schools, workshops (ELIXIR European training portal)
# Already filtered to bioinformatics keywords on the server side
TRAINING_FEEDS = [
    "https://tess.elixir-europe.org/events.rss?keywords%5B%5D=bioinformatics",
]

KEYWORDS = [
    "bioinformatics",
    "computational biology",
    "genomics",
    "transcriptomics",
    "proteomics",
    "metagenomics",
    "biostatistics",
    "sequencing",
    "systems biology",
    "computational genomics",
    "omics",
    "ngs",
    "rna-seq",
    "single-cell",
    "structural biology",
    "molecular biology",
    "machine learning",
]

TITLE_BLACKLIST = {
    "senior", "principal", "director", "head of", "staff scientist",
    "postdoc", "postdoctoral", "faculty", "professor", "lecturer",
    "group leader", "team leader", "expert network", "join our network",
    "infrastructure engineer", "cloud engineer",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def _strip_html(text: str) -> str:
    text = re.sub(r"<[^>]+>", "", text or "")
    text = unescape(text)
    # Remove "The post ... appeared first on ..." trailing text added by some feeds
    text = re.sub(r"\s*The post .+ appeared first on .+\.$", "", text, flags=re.DOTALL)
    return text.strip()


def _is_relevant(entry, check_blacklist: bool = True) -> bool:
    title = _strip_html(entry.get("title") or "").lower()
    # Reject seniority/unrelated patterns in the title (skip for training events)
    if check_blacklist and any(b in title for b in TITLE_BLACKLIST):
        return False
    # Require a keyword match in the title (summary-only matches are too noisy)
    return any(kw in title for kw in KEYWORDS)


MAX_AGE_DAYS = 30  # skip entries older than this


def _is_recent(entry) -> bool:
    """Return False if the entry has a parseable date older than MAX_AGE_DAYS."""
    published = entry.get("published_parsed") or entry.get("updated_parsed")
    if not published:
        return True  # no date info — let it through
    try:
        pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - pub_dt <= timedelta(days=MAX_AGE_DAYS)
    except Exception:
        return True


def _parse_feed(url: str, check_blacklist: bool = True, seen_guids: set = None) -> list[dict]:
    """Parse a single RSS feed URL and return relevant entries."""
    import feedparser
    if seen_guids is None:
        seen_guids = set()
    results = []
    try:
        feed = feedparser.parse(url, request_headers=HEADERS)
    except Exception as e:
        logger.error(f"Error fetching RSS feed {url}: {e}")
        return results

    if feed.bozo and not feed.entries:
        logger.warning(f"RSS feed parse issue for {url}: {feed.bozo_exception}")
        return results

    for entry in feed.entries:
        if not _is_recent(entry):
            continue
        if not _is_relevant(entry, check_blacklist=check_blacklist):
            continue
        guid = entry.get("id") or entry.get("link") or ""
        if not guid or guid in seen_guids:
            continue
        seen_guids.add(guid)
        results.append({
            "guid": guid,
            "title": entry.get("title") or "",
            "link": entry.get("link") or "",
            "summary": _strip_html(entry.get("summary") or ""),
            "published": entry.get("published") or "",
        })
    return results


def fetch_bioinformatics_opportunities() -> list[dict]:
    """
    Fetch all configured RSS feeds and return bioinformatics-relevant entries.

    Each returned dict: {guid, title, link, summary, published}
    Returns empty list on errors.
    """
    try:
        import feedparser  # noqa: F401
    except ImportError:
        logger.error("feedparser is not installed. Run: pip install feedparser>=6.0.0")
        return []

    results = []
    seen_guids = set()

    for url in JOB_FEEDS + SCHOLARSHIP_FEEDS:
        results.extend(_parse_feed(url, check_blacklist=True, seen_guids=seen_guids))

    # Training feeds: ELIXIR TeSS already filters by keyword server-side;
    # skip seniority blacklist since course/workshop titles don't have those patterns
    for url in TRAINING_FEEDS:
        results.extend(_parse_feed(url, check_blacklist=False, seen_guids=seen_guids))

    return results
