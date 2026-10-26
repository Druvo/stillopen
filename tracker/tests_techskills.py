"""O*NET-grounded recognized technologies -- a real named-tool vocabulary, not generic word frequency."""
from django.test import SimpleTestCase

from tracker.services import techskills


class Recognized(SimpleTestCase):
    def test_finds_real_named_technologies_not_generic_words(self):
        posting = "We need a backend engineer who knows Docker, Kubernetes and React. Great team culture!"
        out = techskills.recognized(posting, cv_text="")
        names = {r["name"] for r in out}
        self.assertEqual(names, {"Docker", "Kubernetes", "React"})
        self.assertNotIn("team", names)
        self.assertNotIn("culture", names)

    def test_marks_which_ones_the_candidates_own_material_already_covers(self):
        posting = "Docker, Kubernetes and Git experience required."
        out = techskills.recognized(posting, cv_text="I have used Docker extensively.")
        by_name = {r["name"]: r for r in out}
        self.assertTrue(by_name["Docker"]["have"])
        self.assertFalse(by_name["Kubernetes"]["have"])
        self.assertFalse(by_name["Git"]["have"])

    def test_empty_when_the_posting_names_nothing_recognized(self):
        self.assertEqual(techskills.recognized("Sales operations role, quotas and forecasting.", ""), [])
        self.assertEqual(techskills.recognized("", "Docker"), [])

    def test_hot_in_demand_technologies_sort_first(self):
        out = techskills.recognized("Uses Docker and PuTTY.", "")
        self.assertEqual(out[0]["name"], "Docker")
        self.assertTrue(out[0]["hot"])

    def test_known_ambiguous_short_tokens_are_excluded(self):
        # "Go" and "R" are real O*NET entries but also ordinary English words -- dropped from the bundled catalog.
        posting = "Please go to the office and R.S.V.P. before Friday; we may go over budget."
        self.assertEqual(techskills.recognized(posting, ""), [])

    def test_capped_at_a_dozen(self):
        many = ", ".join(name for name, _ in techskills._catalog()[:30])
        out = techskills.recognized(many, "")
        self.assertLessEqual(len(out), techskills.MAX_RECOGNIZED)
