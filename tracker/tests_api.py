"""The JSON API behind the new app: signed-out calls are refused, another person's job is a 404, and the rules of the classic pages hold."""
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from tracker.api import api
from tracker.tests import close_quietly
from tracker.models import Application, Event, SiteConfig, Status, UserProfile

User = get_user_model()
PW = "correct-horse-battery-staple"
BASE = "/api/v1"


def person(name):
    return User.objects.create_user(name, email=f"{name}@example.com", password=PW)


def job(owner, **kw):
    fields = {"owner": owner, "company": "Acme", "role": "Dev", "status": Status.objects.get(name="Evaluated")}
    fields.update(kw)
    return Application.objects.create(**fields)


def routes():
    """(method, path template) for every operation in the OpenAPI schema -- enumerated, never listed by hand."""
    schema = api.get_openapi_schema()
    found = []
    for path, methods in schema["paths"].items():
        for method in methods:
            found.append((method.upper(), path))
    return found


class RouteInventory(TestCase):
    """A new route cannot be added without these checks applying to it."""

    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        self.job_a, self.job_b = job(self.a, company="AliceCo"), job(self.b, company="BobCo")

    def fill(self, path, pk):
        return path.replace("{job_id}", str(pk))

    def body(self, method):
        return {"status": Status.objects.get(name="Applied").pk} if method == "PATCH" else None

    def call(self, client, method, path, pk):
        url = self.fill(path, pk)
        kwargs = {"content_type": "application/json"}
        body = self.body(method)
        if body is not None:
            import json
            kwargs["data"] = json.dumps(body)
        return getattr(client, method.lower())(url, **kwargs)

    def test_there_are_routes(self):
        self.assertGreaterEqual(len(routes()), 8)

    def test_every_route_refuses_a_signed_out_caller_with_json_401(self):
        client = Client()
        for method, path in routes():
            r = self.call(client, method, path, self.job_a.pk)
            self.assertEqual(r.status_code, 401, f"{method} {path} must answer 401 when signed out")
            self.assertTrue(r["Content-Type"].startswith("application/json"), f"{method} {path}")
        self.assertEqual(Application.objects.get(pk=self.job_a.pk).status.name, "Evaluated")

    def test_every_route_with_an_id_is_a_404_for_someone_elses_job(self):
        client = Client()
        client.force_login(self.a)
        checked = 0
        for method, path in routes():
            if "{job_id}" not in path:
                continue
            r = self.call(client, method, path, self.job_b.pk)
            self.assertEqual(r.status_code, 404, f"{method} {path} must answer 404 for another person's job")
            checked += 1
        self.assertGreaterEqual(checked, 2)
        self.assertEqual(Application.objects.get(pk=self.job_b.pk).status.name, "Evaluated")
        self.assertFalse(Event.objects.filter(application=self.job_b).exists())

    def test_unsupported_methods_are_405(self):
        client = Client()
        client.force_login(self.a)
        for method, path in routes():
            other = "DELETE" if method != "DELETE" else "PUT"
            r = getattr(client, other.lower())(self.fill(path, self.job_a.pk), content_type="application/json")
            self.assertEqual(r.status_code, 405, f"{other} {path} must not be allowed")

    def test_unsafe_methods_need_the_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.a)
        applied = Status.objects.get(name="Applied")
        r = client.patch(f"{BASE}/jobs/{self.job_a.pk}/status", data={"status": applied.pk}, content_type="application/json")
        self.assertEqual(r.status_code, 403)
        self.assertEqual(Application.objects.get(pk=self.job_a.pk).status.name, "Evaluated")


class Dashboard(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        self.job_a = job(self.a, company="AliceCo", summary="alice summary", score=4.0)
        self.job_b = job(self.b, company="BobCo", summary="bob summary")
        self.client.force_login(self.a)

    def test_lists_only_my_jobs_and_the_columns(self):
        data = self.client.get(f"{BASE}/dashboard").json()
        self.assertEqual([j["company"] for j in data["jobs"]], ["AliceCo"])
        self.assertNotIn("BobCo", str(data))
        self.assertEqual(data["jobs"][0]["percent"], 80)
        self.assertEqual(data["stats"]["total"], 1)
        names = {s["name"] for s in data["statuses"]}
        self.assertTrue({"Evaluated", "Applied"} <= names)
        self.assertEqual({s["bucket_key"] for s in data["statuses"]} - {b["key"] for b in data["buckets"]}, set())
        job_status = next(s for s in data["statuses"] if s["id"] == data["jobs"][0]["status_id"])
        self.assertEqual(job_status["bucket_key"], data["jobs"][0]["bucket_key"])

    def test_me(self):
        data = self.client.get(f"{BASE}/me").json()
        self.assertEqual(data["id"], self.a.pk)
        self.assertNotIn("password", str(data).lower())


class StatusChange(TestCase):
    def setUp(self):
        cache.clear()
        self.a = person("alice")
        self.job = job(self.a)
        self.client.force_login(self.a)

    def move(self, name):
        status = Status.objects.get(name=name)
        return self.client.patch(f"{BASE}/jobs/{self.job.pk}/status", data={"status": status.pk}, content_type="application/json")

    def test_same_rule_as_the_classic_page(self):
        applied = Status.objects.filter(counts_as_applied=True).first()
        r = self.move(applied.name)
        self.assertEqual(r.status_code, 200)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status_id, applied.pk)
        self.assertIsNotNone(self.job.applied_date)
        self.assertEqual(self.job.events.filter(kind="applied").count(), 1)
        self.assertEqual(r.json()["bucket_key"], applied.bucket.key)

    def test_moving_to_the_same_status_writes_nothing(self):
        self.move("Evaluated")
        self.assertFalse(self.job.events.exists())

    def test_unknown_status_is_404(self):
        r = self.client.patch(f"{BASE}/jobs/{self.job.pk}/status", data={"status": 99999}, content_type="application/json")
        self.assertEqual(r.status_code, 404)

    def test_bad_body_is_refused(self):
        r = self.client.patch(f"{BASE}/jobs/{self.job.pk}/status", data={"nope": 1}, content_type="application/json")
        self.assertEqual(r.status_code, 422)


class Progress(TestCase):
    def setUp(self):
        cache.clear()
        self.a = person("alice")
        self.client.force_login(self.a)

    def test_status_endpoints_with_no_run(self):
        for path in ("scan/status", "liveness/status"):
            data = self.client.get(f"{BASE}/{path}").json()
            self.assertEqual((data["running"], data["done"], data["total"]), (False, 0, 0))


class NewAppShell(TestCase):
    def setUp(self):
        cache.clear()
        self.a = person("alice")
        self.out = tempfile.TemporaryDirectory()
        self.addCleanup(self.out.cleanup)
        root = Path(self.out.name)
        (root / "_next" / "static").mkdir(parents=True)
        (root / "index.html").write_text("<html>shell</html>", encoding="utf-8")
        (root / "_next" / "static" / "app.js").write_text("console.log(1)", encoding="utf-8")
        (root.parent / "secret.txt").write_text("nope", encoding="utf-8")
        self.addCleanup(lambda: (root.parent / "secret.txt").unlink(missing_ok=True))
        self.override = override_settings(STILLOPEN_FRONTEND_DIR=self.out.name)
        self.override.enable()
        self.addCleanup(self.override.disable)

    def switch(self, site=True, person_on=True):
        SiteConfig.objects.update(new_app_enabled=site)
        UserProfile.objects.filter(user=self.a).update(use_new_app=person_on)

    def test_signed_out_goes_to_sign_in(self):
        self.switch()
        r = self.client.get("/app/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r["Location"])
        self.assertIn("next=", r["Location"])

    def test_off_site_wide_sends_people_to_the_classic_dashboard(self):
        self.client.force_login(self.a)
        self.switch(site=False)
        self.assertRedirects(self.client.get("/app/"), reverse("dashboard"), fetch_redirect_response=False)

    def test_a_person_who_did_not_opt_in_is_sent_to_their_profile(self):
        self.client.force_login(self.a)
        self.switch(person_on=False)
        self.assertRedirects(self.client.get("/app/"), reverse("profile"), fetch_redirect_response=False)

    def test_shell_for_any_deep_path_and_sets_the_csrf_cookie(self):
        self.client.force_login(self.a)
        self.switch()
        for path in ("/app/", "/app/jobs/12", "/app/prep/3/today"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertIn(b"shell", b"".join(r.streaming_content))
            close_quietly(r)
            self.assertEqual(r["Cache-Control"], "no-store")
        self.assertIn("csrftoken", self.client.cookies)

    def test_classic_dashboard_sends_an_opted_in_person_to_the_app_unless_asked(self):
        self.client.force_login(self.a)
        self.switch()
        self.assertRedirects(self.client.get(reverse("dashboard")), "/app/", fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("dashboard") + "?classic=1").status_code, 200)

    def test_not_built_is_a_404(self):
        self.client.force_login(self.a)
        self.switch()
        (Path(self.out.name) / "index.html").unlink()
        self.assertEqual(self.client.get("/app/").status_code, 404)

    def test_assets_are_served_with_long_cache_and_cannot_escape_the_folder(self):
        r = self.client.get("/app/_next/static/app.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("immutable", r["Cache-Control"])
        close_quietly(r)
        self.assertEqual(self.client.get("/app/_next/static/missing.js").status_code, 404)
        self.assertEqual(self.client.get("/app/_next/../secret.txt").status_code, 404)
        self.assertEqual(self.client.get("/app/_next/%2e%2e/secret.txt").status_code, 404)
