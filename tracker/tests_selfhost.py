"""No page may load a stylesheet, script, font or image from a third-party host. Front-end files ship with the app."""
import hashlib
import re
import tempfile
from pathlib import Path

from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from tracker.models import Application, SiteConfig, Status

User = get_user_model()
VENDOR = Path(__file__).resolve().parent.parent / "static" / "vendor" / "tabler"
EXPECTED = {
    "tabler.min.css": "9efa2db2d4f50146d68f03d0d857de52a1d42ca0f6d153c63429b9c948a943ea",
    "tabler.min.js": "5f3b9d83904b49cceba984aaa4f6babc67ddbda8de09045d6a5de5a65854a65d",
}
# anything that makes the browser fetch from another host without a click: stylesheets, scripts, images, fonts, imports
# (a rel="canonical" link only names the page's own address and fetches nothing, so it is not counted)
EXTERNAL_ASSET = re.compile(
    r"""(<link(?![^>]+rel=["']canonical["'])[^>]+href=["'](?:https?:)?//|<script[^>]+src=["'](?:https?:)?//|<img[^>]+src=["'](?:https?:)?//|"""
    r"""@import\s+(?:url\()?["']?(?:https?:)?//|url\(["']?(?:https?:)?//|<iframe[^>]+src=["'](?:https?:)?//)""",
    re.I,
)


class VendoredFiles(TestCase):
    def test_files_are_found_by_the_static_finders(self):
        for name in EXPECTED:
            self.assertIsNotNone(finders.find(f"vendor/tabler/{name}"), name)

    def test_files_are_unmodified_and_keep_their_licence_banner(self):
        for name, digest in EXPECTED.items():
            data = (VENDOR / name).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), digest, f"{name} no longer matches the verified Tabler 1.7.0 file")
            head = data[:500].decode("utf-8", errors="replace")
            self.assertIn("Licensed under MIT", head)
            self.assertIn("Tabler v1.7.0", head)
        self.assertTrue((VENDOR / "NOTICE.md").exists())

    def test_the_stylesheet_itself_loads_nothing_from_elsewhere(self):
        css = (VENDOR / "tabler.min.css").read_text(encoding="utf-8")
        self.assertIsNone(EXTERNAL_ASSET.search(css))

    def test_whitenoise_serves_them_after_collectstatic(self):
        with tempfile.TemporaryDirectory() as root, override_settings(STATIC_ROOT=root):
            call_command("collectstatic", interactive=False, verbosity=0)
            from django.test import Client

            client = Client()
            for name in EXPECTED:
                response = client.get(f"/static/vendor/tabler/{name}")
                self.assertEqual(response.status_code, 200, name)
                self.assertGreater(len(b"".join(response.streaming_content) if response.streaming else response.content), 100_000)


class NoThirdPartyAssets(TestCase):
    def setUp(self):
        SiteConfig.objects.filter(pk=1).update(signup_mode="open")
        self.user = User.objects.create_user("pat", email="pat@example.com", password="correct-horse-battery-staple")
        Application.objects.create(owner=self.user, company="Acme", role="Dev", status=Status.objects.get(name="Evaluated"),
                                   url="https://jobs.example.com/acme", description="Hybrid in Kuala Lumpur.")

    def assert_self_hosted(self, url):
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200, url)
        html = page.content.decode()
        self.assertIsNone(EXTERNAL_ASSET.search(html), f"{url} loads something from a third-party host")
        return html

    def test_public_pages(self):
        for name in ("landing", "openings", "privacy", "terms", "account_login", "account_signup"):
            html = self.assert_self_hosted(reverse(name))
            self.assertIn("/static/vendor/tabler/tabler.min.css", html, name)
            self.assertIn("/static/css/stillopen.css", html, name)

    def test_signed_in_pages(self):
        self.client.force_login(self.user)
        app = Application.objects.get(owner=self.user)
        urls = [reverse("dashboard"), reverse("profile"), reverse("profile_ai"), reverse("knowledge"), reverse("add_job"),
                reverse("cv_list"), reverse("apply_page", args=[app.pk]), reverse("job_edit", args=[app.pk]),
                reverse("account_email"), reverse("account_change_password")]
        for url in urls:
            html = self.assert_self_hosted(url)
        self.assertIn("/static/vendor/tabler/tabler.min.js", self.client.get(reverse("dashboard")).content.decode())

    def test_job_links_are_still_ordinary_links(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse("dashboard")).content.decode()
        self.assertIn('href="https://jobs.example.com/acme"', html)  # navigation to the posting is fine; only assets are banned

    def test_admin_pages_do_not_use_a_font_cdn(self):
        admin = User.objects.create_superuser("root", password="correct-horse-battery-staple")
        for url in ("/admin/login/", ):
            html = self.client.get(url).content.decode()
            self.assertNotIn("fonts.googleapis.com", html, url)
            self.assertIsNone(EXTERNAL_ASSET.search(html), url)
        self.client.force_login(admin)
        for url in ("/admin/", reverse("admin:tracker_siteconfig_changelist")):
            response = self.client.get(url, follow=True)
            html = response.content.decode()
            self.assertNotIn("fonts.googleapis.com", html, url)
            self.assertIsNone(EXTERNAL_ASSET.search(html), url)


class AdminLooksAndSelfHosts(TestCase):
    """The admin (Unfold) keeps its fonts, icons and scripts on this server and its main pages render."""

    def test_admin_pages_render_and_load_nothing_from_third_party_hosts(self):
        from django.contrib.auth import get_user_model
        from django.urls import reverse

        self.assertEqual(self.client.get(reverse("admin:login")).status_code, 200)
        self.assertIsNone(EXTERNAL_ASSET.search(self.client.get(reverse("admin:login")).content.decode()))
        boss = get_user_model().objects.create_superuser("themeboss", "boss@example.com", "x" * 20)
        self.client.force_login(boss)
        for name in ("admin:index", "admin:tracker_siteconfig_change", "admin:tracker_application_changelist", "admin:auth_user_changelist",
                     "admin:tracker_knowledgesource_changelist", "admin:tracker_jobsource_changelist"):
            args = [1] if name.endswith("_change") else []
            page = self.client.get(reverse(name, args=args))
            self.assertEqual(page.status_code, 200, name)
            html = page.content.decode()
            self.assertIsNone(EXTERNAL_ASSET.search(html), f"{name} loads something from a third-party host")
            self.assertNotIn("fonts.googleapis.com", html, name)
