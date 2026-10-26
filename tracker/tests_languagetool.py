"""Grammar/clarity check (LanguageTool): off by default, nothing sent anywhere without a configured server."""
from unittest import mock

from django.test import SimpleTestCase, TestCase

from tracker.models import SiteConfig
from tracker.services import languagetool
from tracker.services.languagetool import LanguageToolError


class Check(SimpleTestCase):
    def config(self, url=""):
        c = SiteConfig(languagetool_url=url)
        return c

    def test_available_only_with_a_url(self):
        self.assertFalse(languagetool.available(self.config()))
        self.assertTrue(languagetool.available(self.config("http://localhost:8010")))

    def test_raises_without_a_configured_server(self):
        with self.assertRaises(LanguageToolError):
            languagetool.check("Some text.", self.config())

    def test_empty_text_is_not_sent_and_returns_nothing(self):
        with mock.patch("requests.post") as post:
            self.assertEqual(languagetool.check("   ", self.config("http://localhost:8010")), [])
            post.assert_not_called()

    @mock.patch("requests.post")
    def test_parses_matches_into_the_apps_own_shape(self, post):
        payload = {
            "matches": [
                {
                    "message": "Did you mean 'receive'?", "shortMessage": "Spelling",
                    "offset": 7, "length": 7, "rule": {"category": {"name": "Spelling"}},
                    "replacements": [{"value": "receive"}, {"value": "recieve"}],
                },
            ]
        }
        post.return_value = mock.Mock(status_code=200, **{"json.return_value": payload})
        out = languagetool.check("I will recieve the offer.", self.config("http://localhost:8010"))
        post.assert_called_once()
        self.assertEqual(post.call_args.args[0], "http://localhost:8010/v2/check")
        self.assertEqual(out, [{
            "message": "Did you mean 'receive'?", "short_message": "Spelling", "context": "recieve",
            "offset": 7, "length": 7, "category": "Spelling", "suggestions": ["receive", "recieve"],
        }])

    @mock.patch("requests.post")
    def test_network_or_bad_status_is_a_plain_error(self, post):
        import requests as rq
        post.side_effect = rq.ConnectionError("boom")
        with self.assertRaises(LanguageToolError):
            languagetool.check("x", self.config("http://localhost:8010"))
        post.side_effect = None
        post.return_value = mock.Mock(status_code=500)
        with self.assertRaises(LanguageToolError):
            languagetool.check("x", self.config("http://localhost:8010"))

    def test_env_override_takes_precedence_and_trailing_slash_is_stripped(self):
        with mock.patch.dict("os.environ", {"LANGUAGETOOL_URL": "http://env:8010/"}):
            self.assertEqual(self.config("http://admin:8010").effective_languagetool_url, "http://env:8010")


from tracker.tests_apply import job, person  # noqa: E402
from tracker.tests_cv import PW  # noqa: E402


class WritingCheckApi(TestCase):
    def setUp(self):
        self.u = person("jane")
        self.app = job(self.u)
        self.client.login(username="jane", password=PW)

    def test_cv_writing_check_off_by_default(self):
        from tracker.models import CVVersion

        v = CVVersion.objects.create(owner=self.u, application=self.app, kind="tailored", label="x", content="Some text.")
        resp = self.client.post(f"/api/v1/cv/{v.pk}/writing-check")
        self.assertEqual(resp.status_code, 400)

    @mock.patch("requests.post")
    def test_cv_writing_check_when_configured(self, post):
        from tracker.models import CVVersion

        SiteConfig.objects.filter(pk=1).update(languagetool_url="http://localhost:8010")
        post.return_value = mock.Mock(status_code=200, **{"json.return_value": {"matches": []}})
        v = CVVersion.objects.create(owner=self.u, application=self.app, kind="tailored", label="x", content="Some text.")
        resp = self.client.post(f"/api/v1/cv/{v.pk}/writing-check")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["matches"], [])
        self.assertEqual(post.call_args.kwargs["data"]["text"], "Some text.")

    def test_cover_letter_writing_check_off_by_default(self):
        from tracker.models import CoverLetter

        letter = CoverLetter.objects.create(owner=self.u, application=self.app, content="Dear hiring manager.")
        resp = self.client.post(f"/api/v1/cover/{letter.pk}/writing-check")
        self.assertEqual(resp.status_code, 400)

    def test_writing_check_is_owner_scoped(self):
        from tracker.models import CVVersion

        other = person("bob")
        v = CVVersion.objects.create(owner=other, application=job(other), kind="tailored", label="x", content="x")
        SiteConfig.objects.filter(pk=1).update(languagetool_url="http://localhost:8010")
        resp = self.client.post(f"/api/v1/cv/{v.pk}/writing-check")
        self.assertEqual(resp.status_code, 404)
