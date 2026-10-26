"""The guided CV builder: assembling a first CV from structured Q&A answers, no AI, nothing invented."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from tracker.models import CVVersion, UserProfile
from tracker.services import cvbuilder
from tracker.services.cvversions import CVError

User = get_user_model()
PW = "correct-horse-battery-staple"

FULL = {
    "full_name": "Jane Doe",
    "email": "jane@example.com",
    "phone": "+1 555 0100",
    "location": "Dhaka, Bangladesh",
    "links": ["linkedin.com/in/janedoe", ""],
    "summary": "Backend engineer with 5 years building APIs.",
    "skills": ["C#", "SQL Server", "", "Docker"],
    "experience": [
        {"company": "Acme", "role": "Backend Engineer", "start": "2021", "end": "Present", "bullets": ["Built the payments API", "Led a team of 3"]},
        {"company": "", "role": "", "start": "", "end": "", "bullets": []},  # a blank row the UI may still submit
    ],
    "education": [{"school": "Dhaka University", "degree": "BSc Computer Science", "start": "2015", "end": "2019"}],
    "projects": [{"name": "Open-source scheduler", "description": "A cron-like job runner in Go."}],
    "certifications": ["AWS Certified Developer", ""],
}


class AssembleMarkdown(TestCase):
    def test_full_answers_produce_every_section_in_order(self):
        md = cvbuilder.assemble_markdown(FULL)
        self.assertTrue(md.startswith("# Jane Doe"))
        for expected in ("## Summary", "## Skills", "## Experience", "## Education", "## Projects", "## Certifications"):
            self.assertIn(expected, md)
        self.assertLess(md.index("## Summary"), md.index("## Skills"))
        self.assertLess(md.index("## Experience"), md.index("## Education"))
        self.assertIn("jane@example.com", md)
        self.assertIn("linkedin.com/in/janedoe", md)
        self.assertIn("Backend Engineer — Acme", md)
        self.assertIn("- Built the payments API", md)
        self.assertIn("C#, SQL Server, Docker", md)  # blank skill dropped, no double comma
        self.assertIn("AWS Certified Developer", md)

    def test_blank_experience_row_is_dropped_not_rendered_as_an_empty_header(self):
        md = cvbuilder.assemble_markdown(FULL)
        experience_block = md.split("## Experience", 1)[1].split("## Education", 1)[0]
        self.assertEqual(experience_block.count("**"), 2)  # exactly one bold header (open+close); the blank row emits nothing

    def test_a_name_is_required(self):
        with self.assertRaises(CVError):
            cvbuilder.assemble_markdown({**FULL, "full_name": ""})

    def test_minimal_answers_give_just_the_name(self):
        md = cvbuilder.assemble_markdown({"full_name": "Jane Doe"})
        self.assertEqual(md.strip(), "# Jane Doe")

    def test_empty_optional_sections_are_omitted_entirely(self):
        md = cvbuilder.assemble_markdown({"full_name": "Jane Doe", "summary": "", "skills": [], "experience": []})
        for absent in ("## Summary", "## Skills", "## Experience", "## Education", "## Projects", "## Certifications"):
            self.assertNotIn(absent, md)


class BuildAndSave(TestCase):
    def setUp(self):
        self.u = User.objects.create_user("jane", password=PW)

    def test_saves_as_profile_cv_and_a_master_version(self):
        version = cvbuilder.build_and_save(self.u, FULL)
        self.assertEqual(version.kind, "master")
        self.assertEqual(version.label, "Built from questions")
        self.assertTrue(version.approved)
        self.assertEqual(UserProfile.objects.get(user=self.u).profile_cv, version.content)
        self.assertEqual(CVVersion.objects.filter(owner=self.u, kind="master").count(), 1)

    def test_building_again_adds_a_new_version_not_a_duplicate(self):
        cvbuilder.build_and_save(self.u, FULL)
        cvbuilder.build_and_save(self.u, {**FULL, "summary": "A different summary."})
        self.assertEqual(CVVersion.objects.filter(owner=self.u, kind="master").count(), 2)

    def test_building_the_same_answers_twice_does_not_duplicate(self):
        cvbuilder.build_and_save(self.u, FULL)
        cvbuilder.build_and_save(self.u, FULL)
        self.assertEqual(CVVersion.objects.filter(owner=self.u, kind="master").count(), 1)

    def test_no_name_raises_and_saves_nothing(self):
        with self.assertRaises(CVError):
            cvbuilder.build_and_save(self.u, {"full_name": ""})
        self.assertFalse(CVVersion.objects.filter(owner=self.u).exists())
        self.assertEqual(UserProfile.objects.get(user=self.u).profile_cv, "")
