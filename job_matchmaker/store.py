from __future__ import annotations

import json
from datetime import datetime, timezone

from job_matchmaker.models import UserProfile
from job_matchmaker.paths import DATA

PROFILE_PATH = DATA / "saved_profiles.json"


def load_profiles() -> list[dict]:
    if not PROFILE_PATH.exists():
        return []
    payload = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def save_profile(profile: UserProfile, *, notify_email: bool, notify_whatsapp: bool) -> str:
    if not profile.name or "@" not in profile.email:
        return "Add a name and a real email address before saving this search."
    record = profile.to_record(
        notify_email=notify_email,
        notify_whatsapp=notify_whatsapp,
        saved_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    profiles = [
        item
        for item in load_profiles()
        if (item.get("email") or "").lower() != profile.email.lower()
    ]
    profiles.append(record)
    PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_PATH.write_text(json.dumps(profiles, indent=2, ensure_ascii=False), encoding="utf-8")
    return "Saved this search for the daily run."
