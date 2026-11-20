"""Read a PDF, DOCX, or TXT résumé into the profile the matcher uses."""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

# Longer phrases first so "machine learning" is found before shorter pieces.
LEXICON = (
    "3D Morphable Models",
    "Natural Language Processing",
    "Computer Vision",
    "Machine Learning",
    "Deep Learning",
    "Generative AI",
    "Data Analysis",
    "REST APIs",
    "Power BI",
    "JavaScript",
    "TypeScript",
    "PostgreSQL",
    "Hugging Face",
    "TensorFlow",
    "PyTorch",
    "FastAPI",
    "OpenCV",
    "Kubernetes",
    "Node.js",
    "LangChain",
    "Tableau",
    "Selenium",
    "Docker",
    "Django",
    "Flask",
    "Pandas",
    "NumPy",
    "Python",
    "React",
    "Linux",
    "Excel",
    "Figma",
    "HTML",
    "CSS",
    "SQL",
    "Git",
    "AWS",
    "Azure",
    "NLP",
    "LLM",
    "C++",
    "Java",
    "CUDA",
    "MLOps",
)

HEADINGS = {
    "summary": "summary",
    "professional summary": "summary",
    "professional profile": "summary",
    "profile": "summary",
    "objective": "summary",
    "research interests": "interests",
    "technical skills": "skills",
    "core skills": "skills",
    "key skills": "skills",
    "skills": "skills",
    "professional experience": "experience",
    "work experience": "experience",
    "research experience": "experience",
    "experience": "experience",
    "employment": "experience",
    "education": "education",
    "publications": "publications",
    "languages": "languages",
}

SKIP_PHRASES = {
    "programming",
    "tools",
    "frameworks",
    "libraries",
    "platforms",
    "databases",
    "soft skills",
    "languages",
    "technical skills",
    "skills",
    "other",
    "workflows",
}


@dataclass
class ParsedCV:
    name: str
    email: str
    phone: str
    location: str
    roles: list[str]
    skills: list[str]
    experience: str
    focus: str = ""

    def note(self) -> str:
        who = self.name or "This CV"
        role = self.roles[0] if self.roles else "the work described in the CV"
        place = f" in {self.location}" if self.location else ""
        return f"Read {who}'s CV as a {self.experience.lower()} {role}{place}."


def read_cv(path: str | Path) -> ParsedCV:
    file_path = Path(path)
    suffix = file_path.suffix.lower()
    if suffix == ".docx":
        text = _read_docx(file_path)
    elif suffix == ".pdf":
        text = _read_pdf(file_path)
    elif suffix == ".txt":
        text = file_path.read_text(encoding="utf-8", errors="ignore")
    else:
        raise ValueError("Upload a PDF, DOCX, or TXT file.")
    if not text.strip():
        raise ValueError("No text could be read from that CV.")
    return parse_cv_text(text)


def parse_cv_text(text: str) -> ParsedCV:
    lines = [_clean_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]
    email = _first(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "\n".join(lines))
    phone = _first(r"\+\d{1,3}(?:[\s().-]*\d){6,14}", "\n".join(lines))
    sections = _sections(lines)
    preamble = sections.get("preamble", [])
    name = next((line for line in preamble if _looks_like_name(line)), "")
    headline = _headline(preamble, name, email)
    roles = _roles(headline, sections.get("experience", []))
    skills = _skills("\n".join(lines), sections.get("skills", []), sections.get("interests", []))
    experience = _experience_level("\n".join(lines), roles)
    location = _location(lines[:25])
    focus = _focus(sections, roles, skills)
    return ParsedCV(
        name=name,
        email=email,
        phone=phone,
        location=location,
        roles=roles,
        skills=skills,
        experience=experience,
        focus=focus,
    )


def _focus(sections: dict[str, list[str]], roles: list[str], skills: list[str]) -> str:
    chunks: list[str] = []
    if roles:
        chunks.append("Roles: " + ", ".join(roles) + ".")
    summary = " ".join(sections.get("summary", [])[:3]).strip()
    if summary:
        chunks.append(summary)
    interests = " ".join(sections.get("interests", [])[:8]).strip()
    if interests:
        chunks.append("Interests: " + interests)
    if skills:
        chunks.append("Skills: " + ", ".join(skills) + ".")
    recent = " ".join(sections.get("experience", [])[:6]).strip()
    if recent:
        chunks.append("Recent work: " + recent)
    return " ".join(chunks)[:1500]


def _sections(lines: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {"preamble": []}
    current = "preamble"
    for line in lines:
        kind = _heading_name(line)
        if kind:
            current = kind
            sections.setdefault(current, [])
            continue
        sections.setdefault(current, []).append(line)
    return sections


def _heading_name(line: str) -> str | None:
    raw = line.strip().strip(":").strip()
    if not raw or len(raw) > 48:
        return None
    cleaned = re.sub(r"[^a-z& ]", "", raw.lower())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if cleaned in HEADINGS:
        return HEADINGS[cleaned]
    if "interest" in cleaned and len(cleaned.split()) <= 4:
        return "interests"
    return None


def _headline(preamble: list[str], name: str, email: str) -> str:
    seen_name = name == ""
    for line in preamble:
        if not seen_name:
            if line == name:
                seen_name = True
            continue
        if _is_contact_line(line, email):
            continue
        return line
    return ""


def _roles(headline: str, experience_lines: list[str]) -> list[str]:
    roles: list[str] = []
    if headline:
        pieces = re.split(r"\s*[/|•·]\s*", headline)
        roles.extend(_clean_role(piece) for piece in pieces)
    if not any(roles):
        for line in experience_lines:
            if line.startswith(("-", "•", "▸", "–")):
                continue
            title = re.split(r"\s+[—–-]\s+|,", line, maxsplit=1)[0]
            cleaned = _clean_role(title)
            if cleaned:
                roles.append(cleaned)
                break
    unique: list[str] = []
    seen: set[str] = set()
    for role in roles:
        if not role:
            continue
        key = role.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(role)
    return unique[:4]


def _clean_role(value: str) -> str:
    role = re.sub(r"\s+", " ", value).strip(" -–—,;:")
    if not role or len(role) > 48 or len(role.split()) > 6:
        return ""
    if "@" in role or "http" in role.lower():
        return ""
    return role


def _skills(full_text: str, skill_lines: list[str], interest_lines: list[str]) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()

    def add(skill: str) -> None:
        cleaned = re.sub(r"\s+", " ", skill).strip(" -–—,;:.")
        key = cleaned.casefold()
        if not cleaned or key in seen or key in SKIP_PHRASES:
            return
        if len(cleaned) > 42 or len(cleaned.split()) > 5:
            return
        seen.add(key)
        found.append(cleaned)

    folded = full_text.lower()
    for term in sorted(LEXICON, key=len, reverse=True):
        if _contains_term(folded, term.lower()):
            add(term)
    for line in skill_lines + interest_lines:
        for phrase in _explode_phrases(line):
            add(phrase)
    return found[:12]


def _explode_phrases(line: str) -> list[str]:
    text = line.replace(";", ",").replace("|", ",").replace("/", ",")
    text = re.sub(r"[•·●◆▸]", ",", text)
    chunks = re.split(r",|\(|\)|:|\n", text)
    phrases: list[str] = []
    for chunk in chunks:
        chunk = chunk.strip(" .-–—")
        if not chunk:
            continue
        parts = re.split(r"\s+&\s+|\s+and\s+", chunk)
        if len(parts) > 1 and all(0 < len(part.split()) <= 4 for part in parts):
            phrases.extend(part.strip() for part in parts)
        else:
            phrases.append(chunk)
    return phrases


def _experience_level(text: str, roles: list[str]) -> str:
    blob = text.lower()
    role_blob = " ".join(roles).lower()
    if re.search(r"\b(intern|internship)\b", role_blob):
        return "Intern"
    if re.search(r"\b(lead|principal|head|director)\b", role_blob):
        return "Lead"
    if re.search(r"\b(senior|staff)\b", role_blob) or re.search(r"\bph\.?d\b|\bdoctorate\b", blob):
        return "Senior"
    if re.search(r"\bm\.?\s?sc\b|\bmsc\b|\bmaster\b|\bmba\b", blob):
        return "Mid"
    years = [int(year) for year in re.findall(r"\b(?:19|20)\d{2}\b", blob)]
    span = max(years) - min(years) if len(years) >= 2 else 0
    if span >= 6:
        return "Senior"
    if span >= 2:
        return "Mid"
    return "Junior"


def _location(lines: list[str]) -> str:
    for line in lines:
        parts = re.split(r"\s*[·•|]\s*", line)
        for part in parts:
            candidate = part.strip(" -")
            if "," not in candidate or len(candidate) > 48:
                continue
            lowered = candidate.lower()
            if "@" in candidate or "http" in lowered or "linkedin" in lowered or "github" in lowered:
                continue
            if re.search(r"\d{3,}", candidate):
                continue
            return candidate
    return ""


def _looks_like_name(line: str) -> bool:
    if "@" in line or len(line) > 60 or any(mark in line for mark in "|•·"):
        return False
    words = re.findall(r"[A-Za-z][A-Za-z'`.-]*", line)
    if not 2 <= len(words) <= 5:
        return False
    return all(word[0].isupper() for word in words)


def _is_contact_line(line: str, email: str) -> bool:
    lowered = line.lower()
    if email and email in line:
        return True
    if "@" in line or "linkedin.com" in lowered or "github.com" in lowered:
        return True
    if re.search(r"\+\d", line):
        return True
    return lowered in {"contact", "contacts"}


def _contains_term(haystack: str, term: str) -> bool:
    if " " in term:
        return term in haystack
    return re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", haystack) is not None


def _first(pattern: str, text: str) -> str:
    match = re.search(pattern, text)
    return re.sub(r"\s+", " ", match.group(0)).strip() if match else ""


def _clean_line(line: str) -> str:
    return re.sub(r"\s+", " ", line.replace("\xa0", " ")).strip()


def _read_docx(path: Path) -> str:
    lines: list[str] = []
    with zipfile.ZipFile(path) as archive:
        names = [
            name
            for name in archive.namelist()
            if name == "word/document.xml" or name.startswith("word/header") or name.startswith("word/footer")
        ]
        names.sort(key=lambda name: (name != "word/document.xml", name))
        for name in names:
            if not name.endswith(".xml"):
                continue
            lines.extend(_docx_xml_lines(archive.read(name)))
    return "\n".join(lines)


def _docx_xml_lines(payload: bytes) -> list[str]:
    root = ElementTree.fromstring(payload)
    lines: list[str] = []
    for paragraph in root.iter(W_NS + "p"):
        text = "".join(node.text or "" for node in paragraph.iter(W_NS + "t")).strip()
        if text:
            lines.append(text)
    return lines


def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)
