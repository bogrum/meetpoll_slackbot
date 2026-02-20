"""
RSS feed fetcher for bioinformatics opportunities.
Sources: jobrxiv.org (jobs/postdocs/PhDs) + opportunitydesk.org (fellowships/scholarships)
"""

import re
import logging
from html import unescape

logger = logging.getLogger(__name__)

FEEDS = [
    "https://jobrxiv.org/feed/?post_type=job_listing",
    "https://opportunitydesk.org/feed/",
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


def _is_relevant(entry) -> bool:
    title = _strip_html(entry.get("title") or "").lower()
    summary = _strip_html(entry.get("summary") or "").lower()
    text = title + " " + summary
    return any(kw in text for kw in KEYWORDS)


def fetch_bioinformatics_opportunities() -> list[dict]:
    """
    Fetch all configured RSS feeds and return bioinformatics-relevant entries.

    Each returned dict: {guid, title, link, summary, published}
    Returns empty list on errors.
    """
    try:
        import feedparser
    except ImportError:
        logger.error("feedparser is not installed. Run: pip install feedparser>=6.0.0")
        return []

    results = []
    seen_guids = set()

    for url in FEEDS:
        try:
            feed = feedparser.parse(url, request_headers=HEADERS)
        except Exception as e:
            logger.error(f"Error fetching RSS feed {url}: {e}")
            continue

        if feed.bozo and not feed.entries:
            logger.warning(f"RSS feed parse issue for {url}: {feed.bozo_exception}")
            continue

        for entry in feed.entries:
            if not _is_relevant(entry):
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
