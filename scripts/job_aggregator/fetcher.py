#!/usr/bin/env python3
"""Fetch jobs from various sources."""
import requests
from .config import ALL_TITLE_KEYWORDS, SEARCH_TAGS
import time
import re
import hashlib
import html
from typing import List, Dict
from bs4 import BeautifulSoup

REMOTIVE_API = "https://remotive.com/api/remote-jobs"
HEADERS = {"User-Agent": "CV-Pipeline Job Aggregator/1.0"}

# Use the template owner's configured title variations for large boards.
def title_passes_gate(title: str) -> bool:
    return not ALL_TITLE_KEYWORDS or any(kw in (title or "").lower() for kw in ALL_TITLE_KEYWORDS)


def fetch_remotive(category: str = None, search: str = None, limit: int = 100) -> List[Dict]:
    """Fetch jobs from Remotive API."""
    params = {"limit": limit}
    if category:
        params["category"] = category
    if search:
        params["search"] = search

    resp = requests.get(REMOTIVE_API, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data.get("jobs", [])


def fetch_all_remotive(categories: List[str]) -> List[Dict]:
    """Fetch from multiple categories, dedupe by ID."""
    seen_ids = set()
    jobs = []

    for cat in categories:
        time.sleep(1)  # Rate limiting
        for job in fetch_remotive(category=cat):
            if job["id"] not in seen_ids:
                seen_ids.add(job["id"])
                job["source"] = "remotive"
                jobs.append(job)

    return jobs


def fetch_workingnomads(categories: List[str] = None) -> List[Dict]:
    """Scrape WorkingNomads for remote jobs."""
    if categories is None:
        categories = ["development", "devops"]

    jobs = []
    seen_urls = set()

    for category in categories:
        try:
            time.sleep(1)  # Rate limiting
            url = f"https://www.workingnomads.com/jobs?category={category}"
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            # Find job links - they're in h4 elements with links to /jobs/
            for job_link in soup.select("a[href^='/jobs/']"):
                job_url = "https://www.workingnomads.com" + job_link.get("href", "")
                if job_url in seen_urls:
                    continue
                seen_urls.add(job_url)

                # Get the parent container to find related info
                parent = job_link.find_parent("div") or job_link

                title = job_link.get_text(strip=True)
                if not title or title.startswith("Unlock") or "Premium" in title:
                    continue

                # Try to find company - usually in a sibling link
                company_link = parent.select_one("a[href*='/remote-company/']")
                company = company_link.get_text(strip=True) if company_link else "Unknown"

                # Generate stable ID from URL
                job_id = int(hashlib.md5(job_url.encode()).hexdigest()[:8], 16)

                # Extract tags from text
                tags = []
                tag_links = parent.select("a[href*='remote-'][href$='-jobs']")
                for t in tag_links[:5]:
                    tag_text = t.get_text(strip=True)
                    if tag_text and len(tag_text) < 30:
                        tags.append(tag_text.lower())

                jobs.append({
                    "id": job_id,
                    "source": "workingnomads",
                    "url": job_url,
                    "title": title,
                    "company_name": company,
                    "candidate_required_location": "Remote",
                    "salary": None,
                    "tags": tags,
                    "category": category,
                    "job_type": "full_time",
                    "description": "",
                })

        except Exception as e:
            print(f"WorkingNomads fetch error ({category}): {e}")

    return jobs


def fetch_remoteok(tags: List[str] = None) -> List[Dict]:
    """Fetch jobs from RemoteOK API."""
    jobs = []
    try:
        # RemoteOK requires a user-agent
        resp = requests.get("https://remoteok.com/api", headers=HEADERS, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # First item is metadata, skip it
        for item in data[1:]:
            if not isinstance(item, dict):
                continue

            job_tags = item.get("tags", [])
            if isinstance(job_tags, str):
                job_tags = [job_tags]

            # Filter by tags if specified
            if tags:
                job_tags_lower = [t.lower() for t in job_tags]
                if not any(t.lower() in job_tags_lower for t in tags):
                    continue

            jobs.append({
                "id": item.get("id", 0),
                "source": "remoteok",
                "url": item.get("url", ""),
                "title": item.get("position", "Unknown"),
                "company_name": item.get("company", "Unknown"),
                "candidate_required_location": item.get("location", "Remote"),
                "salary": f"${item.get('salary_min', '')}-${item.get('salary_max', '')}" if item.get("salary_min") else None,
                "tags": job_tags[:10],
                "category": job_tags[0] if job_tags else "unknown",
                "job_type": "full_time",
                "publication_date": item.get("date", ""),
                "description": item.get("description", ""),
            })

    except Exception as e:
        print(f"RemoteOK fetch error: {e}")

    return jobs


# Search the configured role titles; country can be supplied by the caller.
HIMALAYAS_SEARCHES = [(term, None) for term in SEARCH_TAGS]


def fetch_himalayas(searches=None, pages: int = 2, country: str = None) -> List[Dict]:
    """Search Himalayas (20 per page) for each (query, seniority) pair."""
    jobs = []
    seen_ids = set()
    for query, seniority in searches or HIMALAYAS_SEARCHES:
        for page in range(1, pages + 1):
            params = {"q": query, "page": page}
            if country:
                params["country"] = country
            if seniority:
                params["seniority"] = seniority
            time.sleep(0.5)  # Rate limiting
            try:
                resp = requests.get("https://himalayas.app/jobs/api/search",
                                    params=params, headers=HEADERS, timeout=30)
                resp.raise_for_status()
                job_list = resp.json().get("jobs", [])
            except Exception as e:
                print(f"Himalayas search error ({query}, {seniority}): {e}")
                break

            for item in job_list:
                guid = item.get("guid", "")
                if not guid or guid in seen_ids:
                    continue
                seen_ids.add(guid)
                jobs.append(_himalayas_job(item))
            if len(job_list) < 20:
                break
    return jobs


def _himalayas_job(item: Dict) -> Dict:
    """Map one Himalayas API item onto the aggregator's job dict."""
    from datetime import datetime
    guid = item.get("guid", "")
    salary = None
    if item.get("minSalary") or item.get("maxSalary"):
        currency = item.get("currency", "USD")
        min_sal, max_sal = item.get("minSalary", ""), item.get("maxSalary", "")
        if min_sal and max_sal:
            salary = f"{currency} {min_sal}-{max_sal}"
        elif max_sal:
            salary = f"{currency} up to {max_sal}"

    # Empty restrictions means hiring worldwide. Keep every country: truncating
    # the list can hide the one that makes a job eligible.
    locations = item.get("locationRestrictions") or []
    location = ", ".join(locations) if locations else "Worldwide"

    pub_ts = item.get("pubDate")
    pub_date = (datetime.fromtimestamp(pub_ts).strftime("%Y-%m-%d")
                if isinstance(pub_ts, (int, float)) else None)

    # Rows stored on 2026-06-24 came back with companyName == "name"; fall back
    # to the slug so a placeholder never reaches the board.
    company = item.get("companyName") or ""
    if not company or company.strip().lower() == "name":
        company = (item.get("companySlug") or "Unknown").replace("-", " ").title()

    return {
        "id": int(hashlib.md5(guid.encode()).hexdigest()[:8], 16),
        "source": "himalayas",
        "url": item.get("applicationLink", ""),
        "title": item.get("title", "Unknown"),
        "company_name": company,
        "candidate_required_location": location,
        "salary": salary,
        "tags": item.get("categories", []) + item.get("parentCategories", []),
        "category": (item.get("parentCategories") or ["other"])[0],
        "job_type": (item.get("employmentType") or "Full Time").lower().replace(" ", "_"),
        "publication_date": pub_date,
        "description": item.get("description") or item.get("excerpt") or "",
    }


def fetch_cncf_jobs() -> List[Dict]:
    """Fetch jobs from CNCF-adjacent sources.

    GitJobs.dev is JS-rendered (HTMX) and doesn't have a public API.
    Instead, we scrape Greenhouse/Lever boards from known CNCF member companies.
    """
    jobs = []

    # Companies with public Greenhouse boards. Checked 2026-09-21: the other ids
    # this list carried (kubermatic, isovalent, buoyant, weaveworks, hashicorp,
    # suse, d2iq, giantswarm, pulumi, tetrate, soloio) all return 404.
    # Format: (company_name, board_type, board_id, tags)
    cncf_companies = [
        ("Form3", "greenhouse", "form3", ["fintech", "payments"]),
        ("Grafana Labs", "greenhouse", "grafanalabs", ["observability", "prometheus"]),
        ("Datadog", "greenhouse", "datadog", ["observability", "monitoring"]),
    ]

    for company_name, board_type, board_id, extra_tags in cncf_companies:
        try:
            time.sleep(0.5)  # Rate limiting

            if board_type == "greenhouse":
                api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_id}/jobs"
                resp = requests.get(api_url, headers=headers, timeout=30)
                if resp.status_code != 200:
                    continue

                data = resp.json()
                for item in data.get("jobs", []):
                    # Filter for relevant roles. Bare "engineer"/"developer" matched
                    # almost everything (one big member dumped 300+ roles), so match
                    # the title keywords configured in goals.yaml instead.
                    title = item.get("title", "").lower()
                    if not any(kw in title for kw in ALL_TITLE_KEYWORDS):
                        continue

                    location = item.get("location", {}).get("name", "Remote")

                    jobs.append({
                        "id": item.get("id", 0),
                        "source": "cncf",
                        "url": item.get("absolute_url", ""),
                        "title": item.get("title", "Unknown"),
                        "company_name": company_name,
                        "candidate_required_location": location,
                        "salary": None,
                        "tags": ["kubernetes", "cloud-native", "cncf"] + extra_tags,
                        "category": "cloud-native",
                        "job_type": "full_time",
                        "publication_date": item.get("updated_at", "")[:10] if item.get("updated_at") else None,
                        # content=true returns the posting as escaped HTML
                        "description": html.unescape(item.get("content") or ""),
                    })

        except Exception as e:
            print(f"CNCF fetch error ({company_name}): {e}")
            continue

    return jobs


def fetch_weworkremotely() -> List[Dict]:
    """Fetch jobs from WeWorkRemotely RSS feeds."""
    jobs = []

    # RSS feeds for relevant categories
    rss_feeds = [
        ("https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss", "devops"),
        ("https://weworkremotely.com/categories/remote-programming-jobs.rss", "programming"),
    ]

    seen_urls = set()

    for rss_url, category in rss_feeds:
        try:
            time.sleep(0.5)
            resp = requests.get(rss_url, headers=HEADERS, timeout=30)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "xml")  # needs lxml (requirements.txt)

            for item in soup.find_all("item"):
                try:
                    link = item.find("link")
                    if not link:
                        continue
                    job_url = link.get_text(strip=True)
                    if job_url in seen_urls:
                        continue
                    seen_urls.add(job_url)

                    title_elem = item.find("title")
                    title_text = title_elem.get_text(strip=True) if title_elem else "Unknown"

                    # Parse "Company: Title" format
                    if ":" in title_text:
                        company, title = title_text.split(":", 1)
                        company = company.strip()
                        title = title.strip()
                    else:
                        company = "Unknown"
                        title = title_text

                    # Filter for relevant roles (title keywords from goals.yaml)
                    title_lower = title.lower()
                    if not any(kw in title_lower for kw in ALL_TITLE_KEYWORDS):
                        continue

                    region = item.find("region")
                    location = region.get_text(strip=True) if region else "Remote"

                    skills = item.find("skills")
                    tags = []
                    if skills:
                        tags = [s.strip().lower() for s in skills.get_text().split(",")][:10]

                    pub_date_elem = item.find("pubDate")
                    pub_date = None
                    if pub_date_elem:
                        try:
                            from datetime import datetime
                            pd = pub_date_elem.get_text(strip=True)
                            dt = datetime.strptime(pd, "%a, %d %b %Y %H:%M:%S %z")
                            pub_date = dt.strftime("%Y-%m-%d")
                        except Exception:
                            pass

                    job_id = int(hashlib.md5(job_url.encode()).hexdigest()[:8], 16)

                    jobs.append({
                        "id": job_id,
                        "source": "weworkremotely",
                        "url": job_url,
                        "title": title,
                        "company_name": company,
                        "candidate_required_location": location,
                        "salary": None,
                        "tags": tags if tags else ["remote"],
                        "category": category,
                        "job_type": "full_time",
                        "publication_date": pub_date,
                        "description": (item.find("description").get_text()
                                        if item.find("description") else ""),
                    })

                except Exception:
                    continue

        except Exception as e:
            print(f"WWR fetch error ({category}): {e}")

    return jobs


def fetch_arbeitnow() -> List[Dict]:
    """Fetch jobs from Arbeitnow (EU-focused job board with API)."""
    jobs = []
    headers = {"User-Agent": "CV-Pipeline Job Aggregator/1.0"}

    try:
        # Arbeitnow has a public API
        resp = requests.get(
            "https://www.arbeitnow.com/api/job-board-api",
            headers=headers,
            timeout=30
        )
        if resp.status_code != 200:
            return jobs

        data = resp.json()

        for item in data.get("data", []):
            # Filter for relevant roles and remote jobs
            title = item.get("title", "").lower()
            remote = item.get("remote", False)

            if not remote:
                continue

            if not any(kw in title for kw in ALL_TITLE_KEYWORDS):
                continue

            location = item.get("location", "Remote")
            if item.get("remote"):
                location = f"{location} (Remote)" if location else "Remote"

            job_id = int(hashlib.md5(item.get("url", "").encode()).hexdigest()[:8], 16)

            tags = item.get("tags", [])
            if isinstance(tags, str):
                tags = [tags]

            # Parse timestamp
            pub_date = None
            created_at = item.get("created_at")
            if created_at:
                try:
                    from datetime import datetime
                    if isinstance(created_at, int):
                        pub_date = datetime.fromtimestamp(created_at).strftime("%Y-%m-%d")
                    elif isinstance(created_at, str):
                        pub_date = created_at[:10]
                except Exception:
                    pass

            jobs.append({
                "id": job_id,
                "source": "arbeitnow",
                "url": item.get("url", ""),
                "title": item.get("title", "Unknown"),
                "company_name": item.get("company_name", "Unknown"),
                "candidate_required_location": location,
                "salary": None,
                "tags": tags[:10] if tags else ["eu", "tech"],
                "category": "engineering",
                "job_type": "full_time",
                "publication_date": pub_date,
                "description": item.get("description", ""),
            })

    except Exception as e:
        print(f"Arbeitnow fetch error: {e}")

    return jobs


def fetch_all_sources(remotive_categories: List[str], progress=None,
                      empty_sources: List[str] = None) -> List[Dict]:
    """Fetch from all configured sources.

    progress: optional callback(message: str) for live UI feedback (e.g. the TUI
    status bar). Each source reports before fetching and its job count after.
    Always also prints, so the CLI path is unchanged.
    empty_sources: optional list; the label of every source that failed or
    returned no jobs is appended, so the caller can surface a dead source.
    """
    jobs = []

    def report(msg: str):
        print(msg)
        if progress:
            progress(msg)

    # (label, thunk, pre-sleep seconds)
    sources = [
        ("Remotive", lambda: fetch_all_remotive(remotive_categories), 0),
        ("RemoteOK", lambda: fetch_remoteok(tags=SEARCH_TAGS), 1),
        ("Himalayas", lambda: fetch_himalayas(), 0),
        ("CNCF companies", fetch_cncf_jobs, 1),
        ("WeWorkRemotely", fetch_weworkremotely, 1),
        ("Arbeitnow", fetch_arbeitnow, 1),
    ]

    for i, (label, thunk, presleep) in enumerate(sources, 1):
        report(f"[{i}/{len(sources)}] Fetching from {label}...")
        if presleep:
            time.sleep(presleep)
        try:
            found = thunk()
        except Exception as e:
            found = []
            report(f"[{i}/{len(sources)}] {label} failed: {e}")
        if not found and empty_sources is not None:
            empty_sources.append(label)
        jobs.extend(found)
        report(f"[{i}/{len(sources)}] {label}: {len(found)} jobs ({len(jobs)} total)")

    return jobs
