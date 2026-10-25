"""The rule-based ATS check: every check with a pass and a fail fixture, the score, the keyword coverage and odd input (empty, not English)."""
from datetime import date

from django.test import SimpleTestCase

from tracker.services import ats

TODAY = date(2026, 6, 1)

GOOD = """# Jane Doe

jane.doe@example.com · +60 12 345 6789 · Kuala Lumpur, Malaysia
linkedin.com/in/janedoe

## Summary
Backend engineer who builds reliable payment systems.

## Work experience

**Backend Engineer** - Acme Payments, Jan 2022 - Present
- Built payment APIs in Python serving 10,000 merchants.
- Led a team of 4 engineers across two time zones.
- Reduced deployment time from 40 minutes to 8 minutes.
- Mentored two junior developers through their first year.

**Developer** - Globex, Jun 2019 - Dec 2021
- Designed a reporting service used by 300 analysts.
- Migrated 12 services to Docker with no downtime.
- Wrote the onboarding guide for new engineers.

## Education
**BSc Computer Science** - University of Malaya, 2015 - 2019

## Skills
Languages: Python, SQL, C#
Tools: Docker, Git, AWS
"""

BAD = """# Jane Doe
![photo](me.jpg)
Date of birth: 01/02/1990 | Marital status: single
☎ 0123 💼

## My Journey
**Developer** - Globex, 2015 - 2016
- Responsible for the backend.
- I was responsible for many things.
- Responsible for emails and my team.
- Worked on the database.

**Manager** - Acme, January 2019 - Mar. 2020
- Helped with reports.

| Skill | Level |
|-------|-------|
| Python | Expert |

## What I Know
Python, python, SQL, Docker, Kubernetes, Terraform, Ansible, Go, Rust
Page 1 of 2
Curriculum Vitae
Click [here](https://bit.ly/abc) for more. SEO and CRM work.
"""


def by_id(report):
    return {c["id"]: c for c in report["checks"]}


class GoodCv(SimpleTestCase):
    def setUp(self):
        self.r = ats.check_text(GOOD, TODAY)
        self.c = by_id(self.r)

    def test_scores_high_and_has_no_failures(self):
        self.assertGreaterEqual(self.r["readiness"], 90, [(c["id"], c["status"]) for c in self.r["checks"] if c["status"] != "pass"])
        self.assertEqual(self.r["counts"]["fail"], 0)
        self.assertEqual(self.r["label"], "Strong")
        self.assertIn("not a score from any real applicant tracking system", self.r["caveat"])

    def test_every_check_has_the_documented_fields(self):
        for c in self.r["checks"]:
            self.assertEqual(set(c), {"id", "group", "status", "title", "why", "fix", "weight", "lines"})
            self.assertIn(c["status"], ("pass", "warn", "fail"))
            self.assertTrue(c["title"] and c["why"])
            if c["status"] != "pass":
                self.assertTrue(c["fix"], c["id"])

    def test_the_contact_details_pass(self):
        for cid in ("contact_email", "contact_phone", "contact_location", "contact_link", "contact_extras"):
            self.assertEqual(self.c[cid]["status"], "pass", cid)

    def test_dates_order_and_gaps_pass(self):
        self.assertEqual(self.c["dates_format"]["status"], "pass")
        self.assertEqual(self.c["dates_order"]["status"], "pass")
        self.assertEqual(self.c["gaps"]["status"], "pass")

    def test_export_facts_are_stated(self):
        self.assertTrue(self.r["export"]["single_column"] and self.r["export"]["text_based"])
        self.assertFalse(self.r["export"]["tables"] or self.r["export"]["images"])
        self.assertEqual(self.c["export_format"]["weight"], 0)

    def test_weights_are_shown_and_explain_the_score(self):
        total = sum(c["weight"] for c in self.r["checks"])
        points = sum(c["weight"] * {"pass": 1, "warn": 0.5, "fail": 0}[c["status"]] for c in self.r["checks"])
        self.assertEqual(self.r["readiness"], round(100 * points / total))


class BadCv(SimpleTestCase):
    def setUp(self):
        self.r = ats.check_text(BAD, TODAY)
        self.c = by_id(self.r)

    def test_low_score(self):
        self.assertLess(self.r["readiness"], 55)
        self.assertGreater(self.r["counts"]["fail"], 2)

    def test_missing_email_and_other_contact_details(self):
        self.assertEqual(self.c["contact_email"]["status"], "fail")
        self.assertEqual(self.c["contact_location"]["status"], "warn")
        self.assertEqual(by_id(ats.check_text("# A\na@b.co\n\n## Skills\nPython", TODAY))["contact_link"]["status"], "warn")

    def test_photo_age_and_marital_status_fail_with_line_numbers(self):
        c = self.c["contact_extras"]
        self.assertEqual(c["status"], "fail")
        self.assertIn(2, c["lines"])
        self.assertIn(3, c["lines"])

    def test_creative_headings_get_the_standard_name(self):
        c = self.c["sections_names"]
        self.assertEqual(c["status"], "warn")
        self.assertIn("Work experience", c["fix"])
        self.assertIn("Skills", c["fix"])

    def test_missing_core_sections(self):
        # "My Journey" and "What I Know" are not names a parser knows, so no experience, education or skills section is recognised
        self.assertEqual(self.c["sections_present"]["status"], "fail")
        for name in ("Work experience", "Education", "Skills"):
            self.assertIn(name, self.c["sections_present"]["title"])
        self.assertEqual(by_id(ats.check_text(GOOD, TODAY))["sections_present"]["status"], "pass")
        no_edu = ats.check_text(GOOD.replace("## Education\n**BSc Computer Science** - University of Malaya, 2015 - 2019\n", ""), TODAY)
        self.assertEqual(by_id(no_edu)["sections_present"]["status"], "warn")

    def test_no_experience_section_at_all_fails(self):
        r = by_id(ats.check_text("# A B\na@b.co\n\n## Education\nSchool, 2010 - 2014\n- something done here today for you", TODAY))
        self.assertEqual(r["sections_present"]["status"], "fail")

    def test_dates_in_mixed_styles_and_wrong_order(self):
        self.assertEqual(self.c["dates_format"]["status"], "warn")
        self.assertEqual(self.c["dates_order"]["status"], "warn")

    def test_a_gap_over_a_year_is_a_fact_not_a_verdict(self):
        gap = ats.check_text("# A\n\n## Work experience\n**X** - Y, Jan 2018 - Jan 2019\n- Built a thing.\n**X** - Z, Jan 2021 - Present\n- Built another.\n", TODAY)
        c = by_id(gap)["gaps"]
        self.assertEqual(c["status"], "warn")
        self.assertIn("not a verdict", c["why"])
        self.assertIn("12 months", by_id(ats.check_text(GOOD, TODAY))["gaps"]["title"])

    def test_year_only_dates_do_not_invent_a_gap(self):
        r = ats.check_text("# A\n\n## Work experience\n**X** - Y, 2020 - 2021\n- Built a thing.\n**X** - Z, 2022 - 2024\n- Built another.\n", TODAY)
        self.assertEqual(by_id(r)["gaps"]["status"], "pass")

    def test_weak_bullets_first_person_filler(self):
        self.assertIn(self.c["bullets_verb"]["status"], ("warn", "fail"))
        self.assertEqual(self.c["first_person"]["status"], "warn")
        self.assertEqual(self.c["passive"]["status"], "warn")
        self.assertEqual(self.c["bullets_numbers"]["status"], "fail")  # not one number in five bullets

    def test_table_is_a_failure_and_symbols_are_found(self):
        self.assertEqual(self.c["no_tables"]["status"], "fail")
        self.assertEqual(self.c["no_symbols"]["status"], "warn")
        self.assertTrue(self.c["no_symbols"]["lines"])

    def test_header_footer_hints(self):
        self.assertEqual(self.c["no_header_footer"]["status"], "warn")

    def test_skills_listed_twice(self):
        c = by_id(ats.check_text("# A\na@b.co\n\n## Skills\nPython, python, SQL\n", TODAY))["skills_dupes"]
        self.assertEqual(c["status"], "warn")
        self.assertIn("python", c["title"].lower())

    def test_acronyms_and_bad_links(self):
        self.assertEqual(self.c["acronyms"]["status"], "warn")
        self.assertIn("SEO", self.c["acronyms"]["title"])
        self.assertEqual(self.c["links_visible"]["status"], "warn")


class SmallChecks(SimpleTestCase):
    def test_phone_is_not_a_date_range(self):
        r = by_id(ats.check_text("# A\nsomeone@example.com\n2019 - 2022\n\n## Skills\nPython", TODAY))
        self.assertEqual(r["contact_phone"]["status"], "warn")

    def test_length_thresholds(self):
        long_cv = "# A\na@b.co\n\n## Work experience\n" + "\n".join(f"- Built service number {i} that handled many requests for customers every single day." for i in range(110))
        self.assertEqual(by_id(ats.check_text(long_cv, TODAY))["length"]["status"], "warn")
        self.assertEqual(by_id(ats.check_text("# A\na@b.co\nhi", TODAY))["length"]["status"], "warn")

    def test_early_career_over_one_page_warns(self):
        body = "\n".join(f"- Built service number {i} that handled many requests for customers every single day ok." for i in range(55))
        cv = f"# A\na@b.co\n\n## Work experience\n**X** - Y, Jan 2024 - Present\n{body}\n"
        c = by_id(ats.check_text(cv, TODAY))["length"]
        self.assertEqual(c["status"], "warn")
        self.assertIn("early career", c["title"])

    def test_very_long_paragraph(self):
        cv = "# A\na@b.co\n\n## Summary\n" + "word " * 70 + "\n"
        self.assertEqual(by_id(ats.check_text(cv, TODAY))["long_paragraphs"]["status"], "warn")

    def test_repeated_openings(self):
        cv = "# A\na@b.co\n\n## Work experience\n" + "\n".join(f"- Managed thing {i} for the whole team here." for i in range(4)) + "\n"
        self.assertEqual(by_id(ats.check_text(cv, TODAY))["bullets_repeat"]["status"], "warn")

    def test_mojibake_fails_and_mixed_quotes_warn(self):
        self.assertEqual(by_id(ats.check_text("# A\na@b.co\nCafÃ© owner\n", TODAY))["clean_text"]["status"], "fail")
        self.assertEqual(by_id(ats.check_text("# A\na@b.co\nHe said “hi” and \"bye\"\n", TODAY))["clean_text"]["status"], "warn")

    def test_tabs_are_columns(self):
        self.assertEqual(by_id(ats.check_text("# A\na@b.co\nPython\tSQL\n", TODAY))["no_columns"]["status"], "warn")

    def test_skills_never_used_in_experience(self):
        cv = (
            "# A\na@b.co\n\n## Work experience\n- Built reports for the finance team and presented them every month to senior staff here.\n\n"
            "## Skills\nJava, Rust, Go, Scala, Haskell, Erlang\n"
        )
        self.assertEqual(by_id(ats.check_text(cv, TODAY))["skills_in_experience"]["status"], "warn")

    def test_too_many_skills(self):
        cv = "# A\na@b.co\n\n## Skills\n" + ", ".join(f"Tool{i}" for i in range(30)) + "\n"
        self.assertEqual(by_id(ats.check_text(cv, TODAY))["skills_count"]["status"], "warn")

    def test_spelled_out_acronym_passes(self):
        cv = "# A\na@b.co\nSearch engine optimisation (SEO) lead.\n"
        self.assertEqual(by_id(ats.check_text(cv, TODAY))["acronyms"]["status"], "pass")


class OddInput(SimpleTestCase):
    def test_empty_cv(self):
        for text in ("", "   \n\n", None):
            r = ats.check_text(text, TODAY)
            self.assertEqual(r["readiness"], 0)
            self.assertTrue(r["empty"])
            self.assertEqual(r["checks"][0]["status"], "fail")
            self.assertIn("Add your CV", r["checks"][0]["fix"])

    def test_a_cv_in_another_language_does_not_crash_and_skips_english_only_checks(self):
        cv = (
            "# Zoë Müller\nzoe@example.de · Berlin, Deutschland\n\n## Berufserfahrung\n**Entwicklerin** - Firma GmbH, Jan 2020 - Heute\n"
            + "\n".join(f"- Entwickelte die Schnittstelle für Kunden und Partner in Projekt {i} gemeinsam mit dem Team." for i in range(4))
            + "\n\n## Ausbildung\nUniversität Berlin, 2015 - 2019\n\n## Kenntnisse\nPython, SQL\n"
        )
        r = ats.check_text(cv, TODAY)
        ids = {c["id"] for c in r["checks"]}
        self.assertNotIn("first_person", ids)
        self.assertNotIn("bullets_verb", ids)
        self.assertTrue(r["notes"])
        self.assertEqual(by_id(r)["contact_email"]["status"], "pass")
        self.assertEqual(by_id(r)["sections_names"]["status"], "warn")  # German headings are not names a parser is assumed to know

    def test_binary_looking_and_huge_text_do_not_crash(self):
        ats.check_text("\x00\x01\x02 " * 50 + "# x", TODAY)
        ats.check_text("- word\n" * 5000, TODAY)


class Coverage(SimpleTestCase):
    JOB = (
        "We are hiring a backend engineer.\nRequirements: you must know Python, Django and Docker.\n"
        "You will build REST APIs on PostgreSQL and deploy with Kubernetes. Kubernetes experience is a plus. Terraform helps."
    )
    CV = "# A\n\n## Skills\nPython, Django, REST\n"

    def test_found_missing_and_split_by_the_persons_own_material(self):
        material = ["Ran Docker in production and used PostgreSQL daily."]
        c = ats.coverage(self.CV, self.JOB, material)
        found = {e["term"] for e in c["found"]}
        in_material = {e["term"] for e in c["in_material"]}
        outside = {e["term"] for e in c["not_in_material"]}
        self.assertTrue({"python", "django"} <= found)
        self.assertTrue({"docker", "postgresql"} <= in_material)
        self.assertTrue({"kubernetes", "terraform"} <= outside)
        self.assertFalse(found & in_material or in_material & outside)
        self.assertIn("only add", c["note"].lower())
        self.assertEqual(c["percent"], round(100 * len(c["found"]) / c["wanted"]))

    def test_required_terms_are_marked(self):
        c = ats.coverage(self.CV, self.JOB, [])
        required = {e["term"] for e in c["found"] + c["in_material"] + c["not_in_material"] if e["required"]}
        self.assertTrue({"python", "docker"} <= required)

    def test_nothing_to_compare(self):
        self.assertIsNone(ats.coverage(self.CV, "", []))
