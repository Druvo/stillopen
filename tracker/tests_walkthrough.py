"""Regression tests for what a real first-time walk through the app turned up."""
import re
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from tracker import forms
from tracker.models import Application, JobSource, ScanRun, SearchArea, SiteConfig, UserProfile
from tracker.services import guide, scan
from tracker.tests_engine import BIG, DULL, job, person

User = get_user_model()
PW = "correct-horse-battery-staple"
CV = "# Rina\nBackend engineer. C#, SQL Server, REST APIs, Docker, Kubernetes, PostgreSQL, microservices, payment systems."


class WelcomeAsksWhereYouWouldWork(TestCase):
    def setUp(self):
        self.u = User.objects.create_user("rina", email="rina@example.com", password=PW)
        self.client.login(username="rina", password=PW)

    def post(self, **extra):
        data = {"target_roles": "Backend Engineer", "home_country": "Bangladesh", "profile_cv": CV, "open_remote": "on", "other_places": ""}
        data.update(extra)
        return self.client.post(reverse("welcome"), data)

    def places(self):
        return [(a.place, a.allow_remote, a.allow_hybrid, a.allow_onsite) for a in self.u.search_areas.all()]

    def test_home_country_and_remote_anywhere_become_visible_areas(self):
        self.post()
        self.assertEqual(self.places(), [("Bangladesh", True, True, True), ("Anywhere", True, False, False)])

    def test_other_places_are_added_and_remote_can_be_declined(self):
        self.post(open_remote="", other_places="Malaysia\nGulf")
        self.assertEqual([p[0] for p in self.places()], ["Bangladesh", "Malaysia", "Gulf"])

    def test_nothing_given_makes_no_areas(self):
        self.post(home_country="", open_remote="")
        self.assertEqual(self.places(), [])

    def test_a_careful_existing_setup_is_never_replaced(self):
        SearchArea.objects.create(owner=self.u, place="Qatar", allow_onsite=True)
        self.post(other_places="Malaysia")
        self.assertEqual([p[0] for p in self.places()], ["Qatar"])

    def test_duplicates_are_not_repeated(self):
        self.post(other_places="bangladesh\nMalaysia")
        self.assertEqual([p[0] for p in self.places()], ["Bangladesh", "Anywhere", "Malaysia"])

    def test_too_many_places_is_refused_politely(self):
        r = self.post(other_places="\n".join(f"Place {i}" for i in range(9)))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "a lot of places")
        self.assertFalse(self.u.search_areas.exists())

    def test_the_page_says_what_it_does_now(self):
        page = self.client.get(reverse("welcome"))
        self.assertContains(page, "Find jobs for me")
        self.assertContains(page, "work remotely, from anywhere")
        self.assertNotContains(page, "add my first job")


class NextStepMatchesWhatIsHappening(TestCase):
    def setUp(self):
        self.u = person()

    def test_while_searching_there_is_no_contradicting_add_a_job_prompt(self):
        step = guide.next_step(UserProfile.objects.get(user=self.u), [], searching=True)
        self.assertIn("searching", step["headline"].lower())
        self.assertEqual(step["url"], "")

    def test_no_places_is_pointed_out_before_the_list_fills_with_everywhere(self):
        step = guide.next_step(UserProfile.objects.get(user=self.u), [], has_areas=False)
        self.assertIn("where you would work", step["headline"])
        self.assertTrue(step["url"].endswith("#areas"))

    def test_dashboard_shows_searching_without_a_button_and_without_the_old_prompt(self):
        ScanRun.objects.create(owner=self.u, running=True, total=118, done=40)
        self.client.login(username="rina", password=PW)
        page = self.client.get(reverse("dashboard"))
        self.assertContains(page, "We are searching for jobs that fit you")
        self.assertNotContains(page, "Add the first job you are curious about")
        self.assertContains(page, "Reading job sources... 40/118")

    def test_when_every_source_is_read_the_label_says_it_is_sorting(self):
        ScanRun.objects.create(owner=self.u, running=True, total=118, done=118)
        self.client.login(username="rina", password=PW)
        self.assertContains(self.client.get(reverse("dashboard")), "Sorting out the best matches")


class SignUpWorksWithoutEmail(TestCase):
    def setUp(self):
        cache.clear()
        SiteConfig.objects.filter(pk=1).update(signup_mode="open")

    def signup(self):
        return self.client.post(reverse("account_signup"), {"email": "sam@example.com", "password1": PW})

    @override_settings(STILLOPEN_REQUIRE_EMAIL_CONFIRMATION=False, STILLOPEN_SIGNUP_MIN_SECONDS=0)
    def test_without_smtp_a_new_person_is_signed_straight_in(self):
        r = self.signup()
        self.assertEqual(r.status_code, 302)
        self.assertIn("/welcome/", r["Location"])
        self.assertEqual(self.client.get(reverse("welcome")).status_code, 200)  # signed in: the welcome page opens for them
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 200)

    @override_settings(STILLOPEN_REQUIRE_EMAIL_CONFIRMATION=True, STILLOPEN_SIGNUP_MIN_SECONDS=0)
    def test_with_smtp_confirmation_is_still_required(self):
        self.signup()
        self.assertEqual(self.client.get(reverse("welcome")).status_code, 302)
        self.assertTrue(any("confirm" in m.subject.lower() for m in mail.outbox))

    def test_the_setting_follows_whether_email_is_configured(self):
        from django.conf import settings
        self.assertEqual(settings.STILLOPEN_REQUIRE_EMAIL_CONFIRMATION, True)  # tests always insist; see settings.py for the rule

    @override_settings(STILLOPEN_REQUIRE_EMAIL_CONFIRMATION=False)
    def test_an_admin_is_told_but_an_ordinary_person_is_not(self):
        staff = User.objects.create_user("boss", email="boss@example.com", password=PW, is_staff=True)
        UserProfile.objects.filter(user=staff).update(onboarding_done=True, target_roles="x")
        normal = User.objects.create_user("jo", email="jo@example.com", password=PW)
        UserProfile.objects.filter(user=normal).update(onboarding_done=True, target_roles="x")
        self.client.login(username="boss", password=PW)
        self.assertContains(self.client.get(reverse("dashboard")), "no email set up")
        self.client.login(username="jo", password=PW)
        self.assertNotContains(self.client.get(reverse("dashboard")), "no email set up")

    @override_settings(STILLOPEN_REQUIRE_EMAIL_CONFIRMATION=False)
    def test_no_warning_when_sign_up_is_closed(self):
        SiteConfig.objects.filter(pk=1).update(signup_mode="closed")
        staff = User.objects.create_user("boss", email="boss@example.com", password=PW, is_staff=True)
        UserProfile.objects.filter(user=staff).update(onboarding_done=True, target_roles="x")
        self.client.login(username="boss", password=PW)
        self.assertNotContains(self.client.get(reverse("dashboard")), "no email set up")


class SearchQuality(TestCase):
    def setUp(self):
        cache.clear()
        self.u = person(cv=CV)
        self.src = JobSource.objects.create(name="Acme", connector="greenhouse", board_token="acme")

    def run_scan(self, rows, **kw):
        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=rows), override_settings(**kw):
            return scan.start_run(self.u, background=False)

    def test_a_posting_with_only_a_title_is_not_given_a_fake_perfect_score(self):
        self.run_scan([job(description="")])
        app = Application.objects.get(owner=self.u)
        self.assertIsNone(app.score)

    def test_a_posting_with_real_text_is_scored(self):
        self.run_scan([job(description=BIG)])
        self.assertIsNotNone(Application.objects.get(owner=self.u).score)

    def test_one_employer_cannot_fill_the_list(self):
        rows = [job(url=f"https://x.test/{i}", title="Backend Engineer", company="Grab", location=f"City {i}", description=BIG) for i in range(9)]
        run = self.run_scan(rows, STILLOPEN_SCAN_MAX_PER_COMPANY=3)
        self.assertEqual(run.added, 3)
        self.assertEqual(self.run_scan(rows, STILLOPEN_SCAN_MAX_PER_COMPANY=3).added, 3)  # the next batch from them, a fair share again

    def test_other_employers_still_get_a_place(self):
        rows = [job(url=f"https://x.test/g{i}", company="Grab", location=f"City {i}", description=BIG) for i in range(6)]
        rows.append(job(url="https://x.test/w", company="Wise", location="London", description=BIG))
        self.run_scan(rows, STILLOPEN_SCAN_MAX_PER_COMPANY=2)
        companies = sorted(Application.objects.filter(owner=self.u).values_list("company", flat=True))
        self.assertEqual(companies, ["Grab", "Grab", "Wise"])

    def test_cap_message_is_a_note_and_not_an_error_on_the_page(self):
        rows = [job(url=f"https://x.test/{i}", company=f"Co{i}", description=BIG) for i in range(4)]
        run = self.run_scan(rows, STILLOPEN_SCAN_MAX_NEW=2)
        self.assertIn("best new matches", run.note)
        self.assertEqual(run.error, "")
        self.client.login(username="rina", password=PW)
        page = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("best new matches", page)
        self.assertNotRegex(page, r'text-danger[^>]*>[^<]*best new matches')

    def test_progress_counts_up_while_sources_are_read(self):
        seen = []
        real = scan._prefetch

        def spy(sources, roles=None, jooble_key="", on_progress=None):
            return real(sources, roles, jooble_key, on_progress=lambda n: (seen.append(n), on_progress(n)))

        JobSource.objects.create(name="Lever Co", connector="lever", board_token="lev")
        with mock.patch("tracker.services.scan._prefetch", spy), \
                mock.patch("tracker.services.scan.fetch_greenhouse", return_value=[]), mock.patch("tracker.services.scan.fetch_lever", return_value=[]):
            run = scan.start_run(self.u, background=False)
        self.assertEqual(sorted(seen), [1, 2])
        self.assertEqual((run.done, run.total), (2, 2))

    def test_place_names_from_a_feed_are_tidied(self):
        self.assertEqual(scan._tidy_place("Beijing, , China"), "Beijing, China")
        self.assertEqual(scan._tidy_place("Singapore, , Singapore"), "Singapore, Singapore")
        self.assertEqual(scan._tidy_place(""), "")


class GenericWordsAreNotSkills(TestCase):
    """The fallback that finds postings whose title misses every role was matching almost everything, because
    words like "team" and "experience" count as the person's skills."""

    def test_common_words_are_measured_against_what_was_actually_read(self):
        skills = {"collaborate", "stakeholders", "docker", "kubernetes", "rust"}
        everyday = [{"title": "Role", "description": "Join us. Collaborate with stakeholders. " + ("docker " if i % 50 == 0 else "")} for i in range(300)]
        generic = scan._generic_terms({1: everyday}, skills, 0.12)
        self.assertEqual(generic, {"collaborate", "stakeholders"})

    def test_too_small_a_sample_says_nothing(self):
        few = [{"title": "Role", "description": "Collaborate."} for _ in range(20)]
        self.assertEqual(scan._generic_terms({1: few}, {"collaborate"}, 0.12), set())

    def test_failed_sources_are_ignored(self):
        self.assertEqual(scan._generic_terms({1: Exception("x")}, {"collaborate"}, 0.12), set())

    def test_a_search_does_not_add_a_posting_that_only_shares_filler_words(self):
        cache.clear()
        u = person(roles="Quantum Chef", cv="Collaborate with stakeholders. Docker, Kubernetes, SQL Server, Terraform, Ansible, Rust.")
        JobSource.objects.create(name="Acme", connector="greenhouse", board_token="acme")
        filler = [job(url=f"https://x.test/f{i}", title=f"Office Role {i}", company=f"Co{i}", description="collaborate stakeholders collaborate stakeholders work environment") for i in range(250)]
        real = job(url="https://x.test/real", title="Platform Role", company="Real", description="Docker Kubernetes Terraform Ansible SQL Server pipelines and reliability for the platform team")
        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=filler + [real]), override_settings(STILLOPEN_SKILL_MATCH_MIN_OVERLAP=3):
            run = scan.start_run(u, background=False)
        self.assertEqual(list(Application.objects.filter(owner=u).values_list("company", flat=True)), ["Real"])
        self.assertEqual(run.entries.get().matched, 1)


class LocationFieldIsTrusted(TestCase):
    def codes(self, text):
        from tracker.services import geo
        return geo.location_codes(text)

    def test_places_in_the_location_field(self):
        self.assertEqual(self.codes("Bastrop, TX"), {"US"})
        self.assertEqual(self.codes("Palo Alto, CA"), {"US"})
        self.assertEqual(self.codes("Remote - United States"), {"US"})
        self.assertEqual(self.codes("US - Remote"), {"US"})
        self.assertEqual(self.codes("Petaling Jaya, Malaysia"), {"MY"})
        self.assertEqual(self.codes("Dhaka"), {"BD"})
        self.assertEqual(self.codes("Hong Kong; Singapore; Taiwan"), {"HK", "SG", "TW"})
        self.assertEqual(self.codes("United States and Canada"), {"US", "CA"})

    def test_unknown_or_worldwide_adds_nothing_and_is_never_guessed(self):
        for text in ("", "Remote", "Remote, Global", "Anywhere in the World", "Time zone: CET (+/- 3 hours)", "Zug (remote)"):
            self.assertEqual(self.codes(text), set(), text)

    def test_india_is_not_mistaken_for_indiana(self):
        self.assertEqual(self.codes("Gurugram, IN"), {"IN"})

    def test_a_region_names_several_countries(self):
        eu = self.codes("Remote - European Union")
        self.assertIn("DE", eu)
        self.assertGreater(len(eu), 10)

    def test_the_word_global_in_a_description_no_longer_turns_a_us_only_job_into_a_worldwide_one(self):
        cache.clear()
        u = person()
        SearchArea.objects.create(owner=u, place="Anywhere", allow_remote=True)
        SearchArea.objects.create(owner=u, place="Bangladesh", allow_remote=True, allow_hybrid=True, allow_onsite=True)
        UserProfile.objects.filter(user=u).update(home_country="BD")
        JobSource.objects.create(name="Acme", connector="greenhouse", board_token="acme")
        boiler = BIG + " We are a global company with a remote-first culture."
        rows = [
            job(url="https://x.test/us", company="UsOnly", location="Remote - United States", description=boiler),
            job(url="https://x.test/tx", company="Texas", location="Bastrop, TX", description=boiler),
            job(url="https://x.test/world", company="World", location="Remote, Global", description=boiler),
            job(url="https://x.test/dhaka", company="Local", location="Dhaka", description=boiler),
        ]
        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=rows):
            run = scan.start_run(u, background=False)
        self.assertEqual(sorted(Application.objects.filter(owner=u).values_list("company", flat=True)), ["Local", "World"])
        self.assertEqual(run.entries.get().outside, 2)
        self.assertEqual(Application.objects.get(owner=u, company="Local").country, "BD")

    def test_multi_country_and_region_postings_need_one_of_the_persons_places(self):
        from tracker.services import fit
        u = person()
        UserProfile.objects.filter(user=u).update(home_country="BD")
        areas = [SearchArea.objects.create(owner=u, place="Anywhere", allow_remote=True), SearchArea.objects.create(owner=u, place="Malaysia", allow_onsite=True)]
        profile = UserProfile.objects.get(user=u)
        self.assertTrue(fit.region_outside({"HK", "SG", "TW"}, areas, profile))
        self.assertFalse(fit.region_outside({"MY", "SG"}, areas, profile))  # one of them is a place they named
        self.assertFalse(fit.region_outside({"BD", "IN"}, areas, profile))  # they live in one of them
        self.assertFalse(fit.region_outside({"US"}, areas, profile))  # a single country is handled elsewhere
        self.assertFalse(fit.region_outside({"HK", "SG"}, [], profile))  # no places: nothing to compare with
        gulf = SearchArea.objects.create(owner=u, place="Gulf", allow_onsite=True)
        self.assertFalse(fit.region_outside({"AE", "GB"}, [gulf], profile))  # a region they named covers Dubai


class ScoresUseDistinctiveWords(TestCase):
    CV = "Backend engineer. C#, SQL Server, Docker, Kubernetes, microservices, payment systems."

    def test_filler_words_are_left_out_of_the_comparison(self):
        from tracker.services import ai
        posting = "software software software engineer engineer systems systems build build kubernetes terraform kafka"
        plain = ai.keyword_match(posting, self.CV)
        focused = ai.keyword_match(posting, self.CV, ignore=frozenset({"software", "engineer", "systems", "build"}))
        self.assertEqual(focused["strengths"], ["kubernetes"])
        self.assertNotIn("software", " ".join(focused["gaps"]))

    def test_if_everything_is_filler_it_falls_back_to_the_plain_comparison(self):
        from tracker.services import ai
        result = ai.keyword_match("docker kubernetes", self.CV, ignore=frozenset({"docker", "kubernetes"}))
        self.assertEqual(result["match_percent"], 100)

    def test_without_the_list_it_behaves_exactly_as_before(self):
        from tracker.services import ai
        a = ai.keyword_match("docker kubernetes terraform", self.CV)
        b = ai.keyword_match("docker kubernetes terraform", self.CV, ignore=frozenset())
        self.assertEqual(a, b)

    def test_a_search_remembers_the_filler_so_a_later_check_scores_the_same_way(self):
        cache.clear()
        u = person(cv=CV)
        JobSource.objects.create(name="Acme", connector="greenhouse", board_token="acme")
        rows = [job(url=f"https://x.test/{i}", title=f"Backend Engineer {i}", company=f"Co{i}", description=f"software engineer systems build project{i}alpha project{i}beta " + BIG) for i in range(250)]
        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=rows), override_settings(STILLOPEN_SCAN_MAX_NEW=3):
            scan.start_run(u, background=False)
        common = cache.get("scan-common-terms")
        self.assertIsNotNone(common)
        self.assertIn("software", common)
        app = Application.objects.filter(owner=u).first()
        from tracker.services import ai
        from tracker.models import SiteConfig as SC
        ai.evaluate_application(app, SC.for_user(u))  # the free path reads the same list
        app.refresh_from_db()
        self.assertNotIn("software", " ".join(i.text for i in app.insights.all()))


class SkillCoverageScore(TestCase):
    CV = "Backend engineer. C#, SQL Server, Docker, Kubernetes, microservices, PostgreSQL, AWS, payment systems, REST APIs."
    FILLER = frozenset({"software", "engineer", "systems", "build", "team", "platform"})

    def test_a_posting_that_mentions_many_of_your_skills_scores_well(self):
        from tracker.services import ai
        strong = ai.keyword_match("Build REST APIs in C# on SQL Server with Docker and Kubernetes. PostgreSQL and AWS a plus. microservices.", self.CV, ignore=self.FILLER)
        weak = ai.keyword_match("Sales operations role focused on salesforce, quotas, territories and forecasting for enterprise accounts.", self.CV, ignore=self.FILLER)
        self.assertGreaterEqual(strong["match_percent"], 60)
        self.assertLessEqual(weak["match_percent"], 10)
        self.assertIn("main skills", strong["summary"])
        self.assertIn("docker", strong["strengths"])

    def test_it_is_not_pulled_down_by_words_only_this_posting_repeats(self):
        from tracker.services import ai
        noisy = "Kubernetes docker " + "acmecorp widgets widgets widgets gadgets gadgets gadgets " * 5 + "C# SQL Server microservices"
        self.assertGreaterEqual(ai.keyword_match(noisy, self.CV, ignore=self.FILLER)["match_percent"], 40)

    def test_percent_never_exceeds_one_hundred(self):
        from tracker.services import ai
        everything = "C# SQL Server Docker Kubernetes microservices PostgreSQL AWS payment REST APIs backend " * 3
        self.assertLessEqual(ai.keyword_match(everything, self.CV, ignore=self.FILLER)["match_percent"], 100)

    def test_the_plain_count_is_unchanged_without_a_filler_list(self):
        from tracker.services import ai
        self.assertIn("things this posting talks about", ai.keyword_match("docker kubernetes terraform", self.CV)["summary"])
