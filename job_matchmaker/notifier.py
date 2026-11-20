from __future__ import annotations

import os
import re
import smtplib
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

import requests
from dotenv import load_dotenv

from job_matchmaker.models import Match, UserProfile
from job_matchmaker.paths import NOTIFICATIONS, ROOT
from job_matchmaker.render import render_plain, render_short


def load_env() -> None:
    load_dotenv(ROOT / ".env")


def write_notification(
    profile: UserProfile,
    matches: list[Match],
    directory: Path | None = None,
) -> Path:
    folder = directory or NOTIFICATIONS
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    slug = re.sub(r"[^a-z0-9]+", "-", profile.name.lower()).strip("-") or "search"
    path = folder / f"{stamp}-{slug}.txt"
    path.write_text(render_plain(profile, matches), encoding="utf-8")
    return path


def deliver(
    profile: UserProfile,
    matches: list[Match],
    *,
    email: bool,
    whatsapp: bool,
    directory: Path | None = None,
) -> list[str]:
    load_env()
    path = write_notification(profile, matches, directory)
    try:
        shown = path.relative_to(ROOT)
    except ValueError:
        shown = path
    notes = [f"Shortlist saved to `{shown.as_posix()}`."]
    if email:
        notes.append(send_email(profile, matches))
    if whatsapp:
        notes.append(send_whatsapp(profile, matches))
    return notes


def send_email(profile: UserProfile, matches: list[Match]) -> str:
    load_env()
    if "@" not in profile.email:
        return "Add an email address before sending the shortlist."
    host = os.getenv("SMTP_HOST", "").strip()
    user = os.getenv("SMTP_USER", "").strip()
    password = os.getenv("SMTP_PASSWORD", "").strip()
    sender = os.getenv("SMTP_FROM", "").strip() or user
    port = _port(os.getenv("SMTP_PORT", "587"))
    if not host or not user or not password or not sender:
        return "Email needs SMTP_HOST, SMTP_USER, and SMTP_PASSWORD in .env. The file copy is saved."

    message = EmailMessage()
    message["Subject"] = f"Jobs that match your profile, {profile.name or 'job search'}".strip()
    message["From"] = sender
    message["To"] = profile.email
    message.set_content(render_plain(profile, matches))
    try:
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20) as server:
                server.login(user, password)
                server.send_message(message)
        else:
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.starttls()
                server.login(user, password)
                server.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        return f"Email could not be sent ({exc.__class__.__name__}). The file copy is saved."
    return f"Email sent to {profile.email}."


def send_whatsapp(profile: UserProfile, matches: list[Match]) -> str:
    load_env()
    phone = _normalize_phone(profile.phone)
    if not phone:
        return "Add a WhatsApp number with the country code, for example +923001234567."
    sid = os.getenv("TWILIO_ACCOUNT_SID", "").strip()
    token = os.getenv("TWILIO_AUTH_TOKEN", "").strip()
    sender = os.getenv("TWILIO_WHATSAPP_FROM", "").strip()
    if not sid or not token or not sender:
        return "WhatsApp needs TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, and TWILIO_WHATSAPP_FROM in .env."
    if not sender.startswith("whatsapp:"):
        sender = f"whatsapp:{sender}"
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    try:
        response = requests.post(
            url,
            data={"From": sender, "To": f"whatsapp:{phone}", "Body": render_short(profile, matches)},
            auth=(sid, token),
            timeout=20,
        )
    except requests.RequestException:
        return "WhatsApp could not be sent because Twilio did not respond. The file copy is saved."
    if response.status_code >= 400:
        return "WhatsApp was refused by Twilio. Check the sandbox number and your .env values."
    return f"WhatsApp message sent to {phone}."


def _normalize_phone(phone: str) -> str:
    raw = phone.strip()
    if raw.lower().startswith("whatsapp:"):
        raw = raw.split(":", 1)[1]
    digits = re.sub(r"[^\d+]", "", raw)
    if not digits:
        return ""
    if not digits.startswith("+"):
        digits = "+" + digits
    return digits


def _port(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 587
