from __future__ import annotations

from job_matchmaker.fetcher import FetchResult, fetch_jobs, query_from_profile
from job_matchmaker.matcher import rank_jobs
from job_matchmaker.models import Match, UserProfile
from job_matchmaker.notifier import deliver
from job_matchmaker.semantic import score_jobs
from job_matchmaker.store import load_profiles


def match_profile(profile: UserProfile) -> tuple[FetchResult, list[Match]]:
    fetched = fetch_jobs(profile.sources, query_from_profile(profile.roles, profile.skills))
    semantic = score_jobs(profile, fetched.jobs)
    if semantic is None:
        fetched.notes.append("Meaning match is unavailable, so this shortlist uses overlapping words.")
    else:
        fetched.notes.append("Ranked by how close each listing is to your CV.")
    matches = rank_jobs(profile, fetched.jobs, profile.top_n, semantic=semantic)
    return fetched, matches


def run_saved_profiles() -> list[str]:
    profiles = load_profiles()
    if not profiles:
        return [
            "No saved searches yet. In the app, turn on Save this search for the daily run, then search once."
        ]
    lines: list[str] = []
    for data in profiles:
        profile = UserProfile.from_dict(data)
        _fetched, matches = match_profile(profile)
        notes = deliver(
            profile,
            matches,
            email=bool(data.get("notify_email")),
            whatsapp=bool(data.get("notify_whatsapp")),
        )
        summary = f"{profile.name or profile.email}: {len(matches)} matches."
        lines.append(summary + " " + " ".join(notes))
    return lines
