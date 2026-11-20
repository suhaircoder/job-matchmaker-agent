"""Fetch job listings from a local sample board, a local HTML board, and public job APIs.

Remotive and Jobicy publish free JSON feeds and ask for a link back to the original
listing. LinkedIn, Indeed, and Glassdoor do not offer an open feed, so this agent
does not scrape them.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

from job_matchmaker.models import Job, split_list
from job_matchmaker.paths import CACHE, DATA

HEADERS = {
    "User-Agent": "JobMatchmakerAgent/1.0 (personal job alerts)",
    "Accept": "application/json, text/html",
}
CACHE_TTL_SECONDS = 6 * 60 * 60
SAMPLE_SOURCE = "Sample board"
HTML_SOURCE = "Local HTML board"
REMOTIVE_SOURCE = "Remotive"
JOBICY_SOURCE = "Jobicy"
REMOTEOK_SOURCE = "Remote OK"
HIMALAYAS_SOURCE = "Himalayas"
NOMADS_SOURCE = "Working Nomads"


@dataclass
class FetchResult:
    jobs: list[Job]
    notes: list[str]


def html_to_text(raw: str) -> str:
    if not raw:
        return ""
    text = BeautifulSoup(raw, "html.parser").get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text).strip()


def clip(text: str, limit: int = 5000) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "job"


def load_sample_jobs() -> list[Job]:
    payload = json.loads((DATA / "sample_jobs.json").read_text(encoding="utf-8"))
    return [_job_from_mapping(item, SAMPLE_SOURCE) for item in payload]


def parse_job_html(raw: str) -> list[Job]:
    soup = BeautifulSoup(raw, "html.parser")
    jobs: list[Job] = []
    for article in soup.select("article.job"):
        title = _text(article.select_one(".title"))
        if not title:
            continue
        location = _text(article.select_one(".location")) or "Unspecified"
        company = _text(article.select_one(".company")) or "Unknown company"
        link = article.select_one("a.apply")
        url = ""
        if link and link.get("href"):
            url = str(link.get("href"))
        tags = [li.get_text(" ", strip=True) for li in article.select(".tags li")]
        jobs.append(
            Job(
                id=f"local-{_slug(title)}",
                title=title,
                company=company,
                location=location,
                description=clip(_text(article.select_one(".description"))),
                url=url,
                tags=[tag for tag in tags if tag],
                source=HTML_SOURCE,
                remote="remote" in location.lower(),
            )
        )
    return jobs


def load_local_html_jobs() -> list[Job]:
    path = DATA / "local_board.html"
    if not path.exists():
        return []
    return parse_job_html(path.read_text(encoding="utf-8"))


# Job boards search better on these phrases than on a full CV headline.
SEARCH_TERMS = (
    "computer vision",
    "machine learning",
    "deep learning",
    "generative ai",
    "data scientist",
    "data analyst",
    "research engineer",
    "frontend",
    "backend",
    "devops",
    "react",
    "python",
)


def query_from_profile(roles: list[str], skills: list[str]) -> str:
    blob = " ".join([*(roles or []), *(skills or [])]).lower()
    for term in SEARCH_TERMS:
        if term in blob:
            return term
    if roles:
        return roles[0]
    if skills:
        return skills[0]
    return ""


def fetch_jobs(sources: list[str], query: str = "") -> FetchResult:
    selected = set(sources or [])
    jobs: list[Job] = []
    notes: list[str] = []

    if SAMPLE_SOURCE in selected:
        sample = load_sample_jobs()
        jobs.extend(sample)
        notes.append(f"Sample board: {len(sample)} practice listings.")

    if HTML_SOURCE in selected:
        local = load_local_html_jobs()
        jobs.extend(local)
        notes.append(f"Local HTML board: {len(local)} practice listings read with BeautifulSoup.")

    if REMOTIVE_SOURCE in selected:
        try:
            found, note = fetch_remotive(query)
            jobs.extend(found)
            notes.append(note)
        except requests.RequestException:
            notes.append("Remotive did not respond. The other selected boards are still included.")

    if JOBICY_SOURCE in selected:
        try:
            found, note = fetch_jobicy(query)
            jobs.extend(found)
            notes.append(note)
        except requests.RequestException:
            notes.append("Jobicy did not respond. The other selected boards are still included.")

    if REMOTEOK_SOURCE in selected:
        try:
            found, note = fetch_remoteok()
            jobs.extend(found)
            notes.append(note)
        except requests.RequestException:
            notes.append("Remote OK did not respond. The other selected boards are still included.")

    if HIMALAYAS_SOURCE in selected:
        try:
            found, note = fetch_himalayas()
            jobs.extend(found)
            notes.append(note)
        except requests.RequestException:
            notes.append("Himalayas did not respond. The other selected boards are still included.")

    if NOMADS_SOURCE in selected:
        try:
            found, note = fetch_working_nomads()
            jobs.extend(found)
            notes.append(note)
        except requests.RequestException:
            notes.append("Working Nomads did not respond. The other selected boards are still included.")

    deduped = _dedupe(jobs)
    if len(deduped) != len(jobs):
        notes.append(f"Removed {len(jobs) - len(deduped)} duplicate listings.")
    return FetchResult(jobs=deduped, notes=notes)


def fetch_remotive(query: str) -> tuple[list[Job], str]:
    jobs = _remotive_jobs(query)
    if jobs or not query:
        return jobs, f"Remotive: {len(jobs)} live listings."
    jobs = _remotive_jobs("")
    return jobs, f'Remotive: no listings for "{query}". Showing {len(jobs)} from the general feed.'


def fetch_jobicy(query: str) -> tuple[list[Job], str]:
    jobs = _jobicy_jobs(query)
    if jobs or not query:
        return jobs, f"Jobicy: {len(jobs)} live listings."
    jobs = _jobicy_jobs("")
    return jobs, f'Jobicy: no listings for "{query}". Showing {len(jobs)} from the general feed.'


def fetch_remoteok() -> tuple[list[Job], str]:
    payload = _cached_json("https://remoteok.com/api")
    rows = payload if isinstance(payload, list) else []
    jobs: list[Job] = []
    for item in rows:
        if not isinstance(item, dict) or not item.get("position"):
            continue
        title = str(item.get("position") or "").strip()
        url = str(item.get("url") or item.get("apply_url") or "").strip()
        if not title or not url:
            continue
        tags = [str(tag) for tag in item.get("tags") or [] if str(tag).strip()]
        location = str(item.get("location") or "Remote").strip() or "Remote"
        jobs.append(
            Job(
                id=f"remoteok-{item.get('id') or _slug(title)}",
                title=title,
                company=str(item.get("company") or "Unknown company").strip(),
                location=location,
                description=clip(html_to_text(str(item.get("description") or ""))),
                url=url,
                tags=tags[:12],
                source=REMOTEOK_SOURCE,
                remote=True,
            )
        )
    return jobs, f"Remote OK: {len(jobs)} live listings."


def fetch_himalayas() -> tuple[list[Job], str]:
    payload = _cached_json("https://himalayas.app/jobs/api?" + urlencode({"limit": 50}))
    rows = payload.get("jobs") if isinstance(payload, dict) else []
    jobs: list[Job] = []
    for item in rows or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("applicationLink") or "").strip()
        if not title or not url:
            continue
        restrictions = item.get("locationRestrictions") or []
        if isinstance(restrictions, list):
            location = ", ".join(str(part) for part in restrictions if str(part).strip()) or "Remote"
        else:
            location = str(restrictions or "Remote")
        tags = split_list(item.get("categories")) + split_list(item.get("parentCategories"))
        seniority = str(item.get("seniority") or "").strip()
        if seniority:
            tags.append(seniority)
        jobs.append(
            Job(
                id=f"himalayas-{item.get('guid') or _slug(title)}",
                title=title,
                company=str(item.get("companyName") or "Unknown company").strip(),
                location=location,
                description=clip(html_to_text(str(item.get("description") or item.get("excerpt") or ""))),
                url=url,
                tags=tags[:12],
                source=HIMALAYAS_SOURCE,
                remote=True,
            )
        )
    return jobs, f"Himalayas: {len(jobs)} live listings."


def fetch_working_nomads() -> tuple[list[Job], str]:
    payload = _cached_json("https://www.workingnomads.com/api/exposed_jobs/")
    rows = payload if isinstance(payload, list) else []
    jobs: list[Job] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not title or not url:
            continue
        jobs.append(
            Job(
                id=f"nomads-{_slug(title)}-{_slug(str(item.get('company_name') or ''))}",
                title=title,
                company=str(item.get("company_name") or "Unknown company").strip(),
                location=str(item.get("location") or "Remote").strip() or "Remote",
                description=clip(html_to_text(str(item.get("description") or ""))),
                url=url,
                tags=split_list(item.get("tags"))[:12],
                source=NOMADS_SOURCE,
                remote=True,
            )
        )
    return jobs, f"Working Nomads: {len(jobs)} live listings."


def _remotive_jobs(query: str) -> list[Job]:
    params: dict[str, str | int] = {"limit": 50}
    if query:
        params["search"] = query
    url = "https://remotive.com/api/remote-jobs?" + urlencode(params)
    body = _cached_get(url)
    jobs: list[Job] = []
    for item in body.get("jobs") or []:
        title = str(item.get("title") or "").strip()
        url_value = str(item.get("url") or "").strip()
        if not title or not url_value:
            continue
        tags = split_list(item.get("tags"))
        category = str(item.get("category") or "").strip()
        if category:
            tags.append(category)
        location = str(item.get("candidate_required_location") or "Remote").strip() or "Remote"
        jobs.append(
            Job(
                id=f"remotive-{item.get('id') or _slug(title)}",
                title=title,
                company=str(item.get("company_name") or "Unknown company").strip(),
                location=location,
                description=clip(html_to_text(str(item.get("description") or ""))),
                url=url_value,
                tags=tags,
                source=REMOTIVE_SOURCE,
                remote=True,
            )
        )
    return jobs


def _jobicy_jobs(query: str) -> list[Job]:
    params: dict[str, str | int] = {"count": 20}
    tag = _jobicy_tag(query)
    if tag:
        params["tag"] = tag
    url = "https://jobicy.com/api/v2/remote-jobs?" + urlencode(params)
    body = _cached_get(url)
    listings = body.get("jobs") or []
    jobs: list[Job] = []
    for item in listings:
        title = str(item.get("jobTitle") or "").strip()
        url_value = str(item.get("url") or "").strip()
        if not title or not url_value:
            continue
        tags = split_list(item.get("jobIndustry")) + split_list(item.get("jobType"))
        level = str(item.get("jobLevel") or "").strip()
        if level:
            tags.append(level)
        location = str(item.get("jobGeo") or "Remote").strip() or "Remote"
        description = html_to_text(str(item.get("jobDescription") or "")) or html_to_text(
            str(item.get("jobExcerpt") or "")
        )
        jobs.append(
            Job(
                id=f"jobicy-{item.get('id') or _slug(title)}",
                title=title,
                company=str(item.get("companyName") or "Unknown company").strip(),
                location=location,
                description=clip(description),
                url=url_value,
                tags=tags,
                source=JOBICY_SOURCE,
                remote=True,
            )
        )
    return jobs


def _jobicy_tag(query: str) -> str:
    """Jobicy filters by a single tag, so a phrase like computer vision becomes one."""
    mapped = {
        "computer vision": "python",
        "machine learning": "python",
        "deep learning": "python",
        "generative ai": "python",
        "data scientist": "python",
        "research engineer": "python",
        "data analyst": "sql",
        "frontend": "javascript",
        "backend": "python",
        "devops": "devops",
        "react": "react",
        "python": "python",
    }
    if not query:
        return ""
    key = query.lower()
    if key in mapped:
        return mapped[key]
    if re.fullmatch(r"[A-Za-z0-9.+#-]+", query):
        return query
    return ""


def _job_from_mapping(item: dict, default_source: str) -> Job:
    title = str(item.get("title") or "Untitled role")
    location = str(item.get("location") or "Unspecified")
    return Job(
        id=str(item.get("id") or _slug(title)),
        title=title,
        company=str(item.get("company") or "Unknown company"),
        location=location,
        description=clip(html_to_text(str(item.get("description") or ""))),
        url=str(item.get("url") or ""),
        tags=[str(tag) for tag in item.get("tags") or [] if str(tag).strip()],
        source=str(item.get("source") or default_source),
        remote=bool(item.get("remote")) or "remote" in location.lower(),
    )


def _text(node) -> str:
    if node is None:
        return ""
    return node.get_text(" ", strip=True)


def _dedupe(jobs: list[Job]) -> list[Job]:
    seen: set[str] = set()
    unique: list[Job] = []
    for job in jobs:
        key = (job.url or "").strip().lower() or f"{job.source}|{job.title}|{job.company}".lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(job)
    return unique


def _cached_json(url: str):
    CACHE.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    path = CACHE / f"{key}.json"
    now = time.time()
    if path.exists():
        cached = json.loads(path.read_text(encoding="utf-8"))
        if cached.get("url") == url and now - float(cached.get("fetched_at") or 0) < CACHE_TTL_SECONDS:
            body = cached.get("body")
            if isinstance(body, (dict, list)):
                return body
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    body = response.json()
    if not isinstance(body, (dict, list)):
        raise requests.RequestException("Job board returned an unexpected payload.")
    path.write_text(
        json.dumps({"fetched_at": now, "url": url, "body": body}),
        encoding="utf-8",
    )
    return body


def _cached_get(url: str) -> dict:
    body = _cached_json(url)
    if not isinstance(body, dict):
        raise requests.RequestException("Job board returned an unexpected payload.")
    return body
