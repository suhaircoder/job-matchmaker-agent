"""Print ranked jobs for three sample people. This is the offline test from the brief."""

from __future__ import annotations

from job_matchmaker.fetcher import load_local_html_jobs, load_sample_jobs
from job_matchmaker.matcher import rank_jobs
from job_matchmaker.models import UserProfile


CASES = [
    {
        "name": "Ayesha Khan",
        "email": "ayesha@example.com",
        "location": "Lahore, Pakistan",
        "roles": ["Python Developer"],
        "skills": ["Python", "Django", "REST APIs", "PostgreSQL", "Git"],
        "experience": "Mid",
    },
    {
        "name": "Bilal Ahmed",
        "email": "bilal@example.com",
        "location": "Remote",
        "roles": ["Data Analyst"],
        "skills": ["SQL", "Excel", "Python", "Tableau", "statistics"],
        "experience": "Junior",
    },
    {
        "name": "Sara Malik",
        "email": "sara@example.com",
        "location": "Karachi, Pakistan",
        "roles": ["Frontend Engineer"],
        "skills": ["JavaScript", "React", "CSS", "HTML", "TypeScript"],
        "experience": "Mid",
    },
]


def main() -> None:
    jobs = load_sample_jobs() + load_local_html_jobs()
    print(f"Loaded {len(jobs)} practice listings.\n")
    for case in CASES:
        profile = UserProfile(
            name=case["name"],
            email=case["email"],
            phone="",
            location=case["location"],
            roles=list(case["roles"]),
            skills=list(case["skills"]),
            experience=case["experience"],
            sources=["Sample board", "Local HTML board"],
            top_n=5,
        )
        matches = rank_jobs(profile, jobs, limit=5)
        print(f"{profile.name} — {', '.join(profile.roles)} — {profile.location}")
        for match in matches:
            job = match.job
            print(f"  {round(match.score * 100):>3}%  {job.title} at {job.company} ({job.location})")
        print()


if __name__ == "__main__":
    main()
