"""Rank jobs against a user profile.

The lexical score uses skills, title, and location. When a semantic score is
supplied, the posting's meaning is compared with the CV and that score leads.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

from job_matchmaker.models import Job, Match, UserProfile

SKILL_WEIGHT = 0.50
ROLE_WEIGHT = 0.25
LOCATION_WEIGHT = 0.25
FUZZY_HIT = 0.86

ALIASES = {
    "js": "javascript",
    "react.js": "react",
    "reactjs": "react",
    "node": "nodejs",
    "node.js": "nodejs",
    "postgres": "postgresql",
    "postgresql": "postgres",
    "k8s": "kubernetes",
    "powerbi": "power bi",
    "ml": "machine learning",
    "rest api": "rest apis",
    "rest apis": "rest api",
}

LEVELS = {"intern": 0, "junior": 1, "mid": 2, "senior": 3, "lead": 4}
STOP_LOCATION_WORDS = {"remote", "anywhere", "hybrid", "pakistan", "worldwide", "global"}
PRACTICE_SOURCES = {"Sample board", "Local HTML board"}


def rank_jobs(
    profile: UserProfile,
    jobs: list[Job],
    limit: int | None = None,
    semantic: dict[str, float] | None = None,
) -> list[Match]:
    cap = profile.top_n if limit is None else limit
    demote_practice = False
    if semantic:
        live_close = sum(
            1
            for job in jobs
            if job.source not in PRACTICE_SOURCES and semantic.get(job.id, 0) >= 0.55
        )
        demote_practice = live_close >= 3
    matches = [
        _score(
            profile,
            job,
            semantic=None if semantic is None else semantic.get(job.id),
            demote_practice=demote_practice and job.source in PRACTICE_SOURCES,
        )
        for job in jobs
    ]
    matches.sort(key=lambda match: (-match.score, match.job.title, match.job.company))
    return matches[: max(0, cap)]


def _score(
    profile: UserProfile,
    job: Job,
    semantic: float | None = None,
    demote_practice: bool = False,
) -> Match:
    skill_score, matched = _skill_score(profile.skills, job)
    role_score = max(_role_score(profile.roles, job), _role_score(_title_skills(profile.skills), job))
    location_score = _location_score(profile.location, job)
    if semantic is None:
        score = (
            SKILL_WEIGHT * skill_score
            + ROLE_WEIGHT * role_score
            + LOCATION_WEIGHT * location_score
        )
    else:
        score = 0.70 * semantic + 0.20 * skill_score + 0.10 * location_score
    reasons: list[str] = []
    if semantic is not None and semantic >= 0.62:
        reasons.append("The posting is close to the work described in your CV.")
    if matched:
        reasons.append("Skills: " + ", ".join(matched) + ".")
    elif profile.skills:
        reasons.append("Few of the listed skills appear in this posting.")
    else:
        reasons.append("No skills were listed, so the title and location led the ranking.")

    if profile.roles and role_score >= 0.75:
        reasons.append("The title fits the role you asked for.")
    elif profile.roles and role_score >= 0.45:
        reasons.append("The title is related to the role you asked for.")

    if location_score >= 0.9:
        reasons.append("The location matches where you want to work.")
    elif location_score >= 0.5 and (job.remote or "remote" in job.location.lower()):
        reasons.append("It is remote, so you can work from your city.")

    if demote_practice:
        score *= 0.72
        reasons.append("Live listings were a closer fit, so this practice card was moved down.")

    score = _apply_level_gap(profile.experience, job, score, reasons)
    return Match(
        job=job,
        score=max(0.0, min(1.0, score)),
        matched_skills=matched,
        reasons=reasons,
    )


def _title_skills(skills: list[str]) -> list[str]:
    """Multi-word skills can name the kind of job, for example Machine Learning."""
    return [skill for skill in skills if len(_normalize(skill).split()) >= 2]


def _skill_score(skills: list[str], job: Job) -> tuple[float, list[str]]:
    if not skills:
        return 0.45, []
    haystack = _normalize(" ".join([job.title, job.description, " ".join(job.tags)]))
    tag_norms = [_normalize(tag) for tag in job.tags]
    title_norm = _normalize(job.title)
    scores: list[float] = []
    matched: list[str] = []
    for skill in skills:
        variants = _variants(skill)
        if any(_contains_term(haystack, variant) for variant in variants):
            scores.append(1.0)
            matched.append(skill)
            continue
        best = 0.0
        for variant in variants:
            for candidate in tag_norms + [title_norm]:
                if not variant or not candidate:
                    continue
                best = max(best, SequenceMatcher(None, variant, candidate).ratio())
        if best >= FUZZY_HIT:
            scores.append(best)
            matched.append(skill)
        else:
            scores.append(0.0)
    earned = sum(scores)
    if earned <= 0:
        return 0.0, matched
    missed = len(scores) - earned
    # A CV lists more skills than any one job uses. Count the hits, and only
    # lightly penalize skills the posting never asked for.
    score = earned / (earned + 0.35 * missed)
    return max(0.0, min(1.0, score)), matched


def _role_score(roles: list[str], job: Job) -> float:
    if not roles:
        return 0.5
    title = _normalize(job.title)
    title_tokens = set(title.split())
    best = 0.0
    for role in roles:
        normalized = _normalize(role)
        if not normalized:
            continue
        if normalized in title or title in normalized:
            best = max(best, 1.0)
            continue
        role_tokens = [token for token in normalized.split() if len(token) > 2]
        overlap = 0.0
        if role_tokens:
            overlap = len(set(role_tokens) & title_tokens) / len(role_tokens)
        similarity = SequenceMatcher(None, normalized, title).ratio()
        best = max(best, overlap, similarity)
    return best


def _location_score(user_location: str, job: Job) -> float:
    loc = _normalize(user_location)
    job_loc = _normalize(job.location)
    user_remote = "remote" in loc or "anywhere" in loc
    job_remote = job.remote or "remote" in job_loc or "anywhere" in job_loc
    if not loc:
        return 0.6
    if user_remote and job_remote:
        return 1.0
    if loc and (loc in job_loc or job_loc in loc):
        return 1.0
    tokens = [token for token in loc.split() if len(token) > 3 and token not in STOP_LOCATION_WORDS]
    if any(token in job_loc for token in tokens):
        return 0.95
    if job_remote:
        return 0.62
    if user_remote:
        return 0.25
    return 0.2


def _apply_level_gap(experience: str, job: Job, score: float, reasons: list[str]) -> float:
    user_level = LEVELS.get(_normalize(experience), None)
    job_level = _infer_level(f"{job.title} {job.description[:240]}")
    if user_level is None or job_level is None:
        return score
    if abs(user_level - job_level) >= 2:
        reasons.append("The experience level is a step away from this role.")
        return score * 0.9
    return score


def _infer_level(text: str) -> int | None:
    tokens = set(_normalize(text).split())
    if "intern" in tokens or "internship" in tokens:
        return 0
    if "junior" in tokens or "jr" in tokens:
        return 1
    if "lead" in tokens or "principal" in tokens or "staff" in tokens:
        return 4
    if "senior" in tokens or "sr" in tokens:
        return 3
    return None


def _contains_term(haystack: str, term: str) -> bool:
    if not term:
        return False
    if " " in term:
        return term in haystack
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", haystack) is not None


def _variants(skill: str) -> list[str]:
    normalized = _normalize(skill)
    variants = [normalized] if normalized else []
    alias = ALIASES.get(normalized)
    if alias and alias not in variants:
        variants.append(alias)
    return variants


def _normalize(text: str) -> str:
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9+#./\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()
