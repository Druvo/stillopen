"""Signing in to the phone app through the website's own sign-in page: start -> sign in -> one-time code -> token."""
import hashlib
import json
import re

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from tracker.models import ApiToken

User = get_user_model()
PW = "correct-horse-battery-staple"
VERIFIER = "a-long-random-secret-only-the-app-knows-0123456789"
CHALLENGE = hashlib.sha256(VERIFIER.encode()).hexdigest()


def exchange(client, code, verifier=VERIFIER):
    return client.post(reverse("mobile_signin_exchange"), data=json.dumps({"code": code, "verifier": verifier}), content_type="application/json")


class MobileSignIn(TestCase):
    def setUp(self):
        cache.clear()
        self.ann = User.objects.create_user("ann", email="ann@example.com", password=PW)
        self.browser = Client()

    def code_after_signing_in(self):
        self.browser.get(reverse("mobile_signin_start"), {"challenge": CHALLENGE})
        self.browser.force_login(self.ann)  # stands in for the real sign-in page (any method)
        page = self.browser.get(reverse("mobile_signin_finish"))
        self.assertEqual(page.status_code, 200)
        return re.search(r"stillopen://auth\?code=([A-Za-z0-9_-]+)", page.content.decode()).group(1)

    def test_start_sends_a_signed_out_browser_to_the_sign_in_page_and_back(self):
        r = self.browser.get(reverse("mobile_signin_start"), {"challenge": CHALLENGE})
        self.assertRedirects(r, "/accounts/login/?next=/auth/mobile/finish/", fetch_redirect_response=False)

    def test_start_refuses_a_challenge_that_is_not_a_sha256(self):
        for bad in ("", "abc", "g" * 64, CHALLENGE + "0"):
            self.assertEqual(self.browser.get(reverse("mobile_signin_start"), {"challenge": bad}).status_code, 400)

    def test_a_signed_in_person_gets_a_code_and_trades_it_for_a_working_token(self):
        code = self.code_after_signing_in()
        r = exchange(Client(), code)
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        me = Client().get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {body['token']}")
        self.assertEqual(me.status_code, 200)
        self.assertEqual(body["user"]["username"], "ann")
        self.assertTrue(ApiToken.objects.filter(owner=self.ann, name="Mobile app").exists())

    def test_a_code_works_once(self):
        code = self.code_after_signing_in()
        self.assertEqual(exchange(Client(), code).status_code, 200)
        self.assertEqual(exchange(Client(), code).status_code, 400)

    def test_a_stolen_code_is_useless_without_the_apps_secret(self):
        code = self.code_after_signing_in()
        self.assertEqual(exchange(Client(), code, verifier="some-other-secret").status_code, 400)
        self.assertEqual(exchange(Client(), code).status_code, 400)  # and a wrong try burns the code

    def test_finish_without_a_start_hands_out_nothing(self):
        self.browser.force_login(self.ann)
        r = self.browser.get(reverse("mobile_signin_finish"))
        self.assertEqual(r.status_code, 400)
        self.assertNotContains(r, "stillopen://auth", status_code=400)

    def test_finish_needs_a_signed_in_person(self):
        self.browser.get(reverse("mobile_signin_start"), {"challenge": CHALLENGE})
        self.assertEqual(self.browser.get(reverse("mobile_signin_finish")).status_code, 302)

    def test_garbage_to_the_exchange_is_a_clean_400(self):
        c = Client()
        for body in ("not json", json.dumps([1]), json.dumps({"code": 5, "verifier": 6}), json.dumps({})):
            self.assertEqual(c.post(reverse("mobile_signin_exchange"), data=body, content_type="application/json").status_code, 400)

    def test_a_turned_off_account_gets_no_token(self):
        code = self.code_after_signing_in()
        User.objects.filter(pk=self.ann.pk).update(is_active=False)
        self.assertEqual(exchange(Client(), code).status_code, 400)
