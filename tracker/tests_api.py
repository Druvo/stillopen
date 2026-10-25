"""The JSON API behind the new app: signed-out calls are refused, another person's job is a 404, and the rules the old pages had hold."""
import json
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase, override_settings

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


def _world_modules():
    """Every `tracker/world_<area>.py`: each API area describes its own fixtures for the route inventory.

    A module defines `world(owner, ids) -> {path parameter name: id}` (rows owned by `owner`, one set per person; `ids` holds what
    earlier modules made, e.g. `job_id`) and may define `BODIES = {("POST", "/path/{param}"): {...json...}}` for routes that need a body
    to get past validation. Path parameter names must be unique per resource (`cv_id`, `contact_id`, ...)."""
    import importlib
    import pkgutil

    import tracker

    return [importlib.import_module(f"tracker.{i.name}") for i in pkgutil.iter_modules(tracker.__path__) if i.name.startswith("world_")]


WORLD_MODULES = _world_modules()
EXTRA_BODIES = {key: body for module in WORLD_MODULES for key, body in getattr(module, "BODIES", {}).items()}


def world(owner):
    """One job and one started prep plan (a week with a lesson, a task and two questions) for `owner`; returns the ids by parameter name."""
    from tracker.models import PrepLesson, PrepMilestone, PrepPlan, PrepQuestion, PrepTopic, PrepWeek

    app = job(owner, company=f"{owner.username}-co")
    plan = PrepPlan.objects.create(owner=owner, application=app, title="Plan", status="active")
    week = PrepWeek.objects.create(plan=plan, order=1, title="W1", hours=6)
    lesson = PrepLesson.objects.create(week=week, order=1, title="L1", gap="K8s", sources=[{"title": "Docs", "url": "https://kubernetes.io/docs/"}])
    milestone = PrepMilestone.objects.create(week=week, kind="build", text="Build it")
    topic = PrepTopic.objects.create(plan=plan, slug="pods", title="Pods")
    questions = [
        PrepQuestion.objects.create(plan=plan, topic=topic, lesson=lesson, prompt=f"Q{n}", choices=["a", "b"], correct=[0], explanation="because the docs say so",
                                    sources=[{"title": "Docs", "url": "https://kubernetes.io/docs/"}])
        for n in range(2)
    ]
    ids = {"job_id": app.pk, "plan_id": plan.pk, "lesson_id": lesson.pk, "milestone_id": milestone.pk, "question_id": questions[0].pk}
    for module in WORLD_MODULES:
        ids.update(module.world(owner, dict(ids)))
    return ids


class RouteInventory(TestCase):
    """A new route cannot be added without these checks applying to it."""

    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        self.ids_a, self.ids_b = world(self.a), world(self.b)
        self.job_a, self.job_b = Application.objects.get(pk=self.ids_a["job_id"]), Application.objects.get(pk=self.ids_b["job_id"])

    def fill(self, path, ids):
        for name, pk in ids.items():
            path = path.replace("{" + name + "}", str(pk))
        return path

    def body(self, method, path):
        if (method, path) in EXTRA_BODIES:
            return EXTRA_BODIES[(method, path)]
        if method == "PATCH":
            return {"status": Status.objects.get(name="Applied").pk}
        if path.endswith("/prep"):
            return {}
        if path.endswith("/answers"):
            return {"answers": {}}
        return None

    def call(self, client, method, path, ids):
        kwargs = {"content_type": "application/json"}
        body = self.body(method, path)
        if body is not None:
            kwargs["data"] = json.dumps(body)
        return getattr(client, method.lower())(self.fill(path, ids), **kwargs)

    def test_there_are_routes(self):
        self.assertGreaterEqual(len(routes()), 18)

    def test_every_route_refuses_a_signed_out_caller_with_json_401(self):
        client = Client()
        for method, path in routes():
            r = self.call(client, method, path, self.ids_a)
            self.assertEqual(r.status_code, 401, f"{method} {path} must answer 401 when signed out")
            self.assertTrue(r["Content-Type"].startswith("application/json"), f"{method} {path}")
        self.assertEqual(Application.objects.get(pk=self.job_a.pk).status.name, "Evaluated")

    def test_every_route_with_an_id_is_a_404_for_someone_elses_object(self):
        client = Client()
        client.force_login(self.a)
        checked = 0
        for method, path in routes():
            if "{" not in path:
                continue
            r = self.call(client, method, path, self.ids_b)
            self.assertEqual(r.status_code, 404, f"{method} {path} must answer 404 for another person's object")
            checked += 1
        self.assertGreaterEqual(checked, 12)
        self.assertEqual(Application.objects.get(pk=self.job_b.pk).status.name, "Evaluated")
        self.assertFalse(Event.objects.filter(application=self.job_b).exists())
        from tracker.models import PrepLesson, PrepPlan, PrepQuestion

        self.assertTrue(PrepPlan.objects.filter(pk=self.ids_b["plan_id"]).exists())
        self.assertTrue(PrepLesson.objects.filter(pk=self.ids_b["lesson_id"], done_at__isnull=True).exists())
        self.assertTrue(PrepQuestion.objects.filter(pk=self.ids_b["question_id"], removed=False).exists())

    def test_unsupported_methods_are_405(self):
        client = Client()
        client.force_login(self.a)
        allowed = {}
        for method, path in routes():
            allowed.setdefault(path, set()).add(method)
        for path, methods in allowed.items():
            other = next(m for m in ("PUT", "DELETE", "PATCH") if m not in methods)
            r = getattr(client, other.lower())(self.fill(path, self.ids_a), content_type="application/json")
            self.assertEqual(r.status_code, 405, f"{other} {path} must not be allowed")

    def test_unsafe_methods_need_the_csrf_token(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.a)
        applied = Status.objects.get(name="Applied")
        r = client.patch(f"{BASE}/jobs/{self.job_a.pk}/status", data={"status": applied.pk}, content_type="application/json")
        self.assertEqual(r.status_code, 403)
        r = client.delete(f"{BASE}/prep/plans/{self.ids_a['plan_id']}")
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

    def test_signed_out_goes_to_sign_in(self):
        r = self.client.get("/app/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r["Location"])
        self.assertIn("next=", r["Location"])

    def test_shell_for_any_deep_path_and_sets_the_csrf_cookie(self):
        self.client.force_login(self.a)
        for path in ("/app/", "/app/jobs/12", "/app/prep/3/today"):
            r = self.client.get(path)
            self.assertEqual(r.status_code, 200, path)
            self.assertIn(b"shell", b"".join(r.streaming_content))
            close_quietly(r)
            self.assertEqual(r["Cache-Control"], "no-store")
        self.assertIn("csrftoken", self.client.cookies)

    def test_the_page_carries_a_strict_policy_with_the_hashes_of_its_inline_scripts(self):
        import base64
        import hashlib

        (Path(self.out.name) / "index.html").write_text('<html><script>var a=1;</script><script src="/app/_next/static/x.js"></script><script>var b=2;</script></html>', encoding="utf-8")
        self.client.force_login(self.a)
        r = self.client.get("/app/")
        policy = r["Content-Security-Policy"]
        close_quietly(r)
        for body in (b"var a=1;", b"var b=2;"):
            self.assertIn("'sha256-" + base64.b64encode(hashlib.sha256(body).digest()).decode() + "'", policy)
        script_src = next(p for p in policy.split("; ") if p.startswith("script-src"))
        self.assertNotIn("unsafe-inline", script_src)
        self.assertNotIn("unsafe-eval", policy)
        self.assertIn("default-src 'self'", policy)
        self.assertIn("frame-ancestors 'none'", policy)
        self.assertEqual(script_src.count("'sha256-"), 2, script_src)  # the external script needs no hash

    @override_settings(STILLOPEN_APP_CSP=False)
    def test_the_policy_can_be_switched_off(self):
        self.client.force_login(self.a)
        r = self.client.get("/app/")
        close_quietly(r)
        self.assertNotIn("Content-Security-Policy", r)

    def test_not_built_says_so_in_plain_words_with_a_503(self):
        self.client.force_login(self.a)
        (Path(self.out.name) / "index.html").unlink()
        r = self.client.get("/app/")
        self.assertEqual(r.status_code, 503)
        self.assertIn("text/html", r["Content-Type"])
        page = r.content.decode()
        self.assertIn("pnpm build", page)
        self.assertIn("Docker", page)
        self.assertEqual(self.client.get("/app/jobs/3").status_code, 503)

    def test_everyone_signed_in_gets_the_app_with_no_switch(self):
        self.client.force_login(self.a)
        r = self.client.get("/app/")
        self.assertEqual(r.status_code, 200)
        close_quietly(r)

    def test_assets_are_served_with_long_cache_and_cannot_escape_the_folder(self):
        r = self.client.get("/app/_next/static/app.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("immutable", r["Cache-Control"])
        close_quietly(r)
        self.assertEqual(self.client.get("/app/_next/static/missing.js").status_code, 404)
        self.assertEqual(self.client.get("/app/_next/../secret.txt").status_code, 404)
        self.assertEqual(self.client.get("/app/_next/%2e%2e/secret.txt").status_code, 404)


class PrepApi(TestCase):
    def setUp(self):
        cache.clear()
        self.a = person("alice")
        self.client.force_login(self.a)
        self.ids = world(self.a)
        from tracker.models import PrepPlan

        self.plan = PrepPlan.objects.get(pk=self.ids["plan_id"])

    def url(self, tail):
        return f"{BASE}/prep/plans/{self.plan.pk}{tail}"

    def post(self, url, body=None):
        return self.client.post(url, data=json.dumps(body or {}), content_type="application/json")

    def test_list_and_detail(self):
        rows = self.client.get(f"{BASE}/prep/plans").json()["plans"]
        self.assertEqual([(r["id"], r["lessons_done"], r["lessons_total"]) for r in rows], [(self.plan.pk, 0, 1)])
        detail = self.client.get(self.url("")).json()
        self.assertEqual(detail["status"], "active")
        self.assertEqual(detail["weeks"][0]["lessons"][0]["title"], "L1")
        self.assertEqual(detail["question_count"], 2)
        self.assertNotIn("questions", detail["weeks"][0]["lessons"][0])  # questions and answers are shown only while reviewing a draft

    def test_a_draft_shows_questions_for_review_and_can_be_started(self):
        self.plan.status = "draft"
        self.plan.save()
        lesson = self.client.get(self.url("")).json()["weeks"][0]["lessons"][0]
        self.assertEqual(len(lesson["questions"]), 2)
        self.assertEqual(self.client.delete(f"{BASE}/prep/questions/{self.ids['question_id']}").status_code, 200)
        self.assertEqual(len(self.client.get(self.url("")).json()["weeks"][0]["lessons"][0]["questions"]), 1)
        self.assertEqual(self.post(self.url("/start")).status_code, 200)
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, "active")

    def test_removing_once_started_changes_nothing(self):
        self.client.delete(f"{BASE}/prep/questions/{self.ids['question_id']}")
        self.client.delete(f"{BASE}/prep/lessons/{self.ids['lesson_id']}")
        self.assertEqual(self.client.get(self.url("")).json()["question_count"], 2)

    def test_ticking_finishes_and_reopens_the_plan(self):
        r = self.post(f"{BASE}/prep/lessons/{self.ids['lesson_id']}/tick")
        self.assertTrue(r.json()["done"])
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, "done")
        self.assertFalse(self.post(f"{BASE}/prep/lessons/{self.ids['lesson_id']}/tick").json()["done"])
        self.plan.refresh_from_db()
        self.assertEqual(self.plan.status, "active")
        self.assertTrue(self.post(f"{BASE}/prep/milestones/{self.ids['milestone_id']}/tick").json()["done"])

    def test_a_plan_being_written_cannot_be_discarded_but_a_finished_one_can(self):
        self.plan.status = "generating"
        self.plan.save()
        r = self.client.delete(self.url(""))
        self.assertEqual(r.status_code, 400)
        self.assertIn("still being written", r.json()["error"])
        self.plan.status = "active"
        self.plan.save()
        self.assertEqual(self.client.delete(self.url("")).status_code, 200)
        self.assertEqual(self.client.get(self.url("")).status_code, 404)

    def test_creating_again_returns_the_existing_plan(self):
        r = self.post(f"{BASE}/jobs/{self.ids['job_id']}/prep")
        self.assertEqual(r.json(), {"id": self.plan.pk, "existing": True})

    def test_creating_without_an_ai_account_says_what_to_do(self):
        from tracker.models import PrepPlan

        self.plan.delete()
        r = self.post(f"{BASE}/jobs/{self.ids['job_id']}/prep")
        self.assertEqual(r.status_code, 400)
        self.assertTrue(r.json()["error"])
        self.assertFalse(PrepPlan.objects.filter(owner=self.a).exists())

    def test_practice_gives_nothing_away_until_it_is_sent(self):
        data = self.client.get(self.url("/today")).json()
        self.assertFalse(data["finished"])
        self.assertEqual(data["total"], 2)
        for row in data["rows"]:
            self.assertEqual(set(row), {"id", "topic", "prompt", "kind", "choices", "review"})
        self.assertNotIn("because the docs say so", json.dumps(data))

    def test_answers_are_all_or_nothing_then_scored_and_explained(self):
        rows = self.client.get(self.url("/today")).json()["rows"]
        first, second = rows[0]["id"], rows[1]["id"]
        r = self.post(self.url("/answers"), {"answers": {str(first): [0]}})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(self.client.get(self.url("/today")).json()["finished"])
        r = self.post(self.url("/answers"), {"answers": {str(first): [0], str(second): [1]}})
        self.assertEqual(r.json()["right"], 1)
        data = self.client.get(self.url("/today")).json()
        self.assertTrue(data["finished"])
        self.assertEqual(data["right"], 1)
        self.assertEqual(data["streak"], 1)
        by_id = {row["id"]: row for row in data["rows"]}
        self.assertTrue(by_id[first]["right"])
        self.assertFalse(by_id[second]["right"])
        self.assertEqual(by_id[second]["chosen"], [1])
        self.assertEqual(by_id[second]["correct"], [0])
        self.assertEqual(by_id[second]["explanation"], "because the docs say so")
        self.assertEqual(self.post(self.url("/answers"), {"answers": {str(first): [0], str(second): [0]}}).status_code, 400)  # only once a day

    def test_practice_needs_a_started_plan(self):
        self.plan.status = "draft"
        self.plan.save()
        self.assertEqual(self.client.get(self.url("/today")).status_code, 404)

    def test_switched_off_by_the_admin_is_a_404_everywhere(self):
        SiteConfig.objects.update(prep_enabled=False)
        for url in (f"{BASE}/prep/plans", self.url(""), self.url("/today")):
            self.assertEqual(self.client.get(url).status_code, 404, url)
        self.assertEqual(self.post(f"{BASE}/jobs/{self.ids['job_id']}/prep").status_code, 404)


class E2ESeed(TestCase):
    """The browser tests' seed command makes users with a known password, so it must refuse to run on a real install."""

    def test_refuses_without_the_switch(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("e2e_seed")
        self.assertFalse(User.objects.filter(username__in=["alice", "bob"]).exists())

    def test_with_the_switch_it_makes_two_separate_people(self):
        import os
        from io import StringIO
        from unittest import mock

        from django.core.management import call_command

        with mock.patch.dict(os.environ, {"STILLOPEN_E2E": "1"}):
            call_command("e2e_seed", stdout=StringIO())
        alice, bob = User.objects.get(username="alice"), User.objects.get(username="bob")
        self.assertEqual(Application.objects.filter(owner=alice).count(), 3)
        self.assertEqual(Application.objects.filter(owner=bob).count(), 1)
        self.assertTrue(UserProfile.objects.get(user=alice).onboarding_done)
