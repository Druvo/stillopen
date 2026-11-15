"""The public "Get the Android app" page and the app file a server can hand out."""
import tempfile
from pathlib import Path

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from tracker.models import SiteConfig


class AndroidPage(TestCase):
    def setUp(self):
        cache.clear()

    def set_url(self, url):
        config = SiteConfig.load()
        config.android_apk_url = url
        config.save()

    def test_page_is_public_and_shows_this_servers_address(self):
        r = self.client.get(reverse("android_app"), HTTP_HOST="testserver")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "http://testserver")
        self.assertContains(r, "stillopen://connect?server=http://testserver")

    def test_without_a_file_or_address_it_says_it_is_not_available(self):
        with override_settings(STILLOPEN_APK_FILE=Path(tempfile.gettempdir()) / "no-such-app-file.apk"):
            r = self.client.get(reverse("android_app"))
        self.assertContains(r, "not available from this site yet")
        self.assertNotContains(r, "Download for Android")

    def test_the_admin_address_becomes_the_download_button(self):
        self.set_url("https://downloads.example.test/stillopen.apk")
        with override_settings(STILLOPEN_APK_FILE=Path(tempfile.gettempdir()) / "no-such-app-file.apk"):
            r = self.client.get(reverse("android_app"))
        self.assertContains(r, 'href="https://downloads.example.test/stillopen.apk"')

    def test_a_file_on_the_server_is_offered_and_served_as_an_apk(self):
        with tempfile.TemporaryDirectory() as folder:
            apk = Path(folder) / "stillopen.apk"
            apk.write_bytes(b"PK\x03\x04 not a real app")
            with override_settings(STILLOPEN_APK_FILE=apk):
                page = self.client.get(reverse("android_app"))
                self.assertContains(page, reverse("android_apk"))
                r = self.client.get(reverse("android_apk"))
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r["Content-Type"], "application/vnd.android.package-archive")
                self.assertIn("attachment", r["Content-Disposition"])
                self.assertEqual(b"".join(r.streaming_content), b"PK\x03\x04 not a real app")

    def test_no_file_means_404_not_an_error(self):
        with override_settings(STILLOPEN_APK_FILE=Path(tempfile.gettempdir()) / "no-such-app-file.apk"):
            self.assertEqual(self.client.get(reverse("android_apk")).status_code, 404)

    def test_the_page_loads_nothing_from_another_site(self):
        self.set_url("https://downloads.example.test/stillopen.apk")
        html = self.client.get(reverse("android_app")).content.decode()
        for tag in ("<script", "<link", "<img"):
            for part in html.split(tag)[1:]:
                head = part.split(">")[0]
                self.assertNotIn("downloads.example.test", head)
