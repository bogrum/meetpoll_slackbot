import requests
import json
from dataclasses import dataclass, asdict
from typing import Optional
from datetime import datetime

@dataclass
class Job:
    title: str
    institution: str
    location: str
    posted_on: str
    url: str
    source: str
    category: Optional[str] = None
    experience_level: Optional[str] = None

    def to_opportunity_dict(self) -> dict:
        """Convert to the dict format expected by db.add_pending_opportunity()."""
        parts = [self.institution, self.location]
        summary = " | ".join(p for p in parts if p and p != "N/A")
        if self.experience_level:
            summary += f" | {self.experience_level}"
        return {
            "guid": self.url,
            "title": self.title,
            "link": self.url,
            "summary": summary,
        }

    def is_undergrad_friendly(self) -> bool:
        """Heuristic filter for undergrad-appropriate roles."""
        blacklist = {
            "postdoc", "postdoctoral", "phd required", "senior", "principal",
            "director", "head of", "5+ years", "10+ years",
            "group leader", "team leader", "manager", "officer", "staff scientist",
            "faculty", "professor", "lecturer",
            "expert network", "join our network",
        }
        whitelist = {"intern", "internship", "undergraduate", "bsc", "bachelor", "junior", "trainee", "student", "entry"}
        text = (self.title + " " + (self.category or "")).lower()
        if any(b in text for b in blacklist):
            return False
        if any(w in text for w in whitelist):
            return True
        return None  # unknown - let caller decide


class WorkdayFetcher:
    """
    Fetches jobs from any institution using Workday ATS.
    The POST /wday/cxs/{tenant}/{board}/jobs endpoint is public - no auth needed.
    
    To find a new institution's tenant/board:
    - Go to their jobs page, look for myworkdayjobs.com in the URL
    - Pattern: https://{tenant}.wd{N}.myworkdayjobs.com/{board}
    """
    
    KNOWN_INSTITUTIONS = {
        "embl":    ("embl.wd103",  "EMBL"),        # covers EMBL + EMBL-EBI (same board)
        "sanger":  ("sanger.wd103", "WellcomeSangerInstitute"),  # Wellcome Sanger Institute, UK
        # "max_planck": ("mpi.wd3", "MPG"),        # unverified — enable once confirmed
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
            "Content-Type": "application/json",
        })

    def _build_url(self, tenant_wd: str, board: str) -> str:
        return f"https://{tenant_wd}.myworkdayjobs.com/wday/cxs/{tenant_wd.split('.')[0]}/{board}/jobs"

    def fetch(
        self,
        institution_key: str = None,
        tenant_wd: str = None,
        board: str = None,
        search_text: str = "",
        limit: int = 20,
        offset: int = 0,
        undergrad_only: bool = False,
    ) -> list[Job]:
        """
        Fetch jobs from a Workday-powered institution.
        
        Either pass institution_key (e.g. "embl") or tenant_wd + board manually.
        
        Args:
            institution_key: Shorthand from KNOWN_INSTITUTIONS dict
            tenant_wd: e.g. "embl.wd103"
            board: e.g. "EMBL"
            search_text: keyword search
            limit: results per page (max ~20 recommended)
            offset: for pagination
            undergrad_only: apply heuristic filter
        """
        if institution_key:
            if institution_key not in self.KNOWN_INSTITUTIONS:
                raise ValueError(f"Unknown institution. Known: {list(self.KNOWN_INSTITUTIONS)}")
            tenant_wd, board = self.KNOWN_INSTITUTIONS[institution_key]
        elif not (tenant_wd and board):
            raise ValueError("Provide either institution_key or both tenant_wd and board.")

        url = self._build_url(tenant_wd, board)
        payload = {
            "appliedFacets": {},
            "limit": limit,
            "offset": offset,
            "searchText": search_text,
        }

        resp = self.session.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        institution_name = institution_key or tenant_wd
        jobs = []
        for j in data.get("jobPostings", []):
            # Build full URL to the job posting
            external_path = j.get("externalPath", "")
            job_url = f"https://{tenant_wd}.myworkdayjobs.com/{board}{external_path}"

            job = Job(
                title=j.get("title", ""),
                institution=institution_name.upper(),
                location=j.get("locationsText") or "N/A",
                posted_on=j.get("postedOn", ""),
                url=job_url,
                source="workday",
            )
            jobs.append(job)

        if undergrad_only:
            jobs = [j for j in jobs if j.is_undergrad_friendly() is not False]

        return jobs

    def fetch_all_pages(self, page_limit: int = 5, **kwargs) -> list[Job]:
        """Paginate through results. page_limit caps API calls."""
        all_jobs, offset, limit = [], 0, kwargs.pop("limit", 20)
        for _ in range(page_limit):
            batch = self.fetch(limit=limit, offset=offset, **kwargs)
            if not batch:
                break
            all_jobs.extend(batch)
            offset += limit
        return all_jobs


class AdzunaFetcher:
    """
    Adzuna Jobs API - free tier: 1000 calls/month.
    Register at: https://developer.adzuna.com/
    """
    BASE = "https://api.adzuna.com/v1/api/jobs"

    COUNTRY_CODES = {
        "turkey": "tr", "uk": "gb", "germany": "de",
        "usa": "us", "australia": "au", "canada": "ca",
    }

    def __init__(self, app_id: str, app_key: str):
        self.app_id = app_id
        self.app_key = app_key
        self.session = requests.Session()

    def fetch(
        self,
        query: str,
        country: str = "gb",
        results_per_page: int = 20,
        page: int = 1,
        max_days_old: int = 30,
        undergrad_only: bool = False,
    ) -> list[Job]:
        """
        Args:
            query: keyword string e.g. "bioinformatics internship"
            country: 2-letter ISO or key from COUNTRY_CODES
            max_days_old: filter by recency
        """
        country = self.COUNTRY_CODES.get(country.lower(), country)
        url = f"{self.BASE}/{country}/search/{page}"

        params = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "what": query,
            "results_per_page": results_per_page,
            "max_days_old": max_days_old,
            "content-type": "application/json",
        }

        resp = self.session.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        jobs = []
        for j in data.get("results", []):
            job = Job(
                title=j.get("title", ""),
                institution=j.get("company", {}).get("display_name", ""),
                location=j.get("location", {}).get("display_name", ""),
                posted_on=j.get("created", ""),
                url=j.get("redirect_url", ""),
                source="adzuna",
                category=j.get("category", {}).get("label", ""),
            )
            jobs.append(job)

        if undergrad_only:
            jobs = [j for j in jobs if j.is_undergrad_friendly() is not False]

        return jobs


if __name__ == "__main__":
    # --- Test Workday (no key needed) ---
    fetcher = WorkdayFetcher()

    print("=== EMBL Internships (Workday, free) ===")
    jobs = fetcher.fetch(institution_key="embl", search_text="intern", undergrad_only=True)
    for j in jobs:
        print(f"  [{j.posted_on}] {j.title} | {j.location}")
        print(f"    {j.url}\n")

    print(f"\nTotal: {len(jobs)} undergrad-friendly jobs\n")

    # --- Adzuna example (needs key) ---
    print("=== Adzuna (needs free API key) ===")
    print("  Register at https://developer.adzuna.com/ then:")
    print("  fetcher = AdzunaFetcher(app_id='your_id', app_key='your_key')")
    print("  jobs = fetcher.fetch('bioinformatics intern', country='tr', undergrad_only=True)")
