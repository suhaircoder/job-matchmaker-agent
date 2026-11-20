import os

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")
# A local SOCKS proxy on this PC uses a scheme Gradio cannot read.
# Bypass it so `python app.py` can start and the job boards can be reached.
os.environ["NO_PROXY"] = "*"
os.environ["no_proxy"] = "*"

import gradio as gr

from job_matchmaker.cv_parser import read_cv
from job_matchmaker.models import UserProfile
from job_matchmaker.notifier import load_env
from job_matchmaker.render import render_html, render_plain
from job_matchmaker.service import match_profile
from job_matchmaker.store import save_profile

EXAMPLES = {
    "python": (
        "Ayesha Khan",
        "ayesha@example.com",
        "",
        "Lahore, Pakistan",
        "Python Developer",
        "Python, Django, REST APIs, PostgreSQL, Git",
        "Python backend developer building REST APIs with Django and PostgreSQL in Lahore.",
        "Mid",
    ),
    "analyst": (
        "Bilal Ahmed",
        "bilal@example.com",
        "",
        "Remote",
        "Data Analyst",
        "SQL, Excel, Python, Tableau, statistics",
        "Remote data analyst who works in SQL, Excel, Python, Tableau, and statistics.",
        "Junior",
    ),
    "frontend": (
        "Sara Malik",
        "sara@example.com",
        "",
        "Karachi, Pakistan",
        "Frontend Engineer",
        "JavaScript, React, CSS, HTML, TypeScript",
        "Frontend engineer in Karachi building interfaces with JavaScript, React, CSS, HTML, and TypeScript.",
        "Mid",
    ),
}

THEME = gr.themes.Soft(primary_hue="green", neutral_hue="stone").set(
    body_background_fill="#f4f0e6",
    block_background_fill="#fffdf8",
    block_border_color="#e4ddd0",
    block_label_text_color="#3a342c",
    body_text_color="#1c1915",
    button_primary_background_fill="#0f6e56",
    button_primary_background_fill_hover="#0c5b48",
    button_primary_text_color="#ffffff",
    input_background_fill="#fffdf8",
)

CSS = """
.gradio-container { max-width: 1120px !important; }
.job-card {
  background: #fffdf8;
  border: 1px solid #e4ddd0;
  border-left: 6px solid #8a8175;
  border-radius: 14px;
  padding: 14px 16px 12px;
  margin: 0 0 12px;
}
.job-high { border-left-color: #0f6e56; }
.job-mid { border-left-color: #a16207; }
.job-low { border-left-color: #8a8175; }
.job-top { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
.job-kicker { font-size: 12px; letter-spacing: 0.05em; text-transform: uppercase; color: #6d655c; }
.job-title { font-family: Georgia, "Times New Roman", serif; font-size: 22px; line-height: 1.2; margin: 4px 0; color: #1c1915; }
.job-meta, .job-why, .attribution, .empty { color: #4e483f; }
.job-score { font-family: Georgia, "Times New Roman", serif; font-size: 28px; line-height: 1; color: #0f6e56; }
.job-copy { color: #1c1915; line-height: 1.45; margin: 10px 0; }
.pill {
  display: inline-block;
  margin: 0 6px 6px 0;
  padding: 3px 8px;
  border-radius: 999px;
  background: #efe8dc;
  color: #3a342c;
  font-size: 12px;
}
.pill-hit { background: #d7efe6; color: #0f6e56; }
.job-link { color: #0f6e56; font-weight: 700; }
#find-button { min-height: 46px; }
"""


def match_from_cv(
    upload,
    name,
    email,
    phone,
    location,
    roles,
    skills,
    focus,
    experience,
    sources,
    top_n,
    save_search,
    send_email,
    send_whatsapp,
):
    path = _upload_path(upload)
    current = (name, email, phone, location, roles, skills, focus, experience)
    if not path:
        return (
            *current,
            "Upload a PDF, DOCX, or TXT CV first.",
            "<p class='empty'>Add a CV, then match again.</p>",
            "",
        )
    try:
        parsed = read_cv(path)
    except Exception as exc:
        return (
            *current,
            f"Could not read that CV. {exc}",
            "<p class='empty'>The CV could not be read.</p>",
            "",
        )
    status, html, draft = find_matches(
        parsed.name,
        parsed.email,
        parsed.phone,
        parsed.location,
        ", ".join(parsed.roles),
        ", ".join(parsed.skills),
        parsed.focus,
        parsed.experience,
        sources,
        top_n,
        save_search,
        send_email,
        send_whatsapp,
    )
    return (
        parsed.name,
        parsed.email,
        parsed.phone,
        parsed.location,
        ", ".join(parsed.roles),
        ", ".join(parsed.skills),
        parsed.focus,
        parsed.experience,
        parsed.note() + "\n\n" + status,
        html,
        draft,
    )


def _upload_path(upload) -> str:
    if isinstance(upload, (list, tuple)):
        upload = upload[0] if upload else None
    if upload is None:
        return ""
    if isinstance(upload, str):
        return upload
    return str(getattr(upload, "name", "") or "")


def find_matches(
    name,
    email,
    phone,
    location,
    roles,
    skills,
    focus,
    experience,
    sources,
    top_n,
    save_search,
    send_email,
    send_whatsapp,
):
    load_env()
    if not sources:
        return "Select at least one job board.", "<p class='empty'>Nothing to search yet.</p>", ""
    profile = UserProfile.from_form(
        name, email, phone, location, roles, skills, experience, sources, top_n, summary=focus
    )
    try:
        fetched, matches = match_profile(profile)
        notes = list(fetched.notes)
        if save_search:
            notes.append(save_profile(profile, notify_email=bool(send_email), notify_whatsapp=bool(send_whatsapp)))
        notes.extend(
            deliver_safely(profile, matches, email=bool(send_email), whatsapp=bool(send_whatsapp))
        )
        return _status(matches, len(fetched.jobs), notes), render_html(matches), render_plain(profile, matches)
    except Exception as exc:
        return f"Search failed: {exc}", "<p class='empty'>The search did not finish.</p>", ""


def deliver_safely(profile, matches, *, email: bool, whatsapp: bool):
    from job_matchmaker.notifier import deliver

    return deliver(profile, matches, email=email, whatsapp=whatsapp)


def _status(matches, considered: int, notes: list[str]) -> str:
    count = len(matches)
    word = "match" if count == 1 else "matches"
    headline = f"**{count} {word}** from {considered} listings."
    if matches and matches[0].score < 0.45:
        headline += " The overlap is weak, so read this as a loose suggestion."
    details = "\n".join(f"- {note}" for note in notes)
    return f"{headline}\n\n{details}"


def build_demo() -> gr.Blocks:
    with gr.Blocks(title="Job Matchmaker Agent") as demo:
        gr.Markdown(
            """
# Job Matchmaker Agent
Upload a CV. The agent compares what the CV says you do with each job, then ranks the closest real listings first.
            """.strip()
        )
        with gr.Row():
            with gr.Column(scale=4):
                gr.Markdown("### Your CV")
                cv_file = gr.File(
                    label="Upload a CV",
                    file_types=[".pdf", ".docx", ".txt"],
                    type="filepath",
                )
                match_cv_btn = gr.Button("Match jobs to this CV", variant="primary", elem_id="match-cv-button")
                gr.Markdown("### Profile read from the CV")
                name = gr.Textbox(label="Name", value="")
                email = gr.Textbox(label="Email", value="")
                phone = gr.Textbox(label="WhatsApp number", value="", placeholder="+923001234567")
                location = gr.Textbox(label="Location", value="", placeholder="City, Country or Remote")
                roles = gr.Textbox(label="Preferred job roles", value="", placeholder="Filled from the CV headline")
                skills = gr.Textbox(label="Skills", lines=3, value="", placeholder="Filled from the CV")
                focus = gr.Textbox(
                    label="What to match",
                    lines=4,
                    value="",
                    placeholder="Filled from the CV. Each job is compared with this text.",
                )
                experience = gr.Dropdown(
                    label="Experience",
                    choices=["Intern", "Junior", "Mid", "Senior", "Lead"],
                    value="Mid",
                )
                sources = gr.CheckboxGroup(
                    label="Preferred job boards",
                    choices=[
                        "Remotive",
                        "Jobicy",
                        "Remote OK",
                        "Himalayas",
                        "Working Nomads",
                        "Sample board",
                        "Local HTML board",
                    ],
                    value=["Remotive", "Jobicy", "Remote OK", "Himalayas", "Working Nomads"],
                    info="Live boards are searched first. The sample boards are practice data for offline demos.",
                )
                top_n = gr.Slider(label="How many matches", minimum=3, maximum=12, value=6, step=1)
                save_search = gr.Checkbox(label="Save this search for the daily run")
                send_email = gr.Checkbox(label="Email the shortlist")
                send_whatsapp = gr.Checkbox(label="WhatsApp the shortlist")
                with gr.Row():
                    python_btn = gr.Button("Python example")
                    analyst_btn = gr.Button("Data analyst example")
                    frontend_btn = gr.Button("Frontend example")
                find_btn = gr.Button("Find matching jobs", elem_id="find-button")
            with gr.Column(scale=6):
                status = gr.Markdown(
                    "Upload a CV and match. The percentage is how close the job is to your CV. Strong matches are 75% or higher."
                )
                results = gr.HTML(elem_id="job-results")
                draft = gr.Textbox(label="Notification draft", lines=16)

        with gr.Accordion("Daily run and email setup", open=False):
            gr.Markdown(
                """
Copy `.env.example` to `.env` before email or WhatsApp will send.
Until then, every search still writes the shortlist into `notifications/`.

Saved searches live in `data/saved_profiles.json`.

- Run them once: `python run_saved.py`
- Leave a daily timer running: `python run_saved.py --loop`
- Or point Windows Task Scheduler, cron, or cron-job.org at `python run_saved.py`

Practice listings use example.com and are not real openings. Live listings open on Remotive or Jobicy.
                """.strip()
            )

        fields = [name, email, phone, location, roles, skills, focus, experience]
        search_inputs = fields + [sources, top_n, save_search, send_email, send_whatsapp]
        python_btn.click(lambda: EXAMPLES["python"], outputs=fields)
        analyst_btn.click(lambda: EXAMPLES["analyst"], outputs=fields)
        frontend_btn.click(lambda: EXAMPLES["frontend"], outputs=fields)
        match_cv_btn.click(
            match_from_cv,
            inputs=[cv_file, *search_inputs],
            outputs=fields + [status, results, draft],
        )
        find_btn.click(
            find_matches,
            inputs=search_inputs,
            outputs=[status, results, draft],
        )
    return demo


demo = build_demo()


if __name__ == "__main__":
    demo.launch(
        server_name="127.0.0.1",
        server_port=int(os.getenv("PORT", "7860")),
        inbrowser=False,
        theme=THEME,
        css=CSS,
    )
