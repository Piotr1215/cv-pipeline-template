#!/usr/bin/env python3
"""Fetch jobs from various sources."""
import requests
from .config import ALL_TITLE_KEYWORDS, SEARCH_TAGS
import time
import re
import hashlib
from typing import List, Dict
from bs4 import BeautifulSoup

REMOTIVE_API = "https://remotive.com/api/remote-jobs"


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


def fetch_devrelcareers(max_days_old: int = 30) -> List[Dict]:
    """Fetch DevRelCareers jobs from their sitemap."""
    from datetime import datetime, timedelta
    jobs = []
    cutoff = datetime.now() - timedelta(days=max_days_old)

    try:
        resp = requests.get("https://devrelcareers.com/sitemap-jobs.xml", timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "xml")

        for url_elem in soup.find_all("url"):
            loc = url_elem.find("loc")
            lastmod = url_elem.find("lastmod")

            if not loc:
                continue

            url = loc.get_text(strip=True)
            if "/job/" not in url:
                continue

            # Parse date and filter by age
            pub_date = None
            if lastmod:
                try:
                    pub_date = datetime.strptime(lastmod.get_text(strip=True), "%Y-%m-%d")
                    if pub_date < cutoff:
                        continue
                except ValueError:
                    pass

            # Extract info from URL slug: /job/1234567-title-here-company
            slug = url.split("/job/")[-1]
            parts = slug.split("-", 1)
            if len(parts) < 2:
                continue

            # Title is in the slug, convert dashes to spaces and titlecase
            title_slug = parts[1]
            title = title_slug.replace("-", " ").title()

            # Try to extract company from end of title (usually last word)
            words = title_slug.split("-")
            company = words[-1].title() if words else "Unknown"

            # Generate stable ID from URL
            job_id = int(hashlib.md5(url.encode()).hexdigest()[:8], 16)

            jobs.append({
                "id": job_id,
                "source": "devrelcareers",
                "url": url,
                "title": title,
                "company_name": company,
                "candidate_required_location": "Remote",
                "salary": None,
                "tags": ["devrel", "developer-relations", "developer-advocate"],
                "category": "DevRel",
                "job_type": "full_time",
                "publication_date": pub_date.strftime("%Y-%m-%d") if pub_date else None,
                "description": "",
            })
    except Exception as e:
        print(f"DevRelCareers fetch error: {e}")

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
        headers = {"User-Agent": "CV-Pipeline Job Aggregator/1.0"}
        resp = requests.get("https://remoteok.com/api", headers=headers, timeout=30)
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


def fetch_himalayas(limit: int = 100) -> List[Dict]:
    """Fetch jobs from Himalayas API (max 20 per request)."""
    jobs = []
    seen_ids = set()

    try:
        # Fetch multiple pages (API max is 20 per request)
        for offset in range(0, limit, 20):
            time.sleep(0.5)  # Rate limiting
            resp = requests.get(
                f"https://himalayas.app/jobs/api?limit=20&offset={offset}",
                timeout=30
            )
            resp.raise_for_status()
            data = resp.json()

            # API returns {"jobs": [...], "totalCount": N, ...}
            job_list = data.get("jobs", [])
            if not job_list:
                break

            for item in job_list:
                guid = item.get("guid", "")
                if guid in seen_ids:
                    continue
                seen_ids.add(guid)

                # Generate stable ID from guid
                job_id = int(hashlib.md5(guid.encode()).hexdigest()[:8], 16)

                # Parse salary
                salary = None
                if item.get("minSalary") or item.get("maxSalary"):
                    currency = item.get("currency", "USD")
                    min_sal = item.get("minSalary", "")
                    max_sal = item.get("maxSalary", "")
                    if min_sal and max_sal:
                        salary = f"{currency} {min_sal}-{max_sal}"
                    elif max_sal:
                        salary = f"{currency} up to {max_sal}"

                # Location from restrictions
                locations = item.get("locationRestrictions", [])
                location = ", ".join(locations[:3]) if locations else "Remote"

                # Convert Unix timestamp to date string
                pub_ts = item.get("pubDate")
                pub_date = None
                if pub_ts and isinstance(pub_ts, (int, float)):
                    from datetime import datetime
                    pub_date = datetime.fromtimestamp(pub_ts).strftime("%Y-%m-%d")

                jobs.append({
                    "id": job_id,
                    "source": "himalayas",
                    "url": item.get("applicationLink", ""),
                    "title": item.get("title", "Unknown"),
                    "company_name": item.get("companyName", "Unknown"),
                    "candidate_required_location": location,
                    "salary": salary,
                    "tags": item.get("categories", []) + item.get("parentCategories", []),
                    "category": item.get("parentCategories", ["other"])[0] if item.get("parentCategories") else "other",
                    "job_type": item.get("employmentType", "Full Time").lower().replace(" ", "_"),
                    "publication_date": pub_date,
                    "description": item.get("excerpt", ""),
                })

    except Exception as e:
        print(f"Himalayas fetch error: {e}")

    return jobs


def fetch_cncf_jobs() -> List[Dict]:
    """Fetch jobs from CNCF-adjacent sources.

    GitJobs.dev is JS-rendered (HTMX) and doesn't have a public API.
    Instead, we scrape Greenhouse/Lever boards from known CNCF member companies.
    """
    jobs = []
    headers = {"User-Agent": "CV-Pipeline Job Aggregator/1.0"}

    # CNCF member companies with public job boards (Greenhouse/Lever)
    # Format: (company_name, board_type, board_id, tags)
    cncf_companies = [
        ("Form3", "greenhouse", "form3", ["fintech", "payments"]),
        ("Kubermatic", "greenhouse", "kubermatic", ["kubernetes"]),
        ("Isovalent", "greenhouse", "isovalent", ["cilium", "ebpf"]),
        ("Buoyant", "greenhouse", "buoyant", ["linkerd", "service-mesh"]),
        ("Weaveworks", "greenhouse", "weaveworks", ["gitops", "flux"]),
        ("Grafana Labs", "greenhouse", "grafanalabs", ["observability", "prometheus"]),
        ("HashiCorp", "greenhouse", "hashicorp", ["terraform", "vault"]),
        ("SUSE", "greenhouse", "suse", ["rancher", "kubernetes"]),
        ("D2iQ", "greenhouse", "d2iq", ["kubernetes"]),
        ("Giant Swarm", "greenhouse", "giantswarm", ["kubernetes"]),
        ("Pulumi", "greenhouse", "pulumi", ["iac", "cloud"]),
        ("Tetrate", "greenhouse", "tetrate", ["istio", "service-mesh"]),
        ("Solo.io", "greenhouse", "soloio", ["istio", "envoy"]),
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
                        "description": "",
                    })

        except Exception as e:
            print(f"CNCF fetch error ({company_name}): {e}")
            continue

    return jobs


def fetch_weworkremotely() -> List[Dict]:
    """Fetch jobs from WeWorkRemotely RSS feeds."""
    jobs = []
    headers = {"User-Agent": "CV-Pipeline Job Aggregator/1.0"}

    # RSS feeds for relevant categories
    rss_feeds = [
        ("https://weworkremotely.com/categories/remote-devops-sysadmin-jobs.rss", "devops"),
        ("https://weworkremotely.com/categories/remote-programming-jobs.rss", "programming"),
    ]

    seen_urls = set()

    for rss_url, category in rss_feeds:
        try:
            time.sleep(0.5)
            resp = requests.get(rss_url, headers=headers, timeout=30)
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "xml")

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
                        "description": "",
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
                "description": "",
            })

    except Exception as e:
        print(f"Arbeitnow fetch error: {e}")

    return jobs


def fetch_all_sources(remotive_categories: List[str], progress=None) -> List[Dict]:
    """Fetch from all configured sources.

    progress: optional callback(message: str) for live UI feedback (e.g. the TUI
    status bar). Each source reports before fetching and the running job total
    after. Always also prints, so the CLI path is unchanged.
    """
    jobs = []

    def report(msg: str):
        print(msg)
        if progress:
            progress(msg)

    # (label, thunk, pre-sleep seconds)
    sources = [
        ("Remotive", lambda: fetch_all_remotive(remotive_categories), 0),
        ("DevRelCareers", fetch_devrelcareers, 0),
        ("RemoteOK", lambda: fetch_remoteok(tags=SEARCH_TAGS), 1),
        ("Himalayas", lambda: fetch_himalayas(limit=100), 0),
        ("CNCF companies", fetch_cncf_jobs, 1),
        ("WeWorkRemotely", fetch_weworkremotely, 1),
        ("Arbeitnow", fetch_arbeitnow, 1),
    ]

    for i, (label, thunk, presleep) in enumerate(sources, 1):
        report(f"[{i}/{len(sources)}] Fetching from {label}...")
        if presleep:
            time.sleep(presleep)
        try:
            jobs.extend(thunk())
        except Exception as e:
            report(f"  {label} failed: {e}")
        report(f"[{i}/{len(sources)}] {label} done — {len(jobs)} jobs so far")

    return jobs
