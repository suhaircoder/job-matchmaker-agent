from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field


def split_list(value: str | list[str] | None) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    parts = re.split(r"[,;\n]", value or "")
    return [part.strip() for part in parts if part.strip()]


@dataclass
class Job:
    id: str
    title: str
    company: str
    location: str
    description: str
    url: str
    tags: list[str] = field(default_factory=list)
    source: str = ""
    remote: bool = False


@dataclass
class UserProfile:
    name: str
    email: str
    phone: str
    location: str
    roles: list[str]
    skills: list[str]
    experience: str
    sources: list[str]
    top_n: int = 6
    summary: str = ""

    @classmethod
    def from_form(
        cls,
        name: str,
        email: str,
        phone: str,
        location: str,
        roles: str,
        skills: str,
        experience: str,
        sources: list[str] | None,
        top_n: float | int,
        summary: str = "",
    ) -> UserProfile:
        try:
            limit = int(top_n)
        except (TypeError, ValueError):
            limit = 6
        return cls(
            name=(name or "").strip(),
            email=(email or "").strip(),
            phone=(phone or "").strip(),
            location=(location or "").strip(),
            roles=split_list(roles),
            skills=split_list(skills),
            experience=(experience or "Mid").strip() or "Mid",
            sources=list(sources or []),
            top_n=max(1, min(12, limit)),
            summary=(summary or "").strip(),
        )

    @classmethod
    def from_dict(cls, data: dict) -> UserProfile:
        return cls(
            name=data.get("name") or "",
            email=data.get("email") or "",
            phone=data.get("phone") or "",
            location=data.get("location") or "",
            roles=split_list(data.get("roles")),
            skills=split_list(data.get("skills")),
            experience=data.get("experience") or "Mid",
            sources=list(data.get("sources") or ["Sample board"]),
            top_n=max(1, min(12, int(data.get("top_n") or 6))),
            summary=data.get("summary") or "",
        )

    def to_record(self, *, notify_email: bool, notify_whatsapp: bool, saved_at: str) -> dict:
        record = asdict(self)
        record["notify_email"] = notify_email
        record["notify_whatsapp"] = notify_whatsapp
        record["saved_at"] = saved_at
        return record


@dataclass
class Match:
    job: Job
    score: float
    matched_skills: list[str]
    reasons: list[str]
