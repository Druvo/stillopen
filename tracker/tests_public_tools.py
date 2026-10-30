"""The free, no-sign-in tools: job fit, posting liveness, offer comparison. No account, nothing saved, rate
limited per IP. Bot-trap coverage lives once here (job-fit represents all three; they share the same mixin)."""
import re
import time
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse


def token(client, url):
    tag = re.search(r'<input[^>]*name="form_started"[^>]*>', client.get(url).content.decode()).group(0)
    return re.search(r'value="([^"]+)"', tag).group(1)


@override_settings(STILLOPEN_PUBLIC_TOOL_MIN_SECONDS=0)
class JobFitTool(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("tool_job_fit")

    def test_anyone_gets_a_plain_free_match_no_sign_in_needed(self):
        r = self.client.post(self.url, {
            "description": "We need a backend engineer who knows Docker Kubernetes and SQL Server. " * 3,
            "cv": "Backend engineer. Docker, Kubernetes, SQL Server, payment systems.",
        })
        self.assertEqual(r.status_code, 200)
        self.assertGreater(r.context["result"]["match_percent"], 0)
        self.assertNotIn("Sign in", r.context.get("error") or "")

    def test_a_blank_cv_is_a_friendly_error_not_a_crash(self):
        r = self.client.post(self.url, {"description": "Backend engineer needed, Docker and Kubernetes.", "cv": ""})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.context["result"])

    def test_nothing_is_saved(self):
        from tracker.models import Application

        before = Application.objects.count()
        self.client.post(self.url, {"description": "Backend engineer, Docker and Kubernetes. " * 3, "cv": "Docker, Kubernetes."})
        self.assertEqual(Application.objects.count(), before)


@override_settings(STILLOPEN_PUBLIC_TOOL_MIN_SECONDS=0)
class JobFitBotTraps(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("tool_job_fit")

    def data(self, **extra):
        out = {"description": "Backend engineer needed, Docker and Kubernetes. " * 3, "cv": "Docker, Kubernetes."}
        out.update(extra)
        return out

    def test_honeypot_filled_is_refused(self):
        r = self.client.post(self.url, self.data(website="http://spam.example"))
        self.assertIsNone(r.context["result"])

    @override_settings(STILLOPEN_PUBLIC_TOOL_MIN_SECONDS=3)
    def test_instant_submit_is_refused_then_a_patient_one_works(self):
        tok = token(self.client, self.url)
        r = self.client.post(self.url, self.data(form_started=tok))
        self.assertIsNone(r.context["result"])
        with mock.patch("tracker.forms.time.time", return_value=time.time() + 10):
            r = self.client.post(self.url, self.data(form_started=tok))
        self.assertIsNotNone(r.context["result"])

    @override_settings(STILLOPEN_PUBLIC_TOOL_MIN_SECONDS=3)
    def test_missing_or_tampered_token_is_refused(self):
        r = self.client.post(self.url, self.data(form_started="garbage"))
        self.assertIsNone(r.context["result"])

    def test_rate_limited_per_ip(self):
        with override_settings(STILLOPEN_PUBLIC_TOOL_RATE_PER_HOUR=2):
            codes = [self.client.post(self.url, self.data()).status_code for _ in range(4)]
        self.assertEqual(codes, [200, 200, 429, 429])


@override_settings(STILLOPEN_PUBLIC_TOOL_MIN_SECONDS=0)
class LivenessTool(TestCase):
    def setUp(self):
        from tracker.models import SiteConfig

        cache.clear()
        self.url = reverse("tool_liveness")
        SiteConfig.objects.filter(pk=1).update(liveness_mode="http")  # independent of this machine's CAREEROPS_PATH

    @mock.patch("tracker.services.liveness.safe_get")
    def test_reports_active_when_the_page_has_an_apply_control(self, get):
        get.return_value = mock.Mock(status_code=200, text="<html>Apply now</html>")
        r = self.client.post(self.url, {"url": "https://jobs.example.com/1"})
        self.assertEqual(r.context["result"]["state"], "active")

    @mock.patch("tracker.services.liveness.safe_get")
    def test_reports_expired_on_404(self, get):
        get.return_value = mock.Mock(status_code=404, text="")
        r = self.client.post(self.url, {"url": "https://jobs.example.com/1"})
        self.assertEqual(r.context["result"]["state"], "expired")

    def test_a_bad_url_is_a_form_error_not_a_crash(self):
        r = self.client.post(self.url, {"url": "not a url"})
        self.assertIsNone(r.context["result"])
        self.assertFalse(r.context["form"].is_valid())


@override_settings(STILLOPEN_PUBLIC_TOOL_MIN_SECONDS=0)
class OfferCompareTool(TestCase):
    def setUp(self):
        cache.clear()
        self.url = reverse("tool_offer_compare")

    def post(self, **over):
        data = {
            "a_label": "Acme", "a_base": "100000", "a_period": "year", "a_currency": "USD",
            "a_bonus": "10000", "a_equity": "0", "a_signing": "0", "a_other_benefits": "0",
            "b_label": "Globex", "b_base": "90000", "b_period": "year", "b_currency": "USD",
            "b_bonus": "0", "b_equity": "20000", "b_signing": "5000", "b_other_benefits": "0",
        }
        data.update(over)
        return self.client.post(self.url, data)

    def test_same_currency_lands_in_one_group_with_a_best(self):
        r = self.post()
        groups = r.context["groups"]
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["currency"], "USD")
        labels = [row["offer"].label for row in groups[0]["rows"]]
        self.assertEqual(labels, ["Acme", "Globex"])
        self.assertTrue(groups[0]["rows"][0]["best"])

    def test_different_currencies_are_never_converted(self):
        r = self.post(b_currency="MYR")
        groups = {g["currency"]: g for g in r.context["groups"]}
        self.assertEqual(set(groups), {"USD", "MYR"})

    def test_nothing_is_saved(self):
        from tracker.models import Offer

        before = Offer.objects.count()
        self.post()
        self.assertEqual(Offer.objects.count(), before)


class ToolsIndex(TestCase):
    def test_lists_all_three_tools_without_sign_in(self):
        page = self.client.get(reverse("tools_index")).content.decode()
        self.assertIn(reverse("tool_job_fit"), page)
        self.assertIn(reverse("tool_liveness"), page)
        self.assertIn(reverse("tool_offer_compare"), page)


class SampleInterviewQuestions(TestCase):
    def test_shows_questions_for_each_role_with_a_real_source(self):
        page = self.client.get(reverse("tool_sample_questions")).content.decode()
        self.assertIn("Backend Engineer", page)
        self.assertIn("ACID", page)
        self.assertIn("postgresql.org", page)

    def test_every_sample_question_has_a_correct_answer_and_a_source(self):
        from tracker import sample_questions

        for role in sample_questions.ROLES:
            for q in role["questions"]:
                self.assertTrue(0 <= q["correct"] < len(q["choices"]), q["prompt"])
                self.assertTrue(q["source"].get("url", "").startswith("https://"), q["prompt"])
                self.assertTrue(q["explanation"])


class ApiReference(TestCase):
    def test_lists_rest_endpoints_from_the_apis_own_schema_without_sign_in(self):
        page = self.client.get(reverse("api_reference")).content.decode()
        self.assertEqual(self.client.get(reverse("api_reference")).status_code, 200)
        self.assertIn("/api/v1/me", page)
        self.assertIn("/api/v1/dashboard", page)
        self.assertIn("The signed-in person", page)  # a real summary from the schema, not hand-written

    def test_lists_mcp_tools_with_their_read_only_access(self):
        page = self.client.get(reverse("api_reference")).content.decode()
        self.assertIn("summary", page)  # a real tool name
        self.assertIn("Read only", page)

    def test_never_lists_a_delete_tool(self):
        from tracker.mcp_registry import build_server

        tools = [t.name for t in self._list_tools(build_server())]
        self.assertFalse(any("delete" in name for name in tools))

    @staticmethod
    def _list_tools(server):
        from asgiref.sync import async_to_sync

        return async_to_sync(server.list_tools)()
