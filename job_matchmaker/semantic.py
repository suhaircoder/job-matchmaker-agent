"""Compare a CV with job postings by meaning, using a small local embedding model."""

from __future__ import annotations

import os

from job_matchmaker.models import Job, UserProfile

_MODEL = None
_UNAVAILABLE = False


def score_jobs(profile: UserProfile, jobs: list[Job]) -> dict[str, float] | None:
    """Return a 0–1 closeness score per job id, or None if the model cannot run."""
    global _MODEL, _UNAVAILABLE
    if _UNAVAILABLE or not jobs or os.getenv("JOB_MATCH_EMBEDDINGS") == "0":
        return None
    try:
        if _MODEL is None:
            from fastembed import TextEmbedding

            _MODEL = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
        texts = [_profile_text(profile), *(_job_text(job) for job in jobs)]
        vectors = list(_MODEL.embed(texts))
    except Exception:
        _UNAVAILABLE = True
        return None
    if len(vectors) != len(texts):
        return None
    anchor = vectors[0]
    scores: dict[str, float] = {}
    for job, vector in zip(jobs, vectors[1:]):
        raw = _cosine(anchor, vector)
        # On this model, unrelated postings sit near 0 and a genuinely related role sits near 0.40.
        stretched = (raw - 0.05) / 0.45
        scores[job.id] = max(0.0, min(1.0, stretched))
    return scores


def _profile_text(profile: UserProfile) -> str:
    parts: list[str] = []
    if profile.summary:
        parts.append(profile.summary.strip())
    if profile.roles:
        parts.append("Roles: " + ", ".join(profile.roles))
    if profile.skills:
        parts.append("Skills: " + ", ".join(profile.skills))
    if profile.experience:
        parts.append(f"Experience level: {profile.experience}")
    if profile.location:
        parts.append("Location: " + profile.location)
    text = "\n".join(part for part in parts if part).strip()
    return text[:2000] or "General job search"


def _job_text(job: Job) -> str:
    tags = ", ".join(job.tags[:12])
    description = " ".join((job.description or "").split())[:1200]
    return "\n".join(
        part
        for part in (job.title, job.company, job.location, tags, description)
        if part
    )


def _cosine(left, right) -> float:
    import numpy as np

    a = np.asarray(left, dtype=float)
    b = np.asarray(right, dtype=float)
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)
