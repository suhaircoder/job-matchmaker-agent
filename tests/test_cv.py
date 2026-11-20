import unittest
from pathlib import Path

from job_matchmaker.cv_parser import parse_cv_text, read_cv
from job_matchmaker.fetcher import load_sample_jobs, query_from_profile
from job_matchmaker.matcher import rank_jobs
from job_matchmaker.models import UserProfile

CV_TEXT = """
Suhair Ali Ahmed Ghaleb
AI Researcher | Computer Vision | Multimodal Generative AI
Rostov-on-Don, Russia · +7 960 000 00 00 · person@example.com · linkedin.com/in/example
Summary
An AI researcher working on computer vision and generative models.
Research Interests
- Computer Vision
- Generative AI
- Deep Learning
Education:
MSc, Applied Informatics — Don State Technical University (2024–2026)
Technical Skills:
- Machine Learning & Computer Vision: 3D Morphable Models, audio-visual synchronization (SadTalker, Wav2Lip).
- Programming: Python, FastAPI, React
- Data Analysis and Experimental Design.
Professional Experience:
Master's Researcher, AI & Talking Face Systems, Don State Technical University (2024–2026)
Logistics Manager, Touch Logistics Company, Yemen
"""

PERSONAL_CV = Path(r"d:\my cv\CVSS\my cv for testing agent.docx")


class CVParserTests(unittest.TestCase):
    def test_text_cv_fills_profile_fields(self):
        parsed = parse_cv_text(CV_TEXT)
        self.assertEqual(parsed.name, "Suhair Ali Ahmed Ghaleb")
        self.assertEqual(parsed.email, "person@example.com")
        self.assertIn("Rostov-on-Don", parsed.location)
        self.assertEqual(parsed.roles[0], "AI Researcher")
        self.assertIn("Computer Vision", parsed.roles)
        self.assertIn("Python", parsed.skills)
        self.assertIn("FastAPI", parsed.skills)
        self.assertIn("Computer Vision", parsed.skills)
        self.assertIn("Machine Learning", parsed.skills)
        self.assertIn("Python", parsed.focus)
        self.assertIn("Computer Vision", parsed.focus)
        self.assertNotIn("Logistics Manager", parsed.roles)
        self.assertEqual(parsed.experience, "Mid")

    def test_cv_profile_prefers_vision_work_over_unrelated_jobs(self):
        parsed = parse_cv_text(CV_TEXT)
        profile = UserProfile(
            name=parsed.name,
            email=parsed.email,
            phone="",
            location=parsed.location,
            roles=parsed.roles,
            skills=parsed.skills,
            experience=parsed.experience,
            sources=["Sample board"],
            top_n=5,
        )
        ranked = rank_jobs(profile, load_sample_jobs(), limit=len(load_sample_jobs()))
        scores = {match.job.id: match.score for match in ranked}
        self.assertIn(ranked[0].job.id, {"sample-cv-engineer", "sample-ml-engineer", "sample-genai"})
        self.assertGreater(scores["sample-cv-engineer"], scores["sample-accountant"])
        self.assertGreater(scores["sample-cv-engineer"], scores["sample-marketing"])

    def test_search_query_uses_computer_vision_when_the_cv_has_it(self):
        parsed = parse_cv_text(CV_TEXT)
        self.assertEqual(query_from_profile(parsed.roles, parsed.skills), "computer vision")

    def test_real_docx_cv_when_it_is_on_this_machine(self):
        if not PERSONAL_CV.exists():
            self.skipTest("personal CV is not on this machine")
        parsed = read_cv(PERSONAL_CV)
        self.assertGreaterEqual(len(parsed.name.split()), 2)
        self.assertIn("@", parsed.email)
        self.assertIn("Python", parsed.skills)
        self.assertIn("Computer Vision", parsed.skills)
        self.assertEqual(parsed.experience, "Mid")
        self.assertTrue(parsed.location)
