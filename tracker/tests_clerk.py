"""Sign-in through Clerk. No network: Clerk's key list and user lookup are replaced, and tokens are signed with a key made here."""
import base64
import json
import time
from unittest import mock

import jwt
from allauth.account.models import EmailAddress
from cryptography.hazmat.primitives.asymmetric import rsa
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings

from tracker.models import SiteConfig, UserProfile
from tracker.services import clerkauth

User = get_user_model()
HOST = "clerk.example.test"
PUBLISHABLE = "pk_test_" + base64.b64encode(f"{HOST}$".encode()).decode().rstrip("=")
SECRET = "sk_test_not_a_real_key"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
JWK = {**json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(KEY.public_key())), "kid": "k1", "use": "sig", "alg": "RS256"}


def token(sub="user_1", key=KEY, issuer=f"https://{HOST}", exp_in=300, azp=None):
    now = int(time.time())
    claims = {"sub": sub, "iss": issuer, "iat": now, "nbf": now, "exp": now + exp_in}
    if azp:
        claims["azp"] = azp
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


def person(email="jane@example.com", verified=True):
    return {"email": email, "verified": verified, "first_name": "Jane", "last_name": "Doe"}


def clerk_on(test):
    config = SiteConfig.load()
    config.clerk_publishable_key = PUBLISHABLE
    config.set_clerk_secret(SECRET)
    config.signup_mode = "open"
    config.save()
    clerkauth._keys.clear()
    patcher = mock.patch.object(clerkauth, "_signing_keys", side_effect=lambda host, force=False: {"k1": KEY.public_key()})
    patcher.start()
    test.addCleanup(patcher.stop)


class ClerkOff(TestCase):
    def test_sign_in_page_is_the_built_in_one(self):
        r = self.client.get("/accounts/login/")
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "clerk-root")

    def test_exchange_is_not_there_while_off(self):
        r = self.client.post("/auth/clerk/session/", data=json.dumps({"token": "x"}), content_type="application/json")
        self.assertEqual(r.status_code, 404)

    def test_the_secret_is_stored_encrypted_and_env_wins(self):
        config = SiteConfig.load()
        config.clerk_publishable_key = PUBLISHABLE
        config.set_clerk_secret(SECRET)
        config.save()
        self.assertNotIn(SECRET, SiteConfig.load().clerk_secret_encrypted)
        self.assertEqual(SiteConfig.load().effective_clerk, (PUBLISHABLE, SECRET))
        with mock.patch.dict("os.environ", {"CLERK_SECRET_KEY": "sk_test_env"}):
            self.assertEqual(SiteConfig.load().effective_clerk[1], "sk_test_env")


class ClerkPage(TestCase):
    def setUp(self):
        cache.clear()
        clerk_on(self)

    def test_page_loads_clerk_from_the_instance_host_in_the_key(self):
        r = self.client.get("/accounts/login/")
        self.assertContains(r, f"https://{HOST}/npm/@clerk/clerk-js@6.40.1/")
        self.assertContains(r, PUBLISHABLE)
        self.assertNotContains(r, SECRET)

    def test_sign_up_page_asks_clerk_to_sign_up(self):
        self.assertContains(self.client.get("/accounts/signup/"), 'data-mode="signup"')

    def test_a_bad_publishable_key_is_a_plain_error(self):
        config = SiteConfig.load()
        config.clerk_publishable_key = "pk_test_!!!"
        config.save()
        self.assertEqual(self.client.get("/accounts/login/").status_code, 503)

    def test_logout_sends_the_person_to_a_page_that_ends_the_clerk_session_too(self):
        user = User.objects.create_user("lou", password="x" * 12)
        self.client.force_login(user)
        r = self.client.post("/accounts/logout/")
        self.assertRedirects(r, "/accounts/login/?signed_out=1", fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)


class ClerkExchange(TestCase):
    def setUp(self):
        cache.clear()
        clerk_on(self)

    def post(self, tok, **extra):
        return self.client.post("/auth/clerk/session/", data=json.dumps({"token": tok}), content_type="application/json", **extra)

    def sign_in(self, tok=None, who=None):
        with mock.patch.object(clerkauth, "fetch_person", return_value=who or person()):
            return self.post(tok or token())

    def test_first_sign_in_makes_the_person_and_signs_them_in(self):
        r = self.sign_in()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["next"], "/app/welcome")
        user = User.objects.get(email="jane@example.com")
        self.assertEqual(self.client.session["_auth_user_id"], str(user.pk))
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.is_staff)
        self.assertEqual(UserProfile.objects.get(user=user).clerk_user_id, "user_1")
        self.assertTrue(EmailAddress.objects.get(user=user).verified)

    def test_second_sign_in_is_the_same_person(self):
        self.sign_in()
        self.client.logout()
        self.sign_in()
        self.assertEqual(User.objects.filter(email="jane@example.com").count(), 1)

    def test_an_email_clerk_has_not_verified_is_refused(self):
        r = self.sign_in(who=person(verified=False))
        self.assertEqual(r.status_code, 403)
        self.assertFalse(User.objects.filter(email="jane@example.com").exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_never_attached_to_an_older_account_by_email(self):
        old = User.objects.create_user("jane", email="jane@example.com", password="x" * 12)
        self.sign_in()
        self.assertNotEqual(self.client.session["_auth_user_id"], str(old.pk))
        self.assertFalse(UserProfile.for_user(old).clerk_user_id)

    def test_a_token_signed_by_someone_else_is_refused(self):
        self.assertEqual(self.sign_in(token(key=OTHER_KEY)).status_code, 403)

    def test_expired_token_is_refused(self):
        self.assertEqual(self.sign_in(token(exp_in=-600)).status_code, 403)

    def test_token_from_another_clerk_address_is_refused(self):
        self.assertEqual(self.sign_in(token(issuer="https://evil.example.test")).status_code, 403)

    def test_token_made_for_another_site_is_refused(self):
        with mock.patch.object(clerkauth, "fetch_person", return_value=person()):
            r = self.post(token(azp="https://evil.example.test"), HTTP_ORIGIN="https://app.example.test")
        self.assertEqual(r.status_code, 403)

    def test_garbage_is_refused_not_a_crash(self):
        for body in ("not json", json.dumps([1]), json.dumps({"token": 5}), json.dumps({"token": "a.b.c"})):
            r = self.client.post("/auth/clerk/session/", data=body, content_type="application/json")
            self.assertIn(r.status_code, (400, 403), body)

    def test_closed_registration_keeps_new_people_out_but_not_returning_ones(self):
        self.sign_in()
        self.client.logout()
        config = SiteConfig.load()
        config.signup_mode = "closed"
        config.save()
        self.assertEqual(self.sign_in().status_code, 200)
        self.client.logout()
        self.assertEqual(self.sign_in(token("user_2"), person("new@example.com")).status_code, 403)

    def test_a_turned_off_account_cannot_sign_in(self):
        self.sign_in()
        self.client.logout()
        User.objects.filter(email="jane@example.com").update(is_active=False)
        self.assertEqual(self.sign_in().status_code, 403)

    def test_next_only_follows_this_site(self):
        with mock.patch.object(clerkauth, "fetch_person", return_value=person()):
            r = self.client.post("/auth/clerk/session/", data=json.dumps({"token": token(), "next": "https://evil.example.test/"}), content_type="application/json")
        self.assertEqual(r.json()["next"], "/app/welcome")

    @override_settings()
    def test_too_many_tries_are_slowed(self):
        with mock.patch("tracker.views_clerk.EXCHANGES_PER_HOUR", 2):
            codes = [self.post("junk").status_code for _ in range(4)]
        self.assertEqual(codes[-1], 429)

    def test_nothing_secret_in_any_answer(self):
        r = self.sign_in()
        self.assertNotIn(SECRET, r.content.decode())
