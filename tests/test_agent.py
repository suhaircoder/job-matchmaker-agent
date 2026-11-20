import tempfile
import unittest
from pathlib import Path

from job_matchmaker.fetcher import html_to_text, load_sample_jobs, parse_job_html
from job_matchmaker.matcher import rank_jobs
from job_matchmaker.models import UserProfile
from job_matchmaker.notifier import write_notification
from job_matchmaker.paths import DATA
from job_matchmaker.render import render_plain
from job_matchmaker.store import PROFILE_PATH, load_profiles, save_profile


def profile(**overrides) -> UserProfile:
    data = {
        "name": "Ayesha Khan",
        "email": "ayesha@example.com",
        "phone": "",
        "location": "Lahore, Pakistan",
        "roles": ["Python Developer"],
        "skills": ["Python", "Django", "REST APIs", "PostgreSQL", "Git"],
        "experience": "Mid",
        "sources": ["Sample board"],
        "top_n": 6,
    }
    data.update(overrides)
    return UserProfile(**data)


class MatcherTests(unittest.TestCase):
    def setUp(self):
        self.jobs = load_sample_jobs()

    def test_lahore_python_prefers_local_backend(self):
        matches = rank_jobs(profile(), self.jobs, limit=5)
        self.assertEqual(matches[0].job.id, "sample-python-backend")
        self.assertGreater(matches[0].score, 0.85)

    def test_remote_analyst_prefers_remote_listing(self):
        person = profile(
            name="Bilal Ahmed",
            email="bilal@example.com",
            location="Remote",
            roles=["Data Analyst"],
            skills=["SQL", "Excel", "Python", "Tableau", "statistics"],
            experience="Junior",
        )
        matches = rank_jobs(person, self.jobs, limit=5)
        self.assertEqual(matches[0].job.id, "sample-data-analyst-remote")

    def test_karachi_analyst_prefers_karachi_listing(self):
        person = profile(
            location="Karachi, Pakistan",
            roles=["Data Analyst"],
            skills=["SQL", "Excel", "Python", "Tableau", "statistics"],
        )
        matches = rank_jobs(person, self.jobs, limit=3)
        self.assertEqual(matches[0].job.id, "sample-data-analyst-khi")

    def test_frontend_outranks_accountant(self):
        person = profile(
            name="Sara Malik",
            location="Karachi, Pakistan",
            roles=["Frontend Engineer"],
            skills=["JavaScript", "React", "CSS", "HTML", "TypeScript"],
        )
        ranked = rank_jobs(person, self.jobs, limit=len(self.jobs))
        scores = {match.job.id: match.score for match in ranked}
        self.assertEqual(ranked[0].job.id, "sample-frontend")
        self.assertGreater(scores["sample-frontend"], scores["sample-accountant"])
        self.assertGreater(scores["sample-frontend"], scores["sample-marketing"])

    def test_a_close_meaning_can_outrank_keyword_overlap(self):
        person = profile()
        jobs = load_sample_jobs()
        semantic = {job.id: 0.05 for job in jobs}
        semantic["sample-accountant"] = 0.98
        semantic["sample-python-backend"] = 0.05
        top = rank_jobs(person, jobs, limit=1, semantic=semantic)
        self.assertEqual(top[0].job.id, "sample-accountant")

    def test_scores_stay_in_range_for_an_empty_profile(self):
        person = profile(name="", email="", location="", roles=[], skills=[])
        matches = rank_jobs(person, self.jobs, limit=5)
        self.assertEqual(len(matches), 5)
        self.assertTrue(all(0 <= match.score <= 1 for match in matches))


class FetcherTests(unittest.TestCase):
    def test_sample_board_loads(self):
        jobs = load_sample_jobs()
        self.assertGreaterEqual(len(jobs), 15)
        self.assertTrue(all(job.source == "Sample board" for job in jobs))

    def test_local_html_board_is_parsed(self):
        jobs = parse_job_html((DATA / "local_board.html").read_text(encoding="utf-8"))
        titles = {job.title for job in jobs}
        self.assertIn("Django Developer", titles)
        self.assertIn("UI Engineer", titles)
        self.assertTrue(all(job.source == "Local HTML board" for job in jobs))

    def test_html_description_is_plain_text(self):
        text = html_to_text("<p>Hello <b>team</b></p>")
        self.assertNotIn("<p>", text)
        self.assertIn("Hello", text)
        self.assertIn("team", text)

    def test_empty_html_returns_no_jobs(self):
        self.assertEqual(parse_job_html("<html><body><p>Nothing here</p></body></html>"), [])


class NotificationTests(unittest.TestCase):
    def test_shortlist_file_contains_title_company_and_link(self):
        person = profile()
        matches = rank_jobs(person, load_sample_jobs(), limit=3)
        with tempfile.TemporaryDirectory() as folder:
            path = write_notification(person, matches, Path(folder))
            text = path.read_text(encoding="utf-8")
        self.assertIn("Python Backend Developer", text)
        self.assertIn("Northwind Labs", text)
        self.assertIn("https://example.com/jobs/northwind-python-backend", text)
        self.assertIn("Apply:", text)
        self.assertEqual(text, render_plain(person, matches))

    def test_saved_profile_round_trip(self):
        person = profile(email="roundtrip@example.com")
        original = PROFILE_PATH
        with tempfile.TemporaryDirectory() as folder:
            temp_path = Path(folder) / "saved_profiles.json"
            try:
                import job_matchmaker.store as store

                store.PROFILE_PATH = temp_path
                note = save_profile(person, notify_email=True, notify_whatsapp=False)
                self.assertIn("Saved", note)
                loaded = load_profiles()
            finally:
                store.PROFILE_PATH = original
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["email"], "roundtrip@example.com")
        self.assertEqual(loaded[0]["skills"][0], "Python")
        self.assertTrue(loaded[0]["notify_email"])
        self.assertFalse(loaded[0]["notify_whatsapp"])


if __name__ == "__main__":
    unittest.main()
