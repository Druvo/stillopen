"""Regression tests for what a real first-time walk through the app turned up."""
import json
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
        data = {"target_roles": "Backend Engineer", "home_country": "Bangladesh", "profile_cv": CV, "open_remote": True, "other_places": ""}
        data.update(extra)
        return self.client.post("/api/v1/welcome", data=json.dumps(data), content_type="application/json")

    def places(self):
        return [(a.place, a.allow_remote, a.allow_hybrid, a.allow_onsite) for a in self.u.search_areas.all()]

    def test_home_country_and_remote_anywhere_become_visible_areas(self):
        self.post()
        self.assertEqual(self.places(), [("Bangladesh", True, True, True), ("Anywhere", True, False, False)])

    def test_other_places_are_added_and_remote_can_be_declined(self):
        self.post(open_remote=False, other_places="Malaysia\nGulf")
        self.assertEqual([p[0] for p in self.places()], ["Bangladesh", "Malaysia", "Gulf"])

    def test_nothing_given_makes_no_areas(self):
        self.post(home_country="", open_remote=False)
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
        self.assertEqual(r.status_code, 400)
        self.assertIn("a lot of places", r.json()["error"])
        self.assertFalse(self.u.search_areas.exists())

    def test_the_screen_is_told_what_is_already_answered(self):
        data = self.client.get("/api/v1/welcome").json()
        self.assertFalse(data["done"])


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

    def test_the_app_shows_searching_without_the_old_prompt(self):
        ScanRun.objects.create(owner=self.u, running=True, total=118, done=40)
        self.client.login(username="rina", password=PW)
        data = self.client.get("/api/v1/dashboard").json()
        self.assertIn("searching", data["next_step"]["headline"].lower())
        self.assertNotIn("Add the first job you are curious about", json.dumps(data["next_step"]))
        self.assertEqual((data["scan"]["running"], data["scan"]["done"], data["scan"]["total"], data["scan"]["phase"]), (True, 40, 118, "reading"))

    def test_when_every_source_is_read_the_phase_says_it_is_sorting(self):
        ScanRun.objects.create(owner=self.u, running=True, total=118, done=118)
        self.client.login(username="rina", password=PW)
        self.assertEqual(self.client.get("/api/v1/dashboard").json()["scan"]["phase"], "sorting")


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
        self.assertIn("/app/welcome", r["Location"])
        self.assertEqual(self.client.get("/api/v1/me").status_code, 200)  # signed in straight away

    @override_settings(STILLOPEN_REQUIRE_EMAIL_CONFIRMATION=True, STILLOPEN_SIGNUP_MIN_SECONDS=0)
    def test_with_smtp_confirmation_is_still_required(self):
        self.signup()
        self.assertEqual(self.client.get("/api/v1/me").status_code, 401)
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
        self.assertTrue(self.client.get("/api/v1/me").json()["email_unverified_signups"])
        self.client.login(username="jo", password=PW)
        self.assertFalse(self.client.get("/api/v1/me").json()["email_unverified_signups"])

    @override_settings(STILLOPEN_REQUIRE_EMAIL_CONFIRMATION=False)
    def test_no_warning_when_sign_up_is_closed(self):
        SiteConfig.objects.filter(pk=1).update(signup_mode="closed")
        staff = User.objects.create_user("boss", email="boss@example.com", password=PW, is_staff=True)
        UserProfile.objects.filter(user=staff).update(onboarding_done=True, target_roles="x")
        self.client.login(username="boss", password=PW)
        self.assertFalse(self.client.get("/api/v1/me").json()["email_unverified_signups"])


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
        data = self.client.get("/api/v1/scan/status").json()
        self.assertIn("best new matches", data["note"])
        self.assertEqual(data["error"], "")

    def test_progress_counts_up_while_sources_are_read(self):
        seen = []
        real = scan._prefetch_staged

        def spy(sources, roles=None, jooble_key="", usajobs_auth=("", ""), on_progress=None, first_wait=None):
            return real(sources, roles, jooble_key, usajobs_auth, on_progress=lambda n: (seen.append(n), on_progress(n)), first_wait=first_wait)

        JobSource.objects.create(name="Lever Co", connector="lever", board_token="lev")
        with mock.patch("tracker.services.scan._prefetch_staged", spy), \
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


class FasterPlaceDetectionAgreesWithTheSlowOne(TestCase):
    """The search got much faster by scanning text once instead of once per place name; it must give the same answers."""

    def corpus(self):
        from tracker.services import geo
        names = [t for _, _, _, t in geo._PLACES]
        pieces = []
        for i, name in enumerate(names):
            pieces += [name, f"Based in {name}.", f"Join us in {name}, then travel", f"remote from {name.lower()}", f"{name}shire", f"x{name}", f"{name.upper()} office", f"Work in {name} or {names[(i * 7) % len(names)]}"]
        pieces += ["", "Remote - worldwide", "nothing here at all", "New York and York and Kuala Lumpur and Lumpur", "Washington DC / Washington", "UK or United Kingdom or Britain"]
        return pieces

    def test_first_place_is_identical_on_every_name_and_variant(self):
        from tracker.services import geo
        for text in self.corpus():
            self.assertEqual(geo._first_place(text), geo._first_place_slow(text), text)

    def test_identical_inside_long_realistic_text(self):
        from tracker.services import geo
        filler = "We build payment systems for merchants. Our team works across time zones and values ownership. " * 12
        for name in ("Dhaka", "Kuala Lumpur", "Dubai", "Berlin", "New York", "Malaysia", "United States"):
            text = filler + f" Location: {name}. " + filler
            self.assertEqual(geo._first_place(text[:2500]), geo._first_place_slow(text[:2500]))

    def test_resolve_place_lookup_matches_the_old_behaviour(self):
        from tracker.services import geo
        for text, expected in [("Dhaka", {"BD"}), ("dhaka", {"BD"}), ("Malaysia", {"MY"}), ("Kuala Lumpur, Malaysia", {"MY"}),
                               ("Petaling Jaya, Malaysia", {"MY"}), ("Anywhere", {"*"}), ("Nowhereville", None), ("", None)]:
            self.assertEqual(geo.resolve_place(text), expected, text)

    def test_detect_output_unchanged_for_typical_postings(self):
        from tracker.services import geo
        found = geo.detect("Backend Engineer", "Location: Kuala Lumpur, Malaysia. This is a hybrid role. Visa sponsorship available.")
        self.assertEqual((found["country"], found["arrangement"], found["sponsorship"]), ("MY", "hybrid", "yes"))

    def test_the_tokenizer_still_keeps_skills_and_drops_noise(self):
        from tracker.services.text import terms
        self.assertEqual(terms("The C# and C++ developer, .NET and Node.js. Go, R and an AI team."), ["c#", "c++", "developer", ".net", "node.js", "go", "r", "ai"])


class OneTokenizationPerPosting(TestCase):
    def test_corpus_pass_returns_counts_and_a_tiny_per_posting_summary(self):
        postings = [{"title": "Backend Engineer", "description": "docker kubernetes terraform ansible " + ("zzz%d" % i)} for i in range(5)]
        total, counts, memo = scan._read_corpus({1: postings, 2: Exception("x")}, {"docker", "rust"})
        self.assertEqual(total, 5)
        self.assertEqual(counts["docker"], 5)
        skill_words, size = memo[id(postings[0])]
        self.assertEqual(skill_words, frozenset({"docker"}))
        self.assertGreaterEqual(size, 6)

    def test_common_words_decision_needs_a_big_enough_sample(self):
        from collections import Counter
        self.assertEqual(scan._common_from(10, Counter({"a": 10}), 0.12), set())
        self.assertEqual(scan._common_from(300, Counter({"a": 300, "b": 3}), 0.12), {"a"})


class SearchStartsWithTheFastMajority(TestCase):
    """The first jobs appear without waiting for the slowest hosts; those then top the list up."""

    def setUp(self):
        cache.clear()
        self.u = person(cv=CV)
        JobSource.objects.create(name="Fast", connector="greenhouse", board_token="fast")
        JobSource.objects.create(name="Slow", connector="lever", board_token="slow")

    def rows(self, company):
        return [job(url=f"https://{company}.test/{i}", company=f"{company}{i}", title="Backend Engineer", description=BIG) for i in range(3)]

    def test_slow_host_tops_up_after_the_first_batch(self):
        import time

        def slow(token):
            time.sleep(0.8)
            return self.rows("slow")

        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=self.rows("fast")), \
                mock.patch("tracker.services.scan.fetch_lever", side_effect=slow), \
                override_settings(STILLOPEN_SCAN_FIRST_WAIT_SECONDS=0.2, STILLOPEN_SCAN_FIRST_BATCH=2, STILLOPEN_SCAN_MAX_NEW=4, STILLOPEN_SCAN_DEADLINE_SECONDS=10):
            run = scan.start_run(self.u, background=False)
        self.assertEqual(run.added, 4)
        self.assertEqual(run.entries.get(source_name="Fast").added, 2)  # the first batch, from the fast host
        self.assertEqual(run.entries.get(source_name="Slow").added, 2)  # the top-up, from the slow one
        self.assertIn("best new matches", run.note)
        self.assertEqual(run.done, 2)

    def test_the_first_batch_is_in_the_tracker_before_the_slow_host_answers(self):
        import threading
        release, seen = threading.Event(), {}

        def slow(token):
            seen["added_while_waiting"] = Application.objects.filter(owner=self.u).count()
            return []

        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=self.rows("fast")), \
                mock.patch("tracker.services.scan.fetch_lever", side_effect=slow), \
                override_settings(STILLOPEN_SCAN_FIRST_WAIT_SECONDS=0.2, STILLOPEN_SCAN_FIRST_BATCH=2, STILLOPEN_SCAN_MAX_NEW=4, STILLOPEN_SCAN_DEADLINE_SECONDS=10):
            scan.start_run(self.u, background=False)
        self.assertEqual(Application.objects.filter(owner=self.u).count(), 3)  # fast host's 3 candidates, all within the cap of 4

    def test_everyone_answers_fast_means_one_stage_with_the_full_cap(self):
        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=self.rows("fast")), \
                mock.patch("tracker.services.scan.fetch_lever", return_value=self.rows("slow")), \
                override_settings(STILLOPEN_SCAN_FIRST_BATCH=2, STILLOPEN_SCAN_MAX_NEW=5):
            run = scan.start_run(self.u, background=False)
        self.assertEqual(run.added, 5)

    def test_a_host_that_never_answers_still_ends_the_search(self):
        import threading
        release = threading.Event()

        def stuck(token):
            release.wait(10)
            return []

        try:
            with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=self.rows("fast")), \
                    mock.patch("tracker.services.scan.fetch_lever", side_effect=stuck), \
                    override_settings(STILLOPEN_SCAN_FIRST_WAIT_SECONDS=0.2, STILLOPEN_SCAN_DEADLINE_SECONDS=1):
                run = scan.start_run(self.u, background=False)
        finally:
            release.set()
        self.assertEqual(run.added, 3)
        self.assertIn("Took too long", run.entries.get(source_name="Slow").error)
        self.assertFalse(ScanRun.objects.get(pk=run.pk).running)


class LoadingIndicator(TestCase):
    """What the search progress bar reads (the screen itself is drawn by the app)."""

    def setUp(self):
        self.u = person()
        self.client.login(username="rina", password=PW)

    def status(self):
        return self.client.get("/api/v1/scan/status").json()

    def test_before_the_first_search_there_is_nothing_running(self):
        data = self.status()
        self.assertEqual((data["running"], data["total"], data["phase"]), (False, 0, "done"))

    def test_while_running_it_reports_what_the_bar_needs(self):
        ScanRun.objects.create(owner=self.u, running=True, total=100, done=40, added=0)
        data = self.status()
        self.assertEqual((data["running"], data["done"], data["total"], data["phase"]), (True, 40, 100, "reading"))

    def test_when_finished_the_summary_stays(self):
        ScanRun.objects.create(owner=self.u, running=False, total=100, done=100, found=500, added=7)
        data = self.status()
        self.assertEqual((data["running"], data["found"], data["added"], data["phase"]), (False, 500, 7, "done"))

    def test_when_every_source_is_read_the_bar_is_full(self):
        ScanRun.objects.create(owner=self.u, running=True, total=118, done=118)
        data = self.status()
        self.assertEqual((data["done"], data["total"], data["phase"]), (118, 118, "sorting"))

    def test_the_added_number_counts_up_so_the_app_can_refresh_the_list_once(self):
        run = ScanRun.objects.create(owner=self.u, running=True, total=10, done=3, added=0)
        self.assertEqual(self.status()["added"], 0)
        ScanRun.objects.filter(pk=run.pk).update(added=25)
        self.assertEqual(self.status()["added"], 25)


class FullTextWhenItIsNeeded(TestCase):
    """A search keeps a short excerpt; the whole posting is read from its link the first time a check needs it."""

    def setUp(self):
        self.u = person(cv=CV)
        self.cfg = SiteConfig.for_user(self.u)

    def app(self, **kw):
        fields = {"owner": self.u, "company": "Acme", "role": "Backend Engineer", "url": "https://jobs.example.com/1",
                  "description": "short excerpt of the posting", "description_is_excerpt": True,
                  "status": __import__("tracker.models", fromlist=["Status"]).Status.objects.first()}
        fields.update(kw)
        return Application.objects.create(**fields)

    def test_an_excerpt_is_replaced_by_the_full_posting_once(self):
        from tracker.services import ai
        app = self.app()
        with mock.patch("tracker.services.ai.fetch_description", return_value=BIG + " and much more detail about the role") as fetch:
            ai.ensure_description(app, self.cfg)
            ai.ensure_description(app, self.cfg)
        self.assertEqual(fetch.call_count, 1)
        app.refresh_from_db()
        self.assertIn("much more detail", app.description)
        self.assertFalse(app.description_is_excerpt)

    def test_if_the_fetch_fails_the_excerpt_is_kept_and_tried_again_next_time(self):
        from tracker.services import ai
        from tracker.services.netguard import FetchError
        app = self.app()
        with mock.patch("tracker.services.ai.fetch_description", side_effect=FetchError("HTTP 403")):
            ai.ensure_description(app, self.cfg)  # no error: the check goes ahead on the excerpt
        app.refresh_from_db()
        self.assertEqual(app.description, "short excerpt of the posting")
        self.assertTrue(app.description_is_excerpt)

    def test_a_shorter_page_does_not_replace_the_excerpt(self):
        from tracker.services import ai
        app = self.app(description="a reasonably long excerpt of the posting with plenty of words in it")
        with mock.patch("tracker.services.ai.fetch_description", return_value="Sign in to continue"):
            ai.ensure_description(app, self.cfg)
        app.refresh_from_db()
        self.assertIn("plenty of words", app.description)
        self.assertFalse(app.description_is_excerpt)  # asked once; do not keep hitting a login wall

    def test_full_descriptions_and_hand_added_jobs_are_never_refetched(self):
        from tracker.services import ai
        app = self.app(description_is_excerpt=False)
        with mock.patch("tracker.services.ai.fetch_description") as fetch:
            ai.ensure_description(app, self.cfg)
        fetch.assert_not_called()

    def test_an_excerpt_with_no_link_is_used_as_it_is(self):
        from tracker.services import ai
        app = self.app(url="")
        with mock.patch("tracker.services.ai.fetch_description") as fetch:
            ai.ensure_description(app, self.cfg)
        fetch.assert_not_called()

    def test_searches_mark_what_they_save_as_an_excerpt_and_hand_added_jobs_are_not(self):
        cache.clear()
        JobSource.objects.create(name="Acme", connector="greenhouse", board_token="acme")
        with mock.patch("tracker.services.scan.fetch_greenhouse", return_value=[job(description=BIG)]):
            scan.start_run(self.u, background=False)
        self.assertTrue(Application.objects.get(owner=self.u, company="Acme").description_is_excerpt)
        self.assertFalse(Application.objects.create(owner=self.u, company="Hand", role="x", status=Application.objects.first().status).description_is_excerpt)

    def test_the_cover_letter_and_cv_paths_get_the_full_text_too(self):
        from tracker.services import coverletter
        app = self.app()
        with mock.patch("tracker.services.ai.fetch_description", return_value=BIG + " extra") as fetch:
            coverletter.generate(app, self.cfg, mode="keywords")
        fetch.assert_called_once()


class BestAreaIsNamed(TestCase):
    def setUp(self):
        self.u = person()
        self.areas = [
            SearchArea.objects.create(owner=self.u, place="Bangladesh", allow_remote=True, allow_hybrid=True, allow_onsite=True),
            SearchArea.objects.create(owner=self.u, place="Anywhere", allow_remote=True),
            SearchArea.objects.create(owner=self.u, place="Malaysia", allow_remote=True, allow_hybrid=True, allow_onsite=True),
        ]

    def text(self, **kw):
        from tracker.services import fit
        from tracker.models import Status
        app = Application(owner=self.u, company="x", role="y", status=Status.objects.first(), **kw)
        return fit.fit_flags(app, self.areas, UserProfile.objects.get(user=self.u))[0]["text"]

    def test_a_worldwide_remote_job_is_described_by_anywhere(self):
        self.assertIn("fits your search area: Anywhere", self.text(arrangement="remote", location_text="Anywhere in the World"))

    def test_a_job_in_a_named_country_is_described_by_that_country(self):
        self.assertIn("fits your search area: Malaysia", self.text(arrangement="onsite", country="MY", location_text="Kuala Lumpur"))

    def test_a_remote_job_limited_to_a_country_names_that_country_not_anywhere(self):
        self.assertIn("fits your search area: Malaysia", self.text(arrangement="remote", country="MY", location_text="Remote (Malaysia)"))

    def test_fewer_requirements_still_win_over_specificity(self):
        SearchArea.objects.filter(pk=self.areas[2].pk).update(needs_visa_sponsorship=True)
        self.assertIn("fits your search area: Anywhere", self.text(arrangement="remote", location_text="Anywhere in the World"))


class DashboardShowsEverything(TestCase):
    """Every job comes in one list, best first, for the app to filter and sort in the browser."""

    def setUp(self):
        from datetime import date, timedelta
        from tracker.models import Status
        self.u = person()
        self.client.login(username="rina", password=PW)
        ev, applied, rejected = (Status.objects.get(name=n) for n in ("Evaluated", "Applied", "Rejected"))

        def make(company, status=ev, **kw):
            return Application.objects.create(owner=self.u, company=company, role="Backend Engineer", status=status, **kw)

        self.a = make("Alpha", score=4.5, country="MY", arrangement="onsite", location_text="Kuala Lumpur", found_date=date.today())
        self.b = make("Bravo", score=2.0, country="BD", arrangement="hybrid", location_text="Dhaka", found_date=date.today() - timedelta(days=30))
        self.c = make("Charlie", status=applied, applied_date=date.today())
        self.d = make("Delta", status=rejected, score=3.0, arrangement="remote", location_text="Remote")
        UserProfile.objects.filter(user=self.u).update(onboarding_done=True)

    def data(self):
        return self.client.get("/api/v1/dashboard").json()

    def test_every_job_is_in_one_list(self):
        data = self.data()
        self.assertEqual(sorted(j["company"] for j in data["jobs"]), ["Alpha", "Bravo", "Charlie", "Delta"])
        self.assertEqual(data["stats"]["total"], 4)

    def test_the_stages_carry_the_jobs_of_the_admins_tabs(self):
        data = self.data()
        keys = {b["key"] for b in data["buckets"]}
        counts = {k: sum(1 for j in data["jobs"] if j["bucket_key"] == k) for k in keys}
        self.assertEqual((counts["apply"], counts["pending"], counts["closed"]), (2, 1, 1))

    def test_best_match_is_the_default_order(self):
        order = [j["company"] for j in self.data()["jobs"]]
        self.assertLess(order.index("Alpha"), order.index("Delta"))
        self.assertLess(order.index("Delta"), order.index("Bravo"))

    def test_each_job_carries_what_the_filters_read(self):
        jobs = {j["company"]: j for j in self.data()["jobs"]}
        a = jobs["Alpha"]
        self.assertEqual((a["bucket_key"], a["arrangement"], a["country"], a["percent"]), ("apply", "onsite", "MY", 90))
        self.assertIsNone(jobs["Charlie"]["percent"])

    def test_only_my_jobs_are_in_the_list(self):
        other = person("sam")
        Application.objects.create(owner=other, company="Secretco", role="x", country="DE", status=Application.objects.first().status)
        self.assertNotIn("Secretco", json.dumps(self.data()))

    def test_a_person_with_no_jobs_gets_an_empty_list(self):
        Application.objects.all().delete()
        self.assertEqual(self.data()["jobs"], [])
