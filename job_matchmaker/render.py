from __future__ import annotations

import html
import re

from job_matchmaker.models import Match, UserProfile

PRACTICE_SOURCES = {"Sample board", "Local HTML board"}
_SOURCE_LINKS = {
    "Remotive": "https://remotive.com",
    "Jobicy": "https://jobicy.com",
    "Remote OK": "https://remoteok.com",
    "Himalayas": "https://himalayas.app",
    "Working Nomads": "https://www.workingnomads.com",
}


def render_plain(profile: UserProfile, matches: list[Match]) -> str:
    lines: list[str] = []
    lines.append(f"Hello {profile.name}," if profile.name else "Hello,")
    lines.append("")
    role_text = ", ".join(profile.roles) if profile.roles else "the roles in your profile"
    place = profile.location or "any location"
    count = len(matches)
    role_word = "role" if count == 1 else "roles"
    lines.append(f"Here are {count} {role_word} close to {role_text} in {place}.")
    if profile.skills:
        lines.append("Skills used for this match: " + ", ".join(profile.skills) + ".")
    if profile.experience:
        lines.append(f"Experience level: {profile.experience}.")
    lines.append("")
    if not matches:
        lines.append("No listings matched this search.")
        lines.append("")
    for index, match in enumerate(matches, start=1):
        job = match.job
        kind = "practice listing" if job.source in PRACTICE_SOURCES else "live listing"
        lines.append(f"{index}. {job.title} — {job.company}")
        lines.append(
            f"   {job.location} · {job.source} · {kind} · {round(match.score * 100)}% match"
        )
        if match.reasons:
            lines.append("   " + " ".join(match.reasons))
        if job.description:
            lines.append("   " + _brief(job.description))
        if job.url:
            lines.append(f"   Apply: {job.url}")
        lines.append("")
    lines.append("Prepared by Job Matchmaker Agent.")
    for source, link in _SOURCE_LINKS.items():
        if any(match.job.source == source for match in matches):
            lines.append(f"{source} listings link back to {link}.")
    return "\n".join(lines).strip() + "\n"


def render_short(profile: UserProfile, matches: list[Match]) -> str:
    text = render_plain(profile, matches[:5])
    if len(text) <= 1400:
        return text
    return text[:1397].rstrip() + "..."


def render_html(matches: list[Match]) -> str:
    if not matches:
        return '<p class="empty">No listings came back for this search.</p>'
    cards = [render_card(match) for match in matches]
    notes = ["Practice listings are fictional and use example.com."]
    for source, link in _SOURCE_LINKS.items():
        if any(match.job.source == source for match in matches):
            safe_link = html.escape(link, quote=True)
            label = html.escape(link.replace("https://", ""))
            notes.append(
                f'{html.escape(source)} listings link back to <a href="{safe_link}" target="_blank" rel="noopener">{label}</a>.'
            )
    cards.append(f'<p class="attribution">{" ".join(notes)}</p>')
    return "\n".join(cards)


def render_card(match: Match) -> str:
    job = match.job
    score = round(match.score * 100)
    band = "job-high" if match.score >= 0.75 else "job-mid" if match.score >= 0.5 else "job-low"
    kind = "Practice listing" if job.source in PRACTICE_SOURCES else "Live listing"
    matched = {_normalize(skill) for skill in match.matched_skills}
    pills = []
    for tag in job.tags[:8]:
        classes = "pill pill-hit" if _normalize(tag) in matched or _tag_hit(tag, matched) else "pill"
        pills.append(f'<span class="{classes}">{html.escape(tag)}</span>')
    reasons = " ".join(match.reasons)
    link = ""
    if _safe_http(job.url):
        href = html.escape(job.url, quote=True)
        link = f'<p class="job-apply"><a class="job-link" href="{href}" target="_blank" rel="noopener">Open listing</a></p>'
    description = html.escape(_brief(job.description, 280))
    return f"""
<article class="job-card {band}">
  <div class="job-top">
    <div>
      <div class="job-kicker">{html.escape(kind)} · {html.escape(job.source)}</div>
      <h3 class="job-title">{html.escape(job.title)}</h3>
      <div class="job-meta">{html.escape(job.company)} · {html.escape(job.location)}</div>
    </div>
    <div class="job-score">{score}%</div>
  </div>
  <p class="job-copy">{description}</p>
  <div class="job-pills">{''.join(pills)}</div>
  <p class="job-why">{html.escape(reasons)}</p>
  {link}
</article>
""".strip()


def _tag_hit(tag: str, matched: set[str]) -> bool:
    normalized = _normalize(tag)
    return any(normalized == skill or normalized in skill or skill in normalized for skill in matched if skill)


def _brief(text: str, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _normalize(text: str) -> str:
    text = text.lower().replace("&", " and ")
    text = re.sub(r"[^a-z0-9+#./\s]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _safe_http(url: str) -> bool:
    return url.startswith("https://") or url.startswith("http://")
