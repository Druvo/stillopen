"""The Hacker News "Who is hiring?" connector: realistic fake Algolia answers, hostile comment text, the apply address, the shared
Posting dedupe and the rules (site-wide, off by default, never public). No real network."""
from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone

from tracker.models import Application, JobSource, Posting, Status, UserProfile
from tracker.seed_sources import DEFAULT_SOURCES, PUBLIC_OK_CONNECTORS
from tracker.services import scan
from tracker.services.netguard import FetchError

User = get_user_model()
PW = "correct-horse-battery-staple"


def now_i(days_ago=0):
    return int((timezone.now() - timedelta(days=days_ago)).timestamp())


def comment(cid, text, days_ago=1):
    return {"id": cid, "text": text, "created_at_i": now_i(days_ago), "author": "someone", "type": "comment", "children": []}


GOOD = (
    "Launchpad Labs (https://launchpad.example) | Founding Backend Engineer, Data Engineer | Berlin, Germany | REMOTE (EU) | Full-time | $120k-$150k"
    "<p>We build payment rails in Python and Django. Send your CV to <a href=\"mailto:jobs@launchpad.example\">jobs@launchpad.example</a> "
    "or see <a href=\"https://launchpad.example/careers\" rel=\"nofollow\">https://launchpad.example/careers...</a></p>"
)
LINK_ONLY = (
    "Tidewater | Senior Backend Engineer | Remote (US only)<p>Python, Postgres. Apply at "
    "<a href=\"https://boards.greenhouse.io/tidewater/jobs/1\" rel=\"nofollow\">https://boards.greenhouse.io/tidewater/jo...</a>"
)
NO_ROLE = "Mystery Co | Somewhere | Series B | 40 people<p>We are hiring. Details soon.</p>"
EVIL = (
    "<script>alert(1)</script>Evil&lt;b&gt;Corp | Backend Engineer&lt;script&gt;alert(2)&lt;/script&gt; | Remote"
    "<p><script>steal()</script><img src=x onerror=alert(3)>write to jobs [at] evil.example<p>" + "A" * 50000
)
CHATTER = "Thanks for the thread, I will email you."


def threads_payload():
    return {"hits": [
        {"objectID": "5001", "title": "Ask HN: Who is hiring? (This month)", "created_at_i": now_i(2)},
        {"objectID": "5002", "title": "Ask HN: Who wants to be hired? (This month)", "created_at_i": now_i(2)},
        {"objectID": "4001", "title": "Ask HN: Who is hiring? (Last month)", "created_at_i": now_i(33)},
        {"objectID": "3001", "title": "Ask HN: Who is hiring? (Old)", "created_at_i": now_i(400)},
    ]}


def item_payload(story_id):
    if story_id == "5001":
        children = [
            comment(11, GOOD), comment(12, LINK_ONLY), comment(13, NO_ROLE), comment(14, EVIL), comment(15, CHATTER),
            comment(16, GOOD.replace("Founding", "Founding ")),  # the same company and role again: dropped as a duplicate
            comment(17, "Stale Co | Backend Engineer | Remote", days_ago=200),  # too old: dropped
            {"id": 18, "text": None, "created_at_i": now_i(1), "children": []},  # deleted comment
        ]
    else:
        children = [comment(21, "Lastmonth Inc | Platform Engineer | Remote<p>Email hr@lastmonth.example</p>", days_ago=30)]
    return {"id": int(story_id), "children": children}


def fake_get(url, timeout=30, headers=None):
    r = mock.Mock(status_code=200)
    r.json.return_value = threads_payload() if "search_by_date" in url else item_payload(url.rsplit("/", 1)[1])
    r.content = b"{}"
    return r


class Parsing(TestCase):
    def test_header_company_role_place_and_apply_email(self):
        p = scan.parse_hn_comment(GOOD)
        self.assertEqual(p["company"], "Launchpad Labs")
        self.assertEqual(p["title"], "Founding Backend Engineer, Data Engineer")
        self.assertIn("Berlin, Germany", p["location"])
        self.assertIn("REMOTE (EU)", p["location"])
        self.assertEqual(p["apply"], "jobs@launchpad.example")
        self.assertNotIn("Full-time", p["location"])  # not a place
        self.assertNotIn("$120k", p["title"] + p["location"])

    def test_apply_link_read_from_the_href_not_the_cut_off_text(self):
        p = scan.parse_hn_comment(LINK_ONLY)
        self.assertEqual(p["apply"], "https://boards.greenhouse.io/tidewater/jobs/1")
        self.assertEqual(p["location"], "Remote (US only)")

    def test_unknown_stays_blank_never_guessed(self):
        p = scan.parse_hn_comment(NO_ROLE)
        self.assertEqual(p["title"], "Open role (see the post)")
        self.assertEqual(p["apply"], "")
        self.assertNotIn("40 people", p["location"])
        self.assertIsNone(scan.parse_hn_comment(CHATTER))
        self.assertIsNone(scan.parse_hn_comment(""))

    def test_hostile_text_becomes_plain_bounded_text(self):
        p = scan.parse_hn_comment(EVIL)
        blob = " ".join(str(v) for v in p.values())
        for bad in ("<script", "<img", "onerror", "</", "alert(1)>"):
            self.assertNotIn(bad, blob)
        self.assertLessEqual(len(p["description"]), scan.HN_TEXT_CHARS)
        self.assertTrue(all(len(line) <= scan.HN_LINE_CHARS for line in p["description"].split("\n")))
        self.assertEqual(p["apply"], "")  # an obfuscated address is not decoded

    def test_clean_apply_address_accepts_only_email_or_web_links(self):
        for good in ("jobs@x.example", "https://x.example/apply", "http://x.example"):
            self.assertEqual(scan.clean_apply_address(good), good)
        for bad in ("javascript:alert(1)", "mailto:a@b.co", "a b@c.de", "https://x.example/a b", "https://x.example/\"onclick", "", "ftp://x.example/a", "https://" + "a" * 300 + ".com"):
            self.assertEqual(scan.clean_apply_address(bad), "", bad)


class Fetching(TestCase):
    @mock.patch("tracker.services.scan.safe_get", side_effect=fake_get)
    def test_current_and_previous_month_only_deduped(self, get):
        out = scan.fetch_hnhiring("all")
        urls = [p["url"] for p in out]
        self.assertIn("https://news.ycombinator.com/item?id=11", urls)
        self.assertIn("https://news.ycombinator.com/item?id=21", urls)  # last month's thread
        self.assertNotIn("https://news.ycombinator.com/item?id=16", urls)  # duplicate role
        self.assertNotIn("https://news.ycombinator.com/item?id=17", urls)  # too old
        self.assertNotIn("https://news.ycombinator.com/item?id=15", urls)  # chatter
        requested = " ".join(c.args[0] for c in get.call_args_list)
        self.assertNotIn("3001", requested)  # an old thread is never read
        self.assertNotIn("5002", requested)  # "Who wants to be hired?" is not a job thread
        self.assertTrue(all(p["url"].startswith("https://news.ycombinator.com/item?id=") for p in out))

    @mock.patch("tracker.services.scan.HN_MAX_POSTINGS", 2)
    @mock.patch("tracker.services.scan.safe_get", side_effect=fake_get)
    def test_count_is_capped(self, get):
        self.assertEqual(len(scan.fetch_hnhiring("all")), 2)

    @mock.patch("tracker.services.scan.safe_get")
    def test_oversized_answer_is_refused(self, get):
        r = mock.Mock(status_code=200)
        r.content = b"x" * (scan.HN_MAX_BYTES + 1)
        get.return_value = r
        with self.assertRaises(FetchError):
            scan.fetch_hnhiring("all")

    @mock.patch("tracker.services.scan.safe_get")
    def test_a_failing_host_is_a_plain_error(self, get):
        get.return_value = mock.Mock(status_code=503)
        with self.assertRaises(FetchError):
            scan.fetch_hnhiring("all")


class InTheApp(TestCase):
    def setUp(self):
        cache.clear()
        self.u = User.objects.create_user("hana", email="hana@example.com", password=PW)
        UserProfile.objects.filter(user=self.u).update(target_roles="Backend Engineer", profile_cv="Python Django backend engineer.", onboarding_done=True)
        self.src = JobSource.objects.create(name="Startups: Hacker News", connector="hnhiring", board_token="all")

    def test_rules_off_by_default_and_never_public(self):
        self.assertNotIn("hnhiring", PUBLIC_OK_CONNECTORS)
        self.assertFalse(any(c == "hnhiring" for _, c, *_ in DEFAULT_SOURCES))
        self.assertFalse(self.src.show_publicly)
        self.assertIsNone(self.src.owner)
        self.assertNotIn("hnhiring", JobSource.OWN_CONNECTORS)

    def test_a_search_adds_matching_posts_and_keeps_the_apply_address(self):
        with mock.patch("tracker.services.scan.safe_get", side_effect=fake_get):
            scan.start_run(self.u, background=False)
        app = Application.objects.get(owner=self.u, company="Launchpad Labs")
        self.assertEqual(app.url, "https://news.ycombinator.com/item?id=11")
        self.assertEqual(app.posting.apply_address, "jobs@launchpad.example")
        self.assertNotIn("<script", app.description)
        self.client.login(username="hana", password=PW)
        job = next(j for j in self.client.get("/api/v1/dashboard").json()["jobs"] if j["company"] == "Launchpad Labs")
        self.assertEqual(job["apply_address"], "jobs@launchpad.example")

    def test_the_same_post_seen_twice_is_one_shared_posting(self):
        with mock.patch("tracker.services.scan.safe_get", side_effect=fake_get):
            scan.start_run(self.u, background=False)
            cache.clear()
            scan.start_run(self.u, background=False)
        self.assertEqual(Posting.objects.filter(source=self.src, url="https://news.ycombinator.com/item?id=11").count(), 1)
        self.assertEqual(Application.objects.filter(owner=self.u, company="Launchpad Labs").count(), 1)

    def test_all_postings_lists_the_address_and_never_a_bad_one(self):
        good = Posting.objects.create(source=self.src, url="https://news.ycombinator.com/item?id=31", title="Backend Engineer", company="A", title_key="a be", apply_address="jobs@a.example")
        evil = Posting.objects.create(source=self.src, url="https://news.ycombinator.com/item?id=32", title="Backend Engineer", company="B", title_key="b be", apply_address="javascript:alert(1)")
        self.client.login(username="hana", password=PW)
        rows = {r["id"]: r for r in self.client.get("/api/v1/postings").json()["postings"]}
        self.assertEqual(rows[good.pk]["apply_address"], "jobs@a.example")
        self.assertEqual(rows[evil.pk]["apply_address"], "")

    def test_adding_a_posting_by_hand_carries_the_address_to_the_job(self):
        post = Posting.objects.create(source=self.src, url="https://news.ycombinator.com/item?id=41", title="Backend Engineer", company="C", title_key="c be", apply_address="https://c.example/apply")
        self.client.login(username="hana", password=PW)
        job_id = self.client.post(f"/api/v1/postings/{post.pk}/add").json()["id"]
        jobs = self.client.get("/api/v1/dashboard").json()["jobs"]
        self.assertEqual(next(j for j in jobs if j["id"] == job_id)["apply_address"], "https://c.example/apply")

    def test_another_person_never_sees_my_job_or_its_address(self):
        post = Posting.objects.create(source=self.src, url="https://news.ycombinator.com/item?id=51", title="Backend Engineer", company="D", title_key="d be", apply_address="jobs@d.example")
        Application.objects.create(owner=self.u, company="D", role="Backend Engineer", url=post.url, posting=post, status=Status.objects.first())
        User.objects.create_user("omar", email="omar@example.com", password=PW)
        UserProfile.objects.filter(user__username="omar").update(onboarding_done=True)
        self.client.login(username="omar", password=PW)
        self.assertEqual([j for j in self.client.get("/api/v1/dashboard").json()["jobs"] if j["company"] == "D"], [])
