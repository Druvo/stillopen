"""The mobile bearer-token auth path on `/api/v1/`: login issues a usable token, a bad one is refused, a revoked
one stops working, and a read-only token cannot write. Session+CSRF (the web app) is covered by `tests_api.py`."""
import json

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from tracker.models import ApiToken, Application, CVVersion, Status

User = get_user_model()
PW = "correct-horse-battery-staple"


def auth(token: str) -> dict:
    return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


class MobileLogin(TestCase):
    def setUp(self):
        cache.clear()
        self.ann = User.objects.create_user("ann", email="ann@example.com", password=PW)
        self.client = Client()

    def test_correct_credentials_return_a_usable_token(self):
        r = self.client.post("/api/v1/auth/login", data=json.dumps({"username": "ann", "password": PW}), content_type="application/json")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertTrue(body["token"].startswith(ApiToken.PREFIX))
        self.assertEqual(body["user"]["username"], "ann")
        record = ApiToken.objects.get(owner=self.ann)
        self.assertTrue(record.can_write)
        self.assertIsNotNone(ApiToken.lookup(body["token"]))

    def test_also_works_by_email(self):
        r = self.client.post("/api/v1/auth/login", data=json.dumps({"username": "ann@example.com", "password": PW}), content_type="application/json")
        self.assertEqual(r.status_code, 200)

    def test_wrong_password_is_401_not_a_token(self):
        r = self.client.post("/api/v1/auth/login", data=json.dumps({"username": "ann", "password": "nope"}), content_type="application/json")
        self.assertEqual(r.status_code, 401)
        self.assertFalse(ApiToken.objects.filter(owner=self.ann).exists())

    def test_unknown_username_is_401(self):
        r = self.client.post("/api/v1/auth/login", data=json.dumps({"username": "ghost", "password": "x"}), content_type="application/json")
        self.assertEqual(r.status_code, 401)

    def test_a_token_this_endpoint_issues_also_authenticates_mcp(self):
        """One personal access token, usable on both the JSON API and /mcp/ -- the point of reusing `ApiToken`."""
        from tracker.models import SiteConfig

        SiteConfig.objects.update(mcp_remote_enabled=True)
        r = self.client.post("/api/v1/auth/login", data=json.dumps({"username": "ann", "password": PW}), content_type="application/json")
        token = r.json()["token"]
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        reply = self.client.post("/mcp/", data=json.dumps(body), content_type="application/json", **auth(token))
        self.assertEqual(reply.status_code, 200)
        self.assertIn("result", reply.json())


class MobileBearerAuth(TestCase):
    def setUp(self):
        cache.clear()
        self.ann = User.objects.create_user("ann", email="ann@example.com", password=PW)
        self.bob = User.objects.create_user("bob", email="bob@example.com", password=PW)
        self.job = Application.objects.create(owner=self.ann, company="Acme", role="Dev", status=Status.objects.get(name="Evaluated"))
        self.read_record, self.read_token = ApiToken.issue(self.ann, "read", can_write=False)
        self.write_record, self.write_token = ApiToken.issue(self.ann, "write", can_write=True)
        self.client = Client()

    def test_a_valid_token_reads_as_its_owner(self):
        r = self.client.get("/api/v1/me", **auth(self.write_token))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["id"], self.ann.pk)

    def test_a_bad_token_is_401(self):
        r = self.client.get("/api/v1/me", **auth("so_not-a-real-token"))
        self.assertEqual(r.status_code, 401)

    def test_no_token_and_no_session_is_401(self):
        r = self.client.get("/api/v1/me")
        self.assertEqual(r.status_code, 401)

    def test_a_write_token_can_change_a_status_no_csrf_needed(self):
        """The web app needs a CSRF header on an unsafe method; a bearer-authenticated mobile call must not."""
        applied = Status.objects.get(name="Applied")
        r = self.client.patch(f"/api/v1/jobs/{self.job.pk}/status", data=json.dumps({"status": applied.pk}), content_type="application/json", **auth(self.write_token))
        self.assertEqual(r.status_code, 200)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status_id, applied.pk)

    def test_a_read_only_token_cannot_write(self):
        applied = Status.objects.get(name="Applied")
        r = self.client.patch(f"/api/v1/jobs/{self.job.pk}/status", data=json.dumps({"status": applied.pk}), content_type="application/json", **auth(self.read_token))
        self.assertEqual(r.status_code, 401)

    def test_a_revoked_token_stops_working(self):
        ApiToken.objects.filter(pk=self.write_record.pk).update(revoked_at=None)  # sanity: active first
        self.client.post("/api/v1/auth/logout", **auth(self.write_token))
        r = self.client.get("/api/v1/me", **auth(self.write_token))
        self.assertEqual(r.status_code, 401)

    def test_a_token_never_sees_someone_elses_job(self):
        bob_job = Application.objects.create(owner=self.bob, company="Other", role="Dev", status=Status.objects.get(name="Evaluated"))
        r = self.client.get(f"/api/v1/jobs/{bob_job.pk}/details", **auth(self.write_token))
        self.assertEqual(r.status_code, 404)


class MobileCvDownload(TestCase):
    """The one classic (non-JSON) view a mobile client must reach directly: a CV file download."""

    def setUp(self):
        cache.clear()
        self.ann = User.objects.create_user("ann", email="ann@example.com", password=PW)
        self.bob = User.objects.create_user("bob", email="bob@example.com", password=PW)
        self.version = CVVersion.objects.create(owner=self.ann, kind="master", source="manual", content="# Ann Example\n\nSUMMARY\n\nBuilds things.", approved=True)
        _, self.token = ApiToken.issue(self.ann, "mobile", can_write=True)
        self.client = Client()

    def test_a_valid_bearer_token_downloads_the_file(self):
        r = self.client.get(reverse("cv_download", args=[self.version.pk, "md"]), **auth(self.token))
        self.assertEqual(r.status_code, 200)

    def test_no_token_and_no_session_redirects_to_login(self):
        r = self.client.get(reverse("cv_download", args=[self.version.pk, "md"]))
        self.assertEqual(r.status_code, 302)

    def test_a_bad_token_is_401_not_a_login_redirect(self):
        r = self.client.get(reverse("cv_download", args=[self.version.pk, "md"]), **auth("so_not-a-real-token"))
        self.assertEqual(r.status_code, 401)

    def test_a_token_cannot_download_someone_elses_cv(self):
        _, bob_token = ApiToken.issue(self.bob, "mobile", can_write=True)
        r = self.client.get(reverse("cv_download", args=[self.version.pk, "md"]), **auth(bob_token))
        self.assertEqual(r.status_code, 404)
