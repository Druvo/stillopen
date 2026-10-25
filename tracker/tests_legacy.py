"""The old classic-page addresses still work: each one sends the browser to the same screen in the app."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from tracker.legacy import REDIRECTS

User = get_user_model()

OLD_TO_NEW = {
    "/dashboard/": "/app/",
    "/welcome/": "/app/welcome",
    "/jobs/add/": "/app/jobs/add",
    "/postings/": "/app/postings",
    "/jobs/7/edit/": "/app/jobs/7/edit",
    "/jobs/7/apply/": "/app/jobs/7/apply",
    "/profile/": "/app/profile",
    "/profile/ai/": "/app/profile/ai",
    "/profile/assistant/": "/app/profile/assistant",
    "/sources/": "/app/sources",
    "/knowledge/": "/app/knowledge",
    "/cv/": "/app/cv",
    "/cv/7/": "/app/cv/7",
    "/cv/7/diff/": "/app/cv/7/diff",
    "/cover/7/": "/app/cover/7",
    "/interviews/": "/app/interviews",
    "/contacts/": "/app/contacts",
    "/offers/": "/app/offers",
    "/insights/": "/app/insights",
    "/prep/": "/app/prep",
    "/prep/7/": "/app/prep/7",
    "/prep/7/today/": "/app/prep/7/today",
}


class LegacyAddresses(TestCase):
    def test_the_table_here_covers_every_redirect_the_app_defines(self):
        self.assertEqual(len(OLD_TO_NEW), len(REDIRECTS))

    def test_every_old_address_redirects_to_its_screen_in_the_app(self):
        user = User.objects.create_user("alice", password="x" * 20)
        self.client.force_login(user)
        for old, new in OLD_TO_NEW.items():
            r = self.client.get(old)
            self.assertEqual(r.status_code, 302, old)
            self.assertEqual(r["Location"], new, old)

    def test_the_query_string_is_kept(self):
        r = self.client.get("/interviews/?job=4")
        self.assertEqual(r["Location"], "/app/interviews?job=4")
        r = self.client.get("/profile/?welcome=1")
        self.assertEqual(r["Location"], "/app/profile?welcome=1")

    def test_a_signed_out_visitor_ends_at_sign_in_and_is_sent_on_afterwards(self):
        for old, new in OLD_TO_NEW.items():
            first = self.client.get(old)
            self.assertEqual(first["Location"], new, old)
            second = self.client.get(first["Location"])
            self.assertEqual(second.status_code, 302, old)
            self.assertIn("/accounts/login/", second["Location"], old)
            self.assertIn("next=", second["Location"], old)

    def test_a_post_to_an_old_address_is_refused_and_never_an_error(self):
        user = User.objects.create_user("bob", password="x" * 20)
        self.client.force_login(user)
        for old in OLD_TO_NEW:
            self.assertEqual(self.client.post(old, {"x": "1"}).status_code, 405, old)

    def test_removed_actions_that_never_had_a_page_are_simply_gone(self):
        user = User.objects.create_user("carol", password="x" * 20)
        self.client.force_login(user)
        for old in ("/jobs/7/applied/", "/cv/7/approve/", "/api/application/7/status/", "/api/import/", "/profile/delete/", "/prep/7/answer/"):
            self.assertEqual(self.client.post(old).status_code, 404, old)
            self.assertEqual(self.client.get(old).status_code, 404, old)

    def test_the_files_the_app_links_to_are_still_here(self):
        from django.urls import reverse

        for name, args in (("cv_download", [1, "md"]), ("cv_print", [1]), ("cover_download", [1, "txt"]), ("document_file", [1]), ("export_data", [])):
            reverse(name, args=args)
