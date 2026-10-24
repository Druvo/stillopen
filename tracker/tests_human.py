"""The first-run experience: a short sign-up, a warm welcome, plain-language guidance, no dead ends."""
import re
import time
from datetime import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from tracker.models import Application, SiteConfig, Status, UserProfile
from tracker.services import ai, guide

User = get_user_model()
PW = "correct-horse-battery-staple"
CV = "Backend engineer. C#, SQL Server, REST APIs, Docker."
JD = "We need a backend engineer with C#, SQL Server and Docker experience. " * 6


@override_settings(STILLOPEN_SIGNUP_MIN_SECONDS=0, ACCOUNT_RATE_LIMITS={"signup": "1000/m/ip"})
class SignUpAndWelcome(TestCase):
    def setUp(self):
        cache.clear()
        SiteConfig.objects.filter(pk=1).update(signup_mode="open")

    def signup(self, email="sam.jones@example.com"):
        return self.client.post(reverse("account_signup"), {"email": email, "password1": PW})

    def test_signup_asks_only_for_email_and_password(self):
        page = self.client.get(reverse("account_signup")).content.decode()
        self.assertIn('name="email"', page)
        self.assertIn('name="password1"', page)
        self.assertNotIn('name="username"', page)
        self.assertNotIn('name="password2"', page)
        self.signup()
        self.assertTrue(User.objects.filter(email="sam.jones@example.com").exists())

    def test_email_is_warm_and_names_the_product_not_example_com(self):
        self.signup()
        message = mail.outbox[0]
        self.assertIn("StillOpen", message.subject)
        self.assertNotIn("example.com]", message.subject)
        self.assertNotIn("Hello from example.com", message.body)
        self.assertIn("/accounts/confirm-email/", message.body)

    def test_the_link_confirms_signs_in_and_opens_the_welcome_page(self):
        self.signup()
        link = re.search(r"https?://[^\s]+/accounts/confirm-email/[^\s/]+/", mail.outbox[0].body).group(0)
        response = self.client.get("/" + link.split("/", 3)[3])
        self.assertRedirects(response, reverse("welcome"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("welcome")).status_code, 200)

    def test_a_second_click_on_the_link_does_not_sign_anyone_in(self):
        self.signup()
        link = re.search(r"https?://[^\s]+/accounts/confirm-email/[^\s/]+/", mail.outbox[0].body).group(0)
        path = "/" + link.split("/", 3)[3]
        self.client.get(path)
        self.client.logout()
        self.client.get(path)
        self.assertNotEqual(self.client.get(reverse("dashboard")).status_code, 200)

    def test_welcome_needs_a_login(self):
        self.assertEqual(self.client.get(reverse("welcome")).status_code, 302)
        self.assertEqual(self.client.post(reverse("welcome_skip")).status_code, 302)

    def test_saving_the_welcome_answers_fills_the_profile_and_moves_on(self):
        u = User.objects.create_user("sam", email="sam@example.com", password=PW)
        self.client.force_login(u)
        r = self.client.post(reverse("welcome"), {"target_roles": "Backend Engineer", "home_country": "Bangladesh", "profile_cv": CV})
        self.assertRedirects(r, reverse("dashboard"), fetch_redirect_response=False)  # the search starts there; no empty "add a job" detour
        profile = UserProfile.objects.get(user=u)
        self.assertTrue(profile.onboarding_done)
        self.assertEqual(profile.target_roles, "Backend Engineer")
        self.assertEqual(profile.home_country, "BD")
        self.assertTrue(profile.is_complete)

    def test_a_bad_country_keeps_the_person_on_the_page_with_a_clear_message(self):
        u = User.objects.create_user("sam", email="sam@example.com", password=PW)
        self.client.force_login(u)
        r = self.client.post(reverse("welcome"), {"target_roles": "x", "home_country": "Narnia", "profile_cv": CV})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Not recognised as one country")
        self.assertFalse(UserProfile.objects.get(user=u).onboarding_done)

    def test_skipping_is_remembered_and_leads_to_the_dashboard(self):
        u = User.objects.create_user("sam", email="sam@example.com", password=PW)
        self.client.force_login(u)
        self.assertRedirects(self.client.post(reverse("welcome_skip")), reverse("dashboard"), fetch_redirect_response=False)
        self.assertTrue(UserProfile.objects.get(user=u).onboarding_done)

    def test_people_who_already_use_the_app_are_not_sent_to_the_welcome_page(self):
        u = User.objects.create_user("old", email="old@example.com", password=PW)
        UserProfile.objects.filter(user=u).update(onboarding_done=True)
        r = self.client.post(reverse("account_login"), {"login": "old", "password": PW})
        self.assertRedirects(r, reverse("dashboard"), fetch_redirect_response=False)

    def test_a_first_sign_in_goes_to_the_welcome_page(self):
        User.objects.create_user("fresh", email="fresh@example.com", password=PW)
        r = self.client.post(reverse("account_login"), {"login": "fresh", "password": PW})
        self.assertRedirects(r, reverse("welcome"), fetch_redirect_response=False)


class NewJobsAndFit(TestCase):
    def setUp(self):
        cache.clear()
        self.u = User.objects.create_user("quinn", email="q@example.com", password=PW)
        UserProfile.objects.filter(user=self.u).update(profile_cv=CV, target_roles="Backend Engineer", onboarding_done=True)
        self.client.force_login(self.u)

    def add(self):
        self.client.post(reverse("add_job"), {"company": "Globex", "role": "Backend", "url": "https://jobs.example.com/1", "description": JD})
        return Application.objects.get(company="Globex")

    def test_a_new_job_is_saved_not_already_evaluated(self):
        app = self.add()
        self.assertEqual(app.status.name, "Saved")
        page = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn("Not checked yet", page)
        self.assertNotIn(">N/A<", page)

    def test_checking_the_fit_moves_it_to_evaluated(self):
        app = self.add()
        ai.evaluate_application(app, SiteConfig.for_user(self.u))
        app.refresh_from_db()
        self.assertEqual(app.status.name, "Evaluated")

    def test_a_status_you_set_yourself_is_not_overwritten_by_checking_the_fit(self):
        app = self.add()
        app.status = Status.objects.get(name="Applied")
        app.save()
        ai.evaluate_application(app, SiteConfig.for_user(self.u))
        app.refresh_from_db()
        self.assertEqual(app.status.name, "Applied")

    def test_the_percentage_you_see_is_the_percentage_you_were_told(self):
        app = self.add()
        config = SiteConfig.for_user(self.u)
        for percent in (45, 63, 87, 91):
            ai.store_result(app, {
                "match_percent": percent, "verdict": "Consider", "summary": "s", "strengths": [], "gaps": [],
                "risk": "", "next_action": "",
            }, config, "ai:test")
            app.refresh_from_db()
            self.assertEqual(round(app.score / config.score_scale * 100), percent)

    def test_the_keyword_check_speaks_kindly(self):
        app = self.add()
        result = ai.keyword_match(JD, CV)
        text = " ".join([result["summary"], result["next_action"], result["verdict"]] + result["gaps"])
        for harsh in ("Weak match", "poor fit", "Research first", "Keyword match only"):
            self.assertNotIn(harsh, text)
        self.assertIn("rough guide", result["summary"])
        self.assertIn("AI settings", result["next_action"])

    def test_the_dashboard_greets_by_name_and_points_to_one_next_step(self):
        self.u.first_name = "Quinn"
        self.u.save()
        page = self.client.get(reverse("dashboard")).content.decode()
        self.assertRegex(page, r"Good (morning|afternoon|evening), Quinn")
        self.assertEqual(page.count("YOUR NEXT STEP"), 1)


class Guidance(SimpleTestCase):
    def test_greeting_follows_the_time_of_day(self):
        class U:
            first_name, email = "", "sam.jones@example.com"

            def get_username(self):
                return "sam"

        self.assertEqual(guide.greeting(U(), datetime(2026, 1, 1, 8)), "Good morning, Sam")
        self.assertEqual(guide.greeting(U(), datetime(2026, 1, 1, 14)), "Good afternoon, Sam")
        self.assertEqual(guide.greeting(U(), datetime(2026, 1, 1, 21)), "Good evening, Sam")


class NextStep(TestCase):
    def setUp(self):
        self.u = User.objects.create_user("quinn", email="q@example.com", password=PW)
        self.profile = UserProfile.objects.get(user=self.u)
        self.client.force_login(self.u)

    def card(self, percent=None, cv=None, **kw):
        app = Application.objects.create(owner=self.u, company="Globex", role="Dev", description=JD,
                                         status=Status.objects.get(name="Saved"), **kw)
        return {"app": app, "percent": percent, "cv": cv}

    def test_an_incomplete_profile_comes_first(self):
        step = guide.next_step(self.profile, [])
        self.assertIn("Finish your profile", step["headline"])

    def test_then_the_first_job(self):
        UserProfile.objects.filter(pk=self.profile.pk).update(profile_cv=CV, target_roles="Dev")
        step = guide.next_step(UserProfile.objects.get(pk=self.profile.pk), [])
        self.assertIn("first job", step["headline"])

    def test_then_checking_the_fit(self):
        UserProfile.objects.filter(pk=self.profile.pk).update(profile_cv=CV, target_roles="Dev")
        card = self.card()
        step = guide.next_step(UserProfile.objects.get(pk=self.profile.pk), [card])
        self.assertIn("Globex", step["headline"])
        self.assertEqual(step["url"], f"#job-{card['app'].pk}")

    def test_then_tailoring_for_a_promising_job_and_nothing_when_all_is_done(self):
        UserProfile.objects.filter(pk=self.profile.pk).update(profile_cv=CV, target_roles="Dev")
        profile = UserProfile.objects.get(pk=self.profile.pk)
        card = self.card(percent=80)
        self.assertIn("Tailor your CV", guide.next_step(profile, [card])["headline"])
        card["cv"] = object()
        self.assertIsNone(guide.next_step(profile, [card]))


class Wording(TestCase):
    def test_landing_page_speaks_to_the_person_not_the_server_owner(self):
        page = self.client.get(reverse("landing")).content.decode()
        self.assertIn("Your first ten minutes", page)
        self.assertNotIn("Self-hosted", page)
        self.assertNotIn("Paperless", page)
        self.assertNotIn("Configurable from the admin", page)


class SignupBotTraps(TestCase):
    def setUp(self):
        cache.clear()
        SiteConfig.objects.filter(pk=1).update(signup_mode="open")
        self.url = reverse("account_signup")

    def token(self):
        tag = re.search(r"<input[^>]*name=\"form_started\"[^>]*>", self.client.get(self.url).content.decode()).group(0)
        return re.search(r'value="([^"]+)"', tag).group(1)

    def post(self, **extra):
        data = {"email": "kim@example.com", "password1": PW}
        data.update(extra)
        return self.client.post(self.url, data)

    @override_settings(STILLOPEN_SIGNUP_MIN_SECONDS=0)
    def test_honeypot_filled_creates_no_account(self):
        self.post(website="http://spam.example")
        self.assertFalse(User.objects.filter(email="kim@example.com").exists())

    @override_settings(STILLOPEN_SIGNUP_MIN_SECONDS=3)
    def test_missing_or_tampered_token_is_refused(self):
        self.post()
        self.post(form_started="garbage")
        self.assertFalse(User.objects.filter(email="kim@example.com").exists())

    @override_settings(STILLOPEN_SIGNUP_MIN_SECONDS=3)
    def test_instant_submit_is_refused_then_a_patient_one_works(self):
        token = self.token()
        self.post(form_started=token)
        self.assertFalse(User.objects.filter(email="kim@example.com").exists())
        with mock.patch("tracker.forms.time.time", return_value=time.time() + 10):
            self.post(form_started=token)
        self.assertTrue(User.objects.filter(email="kim@example.com").exists())

    @override_settings(STILLOPEN_SIGNUP_MIN_SECONDS=0, ACCOUNT_RATE_LIMITS={"signup": "2/m/ip"})
    def test_signup_is_rate_limited_per_address(self):
        codes = [self.post(email=f"p{i}@example.com").status_code for i in range(4)]
        self.assertIn(429, codes)

    def test_honeypot_box_is_hidden_from_people(self):
        page = self.client.get(self.url).content.decode()
        self.assertIn("left:-10000px", page)
        self.assertIn('aria-hidden="true"', page)
