"""Translate a job description (LibreTranslate): off by default, nothing sent anywhere without a configured server."""
from unittest import mock

from django.test import SimpleTestCase, TestCase

from tracker.models import SiteConfig
from tracker.services import libretranslate
from tracker.services.libretranslate import TranslateError
from tracker.tests_apply import job, person
from tracker.tests_cv import PW


class Translate(SimpleTestCase):
    def config(self, url="", key=""):
        return SiteConfig(libretranslate_url=url, libretranslate_api_key=key)

    def test_available_only_with_a_url(self):
        self.assertFalse(libretranslate.available(self.config()))
        self.assertTrue(libretranslate.available(self.config("http://localhost:5000")))

    def test_raises_without_a_configured_server(self):
        with self.assertRaises(TranslateError):
            libretranslate.translate("Hallo Welt", self.config())

    def test_empty_text_is_not_sent_and_returns_empty(self):
        with mock.patch("requests.post") as post:
            self.assertEqual(libretranslate.translate("  ", self.config("http://localhost:5000")), "")
            post.assert_not_called()

    @mock.patch("requests.post")
    def test_posts_the_text_and_returns_the_translation(self, post):
        post.return_value = mock.Mock(status_code=200, **{"json.return_value": {"translatedText": "Hello world"}})
        out = libretranslate.translate("Hallo Welt", self.config("http://localhost:5000"), target="en")
        self.assertEqual(out, "Hello world")
        self.assertEqual(post.call_args.kwargs["json"], {"q": "Hallo Welt", "source": "auto", "target": "en", "format": "text"})

    @mock.patch("requests.post")
    def test_api_key_is_included_only_when_set(self, post):
        post.return_value = mock.Mock(status_code=200, **{"json.return_value": {"translatedText": "x"}})
        libretranslate.translate("x", self.config("http://localhost:5000", key="sekret"))
        self.assertEqual(post.call_args.kwargs["json"]["api_key"], "sekret")

    @mock.patch("requests.post")
    def test_network_or_bad_status_or_bad_shape_is_a_plain_error(self, post):
        import requests as rq
        post.side_effect = rq.ConnectionError("boom")
        with self.assertRaises(TranslateError):
            libretranslate.translate("x", self.config("http://localhost:5000"))
        post.side_effect = None
        post.return_value = mock.Mock(status_code=500)
        with self.assertRaises(TranslateError):
            libretranslate.translate("x", self.config("http://localhost:5000"))
        post.return_value = mock.Mock(status_code=200, **{"json.return_value": {"unexpected": "shape"}})
        with self.assertRaises(TranslateError):
            libretranslate.translate("x", self.config("http://localhost:5000"))

    def test_env_override_takes_precedence_and_trailing_slash_is_stripped(self):
        with mock.patch.dict("os.environ", {"LIBRETRANSLATE_URL": "http://env:5000/"}):
            self.assertEqual(self.config("http://admin:5000").effective_libretranslate_url, "http://env:5000")


class TranslateApi(TestCase):
    def setUp(self):
        self.u = person("jane")
        self.app = job(self.u, description="Hallo Welt")
        self.client.login(username="jane", password=PW)

    def test_off_by_default(self):
        resp = self.client.post(f"/api/v1/jobs/{self.app.pk}/translate")
        self.assertEqual(resp.status_code, 400)

    @mock.patch("requests.post")
    def test_when_configured(self, post):
        SiteConfig.objects.filter(pk=1).update(libretranslate_url="http://localhost:5000")
        post.return_value = mock.Mock(status_code=200, **{"json.return_value": {"translatedText": "Hello world"}})
        resp = self.client.post(f"/api/v1/jobs/{self.app.pk}/translate")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["translated"], "Hello world")

    def test_refuses_an_empty_description(self):
        SiteConfig.objects.filter(pk=1).update(libretranslate_url="http://localhost:5000")
        empty = job(self.u, description="")
        resp = self.client.post(f"/api/v1/jobs/{empty.pk}/translate")
        self.assertEqual(resp.status_code, 400)

    def test_is_owner_scoped(self):
        SiteConfig.objects.filter(pk=1).update(libretranslate_url="http://localhost:5000")
        other = job(person("bob"), description="x")
        resp = self.client.post(f"/api/v1/jobs/{other.pk}/translate")
        self.assertEqual(resp.status_code, 404)
