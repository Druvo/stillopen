"""The public side: job board, landing page, charts, refresh, robots and sitemap, and the rules that keep it lawful and safe."""
import re
from datetime import timedelta
from itertools import count
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tracker import landing_content, seed
from tracker.models import JobSource, Posting, SiteConfig
from tracker.seed_sources import PUBLIC_OK_CONNECTORS
from tracker.services import public, scan
from tracker.templatetags import charts

User = get_user_model()
_n = count(1)


def source(connector="greenhouse", name="Acme", show_publicly=True, **kw):
    n = next(_n)
    return JobSource.objects.create(name=name, connector=connector, board_token=f"tok{n}", show_publicly=show_publicly, **kw)


def posting(src, title="Backend Engineer", company="Acme", location="Remote", country="", remote=False, excerpt="", seen_days_ago=0, first_days_ago=0, url=None, **terms):
    n = next(_n)
    p = Posting.objects.create(
        source=src, url=url or f"https://jobs.test/{n}", title=title, company=company, title_key=f"{company}::{title}::{n}".lower(),
        location=location, country=country, remote=remote, excerpt=excerpt, **terms,
    )
    now = timezone.now()
    Posting.objects.filter(pk=p.pk).update(last_seen_at=now - timedelta(days=seen_days_ago), first_seen_at=now - timedelta(days=first_days_ago))
    p.refresh_from_db()
    return p


class PublicTestCase(TestCase):
    def setUp(self):
        cache.clear()


class WhatTheBoardMayShow(PublicTestCase):
    def test_only_public_enabled_site_wide_sources_with_recent_postings(self):
        ok = posting(source(), title="Visible")
        posting(source(show_publicly=False), title="HiddenBySwitch")
        posting(source(enabled=False), title="HiddenDisabled")
        posting(source(owner=User.objects.create_user("p", password="x" * 12)), title="HiddenPrivateBoard")
        posting(source(), title="HiddenStale", seen_days_ago=10)
        self.assertEqual(list(public.public_postings()), [ok])

    def test_a_private_board_stays_private_even_if_someone_ticks_public(self):
        owner = User.objects.create_user("owner", password="x" * 12)
        posting(source(owner=owner, show_publicly=True), title="Mine")
        self.assertEqual(public.public_postings().count(), 0)

    def test_default_flags_follow_the_sources_own_terms(self):
        seed.ensure_default_sources(JobSource)
        for connector in ("remotive", "weworkremotely", "workingnomads", "themuse", "jooble"):
            self.assertFalse(JobSource.objects.filter(connector=connector, show_publicly=True).exists(), connector)
        for connector in ("remoteok", "himalayas", "jobicy", "arbeitnow", "greenhouse", "lever", "ashby"):
            self.assertTrue(JobSource.objects.filter(connector=connector, show_publicly=True).exists(), connector)
        self.assertNotIn("remotive", PUBLIC_OK_CONNECTORS)

    def test_a_new_source_is_hidden_until_an_admin_opts_it_in(self):
        self.assertFalse(JobSource.objects.create(name="X", connector="greenhouse", board_token="x").show_publicly)

    def test_credit_names_the_source_and_links_to_the_unchanged_original(self):
        r = posting(source("remoteok", "Remote OK"), url="https://remoteok.com/remote-jobs/123")
        credit = public.credit_for(r)
        self.assertEqual((credit["label"], credit["url"], credit["kind"]), ("Remote OK", "https://remoteok.com/remote-jobs/123", "source"))
        e = posting(source("lever"), company="Grab", url="https://jobs.lever.co/grab/1")
        self.assertEqual((public.credit_for(e)["label"], public.credit_for(e)["kind"]), ("Grab careers", "employer"))

    def test_excerpt_is_short_and_cut_at_a_word(self):
        long_text = ("word " * 300).strip()
        out = scan.excerpt_of(long_text)
        self.assertLessEqual(len(out), scan.EXCERPT_CHARS + 3)
        self.assertTrue(out.endswith("..."))
        self.assertNotIn("  ", scan.excerpt_of("a   b\n\n c"))
        self.assertEqual(scan.excerpt_of("short"), "short")
        self.assertEqual(scan.excerpt_of(""), "")


class SightingsFeedTheBoard(PublicTestCase):
    def test_recording_sightings_stores_country_remote_and_excerpt(self):
        src = source()
        scan.record_sightings(src, [
            {"title": "Backend Engineer", "url": "https://x.test/1", "location": "Kuala Lumpur, Malaysia", "company": "Grab", "description": "Build things. " * 80},
            {"title": "Remote Go Developer", "url": "https://x.test/2", "location": "Anywhere", "company": "Acme", "description": ""},
            {"title": "Multi", "url": "https://x.test/3", "location": "Hong Kong; Singapore", "company": "Acme", "description": "x"},
        ])
        a, b, c = (Posting.objects.get(url=f"https://x.test/{i}") for i in (1, 2, 3))
        self.assertEqual((a.country, a.remote), ("MY", False))
        self.assertTrue(a.excerpt.startswith("Build things.") and len(a.excerpt) <= scan.EXCERPT_CHARS + 3)
        self.assertEqual((b.country, b.remote), ("", True))
        self.assertEqual(c.country, "")  # two countries: not one

    def test_a_second_sighting_refreshes_what_the_board_shows(self):
        src = source()
        scan.record_sightings(src, [{"title": "Old", "url": "https://x.test/1", "location": "Dhaka", "company": "Acme", "description": ""}])
        Posting.objects.update(last_seen_at=timezone.now() - timedelta(days=9))
        scan.record_sightings(src, [{"title": "New title", "url": "https://x.test/1", "location": "Dhaka", "company": "Acme", "description": "fresh text"}])
        p = Posting.objects.get()
        self.assertEqual((p.title, p.excerpt, p.country), ("New title", "fresh text", "BD"))
        self.assertGreater(p.last_seen_at, timezone.now() - timedelta(minutes=1))
        self.assertEqual(public.public_postings().count(), 1)


@override_settings(STILLOPEN_PUBLIC_PAGE_SIZE=3)
class JobBoard(PublicTestCase):
    def setUp(self):
        super().setUp()
        self.src = source("greenhouse", "Acme")
        self.rows = [posting(self.src, title=f"Role {i}", company=f"Co{i}", first_days_ago=i, country="MY" if i % 2 else "BD", remote=i % 3 == 0, excerpt=f"About role {i}") for i in range(7)]

    def test_anyone_can_browse_without_signing_in_and_the_newest_come_first(self):
        r = self.client.get(reverse("openings"))
        self.assertEqual(r.status_code, 200)
        self.assertEqual([x["p"].title for x in r.context["rows"]], ["Role 0", "Role 1", "Role 2"])
        self.assertContains(r, "Create a free account")

    def test_pagination_covers_everything(self):
        titles = []
        for page in (1, 2, 3):
            titles += [x["p"].title for x in self.client.get(reverse("openings"), {"page": page}).context["rows"]]
        self.assertEqual(sorted(titles), sorted(p.title for p in self.rows))
        self.assertContains(self.client.get(reverse("openings")), "Page 1 of 3")
        self.assertContains(self.client.get(reverse("openings")), 'rel="next"')

    def test_search_country_and_remote_filters_combine(self):
        get = lambda **q: {x["p"].title for x in self.client.get(reverse("openings"), q).context["rows"]}
        self.assertEqual(get(q="role 4"), {"Role 4"})
        self.assertEqual(get(q="co1"), {"Role 1"})
        self.assertEqual(get(country="BD", page=1) | get(country="BD", page=2), {"Role 0", "Role 2", "Role 4", "Role 6"})
        self.assertEqual(get(remote="1", page=1) | get(remote="1", page=2), {"Role 0", "Role 3", "Role 6"})
        self.assertEqual(get(country="BD", remote="1"), {"Role 0", "Role 6"})
        self.assertEqual(self.client.get(reverse("openings"), {"q": "zzz"}).context["total"], 0)

    def test_every_word_in_the_search_must_match(self):
        self.assertEqual(self.client.get(reverse("openings"), {"q": "role co3"}).context["total"], 1)
        self.assertEqual(self.client.get(reverse("openings"), {"q": "role nonsense"}).context["total"], 0)

    def test_a_junk_country_is_ignored_not_an_error(self):
        for bad in ("<script>", "XXX", "1", "../"):
            self.assertEqual(self.client.get(reverse("openings"), {"country": bad}).status_code, 200)

    def test_filtered_and_deep_pages_are_noindex_the_plain_board_is_indexable(self):
        self.assertContains(self.client.get(reverse("openings")), 'content="index,follow"')
        self.assertContains(self.client.get(reverse("openings"), {"q": "role"}), 'content="noindex,follow"')
        self.assertContains(self.client.get(reverse("openings"), {"page": 2}), 'content="noindex,follow"')

    def test_titles_and_companies_are_escaped(self):
        posting(self.src, title='<script>alert(1)</script>', company='"><img src=x>', first_days_ago=0)
        page = self.client.get(reverse("openings")).content.decode()
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertNotIn('"><img src=x>', page)

    def test_each_card_links_to_its_page_and_credits_its_source(self):
        page = self.client.get(reverse("openings")).content.decode()
        self.assertIn(reverse("opening_detail", args=[self.rows[0].pk, public.slug_for(self.rows[0])]), page)
        self.assertIn("via Co0 careers", page)  # an employer's own board credits the employer

    def test_the_board_can_be_switched_off(self):
        SiteConfig.objects.filter(pk=1).update(public_board_enabled=False)
        self.assertEqual(self.client.get(reverse("openings")).status_code, 404)
        landing = self.client.get(reverse("landing")).content.decode()
        self.assertNotIn("Browse jobs", landing)

    def test_empty_board_says_what_to_do_next(self):
        Posting.objects.all().delete()
        self.assertContains(self.client.get(reverse("openings")), "The board is filling up")


class OpeningPage(PublicTestCase):
    def setUp(self):
        super().setUp()
        self.src = source("remoteok", "Remote OK")
        self.p = posting(self.src, title="Senior Go Engineer", company="Initech", location="Remote", remote=True, excerpt="You will build services.", url="https://remoteok.com/remote-jobs/42")

    def url(self, p=None, slug=None):
        p = p or self.p
        return reverse("opening_detail", args=[p.pk, slug or public.slug_for(p)])

    def test_shows_the_excerpt_a_credit_and_the_unchanged_apply_link(self):
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 200)
        html = r.content.decode()
        self.assertIn("You will build services.", html)
        self.assertIn('href="https://remoteok.com/remote-jobs/42"', html)
        self.assertIn("apply on Remote OK", html)
        link = re.search(r'<a class="btn btn-primary btn-lg" href="https://remoteok.com/remote-jobs/42"[^>]*>', html).group(0)
        self.assertIn("noopener", link)
        self.assertNotIn("nofollow", link)  # Remote OK asks for a followed link back

    def test_never_emits_job_posting_markup(self):
        html = self.client.get(self.url()).content.decode()
        self.assertNotIn("JobPosting", html)
        self.assertNotIn("application/ld+json", html)

    def test_the_posting_text_is_never_shown_in_full(self):
        Posting.objects.filter(pk=self.p.pk).update(excerpt="x" * 400)
        self.assertLessEqual(len(self.client.get(self.url()).context["p"].excerpt), 400)

    def test_wrong_slug_redirects_permanently_to_the_right_one(self):
        r = self.client.get(self.url(slug="something-else"))
        self.assertEqual(r.status_code, 301)
        self.assertTrue(r["Location"].endswith(self.url()))
        self.assertEqual(self.client.get(reverse("opening_detail_bare", args=[self.p.pk])).status_code, 301)

    def test_canonical_is_its_own_address(self):
        self.assertContains(self.client.get(self.url()), f'rel="canonical" href="http://testserver{self.url()}"')

    def test_not_indexable_unless_the_admin_allows_it(self):
        self.assertContains(self.client.get(self.url()), 'content="noindex,follow"')
        SiteConfig.objects.filter(pk=1).update(public_details_indexable=True)
        self.assertContains(self.client.get(self.url()), 'content="index,follow"')

    def test_a_posting_no_longer_seen_is_gone_410_not_left_up(self):
        Posting.objects.filter(pk=self.p.pk).update(last_seen_at=timezone.now() - timedelta(days=30))
        r = self.client.get(self.url())
        self.assertEqual(r.status_code, 410)
        self.assertContains(r, "no longer listed", status_code=410)
        self.assertContains(r, 'content="noindex,follow"', status_code=410)

    def test_hidden_private_and_unknown_openings_are_404(self):
        hidden = posting(source(show_publicly=False), title="Nope")
        private = posting(source(owner=User.objects.create_user("po", password="x" * 12)), title="Private")
        for p in (hidden, private):
            self.assertEqual(self.client.get(self.url(p, "x")).status_code, 404)
        self.assertEqual(self.client.get(reverse("opening_detail", args=[99999999, "x"])).status_code, 404)

    def test_other_openings_at_the_company_and_country_are_offered(self):
        same = posting(source("greenhouse", "G"), title="Platform Engineer", company="Initech", country="MY", location="Kuala Lumpur")
        near = posting(source("greenhouse", "H"), title="Data Engineer", company="Hooli", country="MY", location="Penang")
        Posting.objects.filter(pk=self.p.pk).update(country="MY")
        html = self.client.get(self.url()).content.decode()
        self.assertIn("More at Initech", html)
        self.assertIn("Platform Engineer", html)
        self.assertIn("More jobs in Malaysia", html)
        self.assertIn("Data Engineer", html)

    def test_signup_cta_only_when_registration_is_open(self):
        self.assertNotContains(self.client.get(self.url()), "Check my fit, free")
        SiteConfig.objects.filter(pk=1).update(signup_mode="open")
        self.assertContains(self.client.get(self.url()), "Check my fit, free")

    def test_an_employers_own_posting_credits_the_employer(self):
        e = posting(source("greenhouse", "G"), company="Grab", url="https://boards.greenhouse.io/grab/jobs/1")
        html = self.client.get(self.url(e)).content.decode()
        self.assertIn("Posted by Grab on its own hiring page", html)
        self.assertNotIn("nofollow", html)


class LandingPage(PublicTestCase):
    def setUp(self):
        super().setUp()
        self.remoteok = source("remoteok", "Remote OK")
        self.boards = source("greenhouse", "Boards")
        for i in range(6):
            posting(self.boards, title=f"Engineer {i}", company=f"Co{i}", country="MY" if i < 4 else "BD", location="Kuala Lumpur" if i < 4 else "Dhaka", first_days_ago=i)
        posting(self.remoteok, title="Remote Dev", company="RemoCo", remote=True, location="Remote", first_days_ago=1)
        self.hidden = posting(source("remotive", "Remotive", show_publicly=False), title="ShouldNeverShow", company="HiddenCo")

    def page(self):
        return self.client.get(reverse("landing")).content.decode()

    def test_leads_with_the_all_in_one_message(self):
        html = self.page()
        self.assertIn("Stop visiting job sites one by one", html)
        self.assertIn("one by one", html)
        self.assertIn("Find, tailor and apply", html)
        self.assertIn("one place", html)

    def test_shows_real_live_numbers(self):
        html = self.page()
        stats = public.stats()
        self.assertEqual(stats["total"], 7)
        self.assertIn(">7</div><div class=\"so-cap\">open jobs right now", html)
        self.assertIn("Browse 7 open jobs", html)
        self.assertEqual(stats["companies"], 7)
        self.assertEqual(stats["countries"], 2)

    def test_has_every_section_a_visitor_needs(self):
        html = self.page()
        for text in ("Your first ten minutes", "How a search narrows the list", "What is open right now", "Everything a job hunt needs", "One tool instead of a pile of tabs",
                     "Private to you, honest about its limits", "Everything you need to know", "Stop opening tabs. Start applying.", "Fresh openings, right now"):
            self.assertIn(text, html)
        self.assertEqual(html.count('class="so-faq"'), len(landing_content.FAQ))

    def test_charts_are_real_accessible_svg_with_the_live_data(self):
        html = self.page()
        self.assertGreaterEqual(html.count('<svg class="so-chart'), 2)
        self.assertIn("Open jobs by country", html)
        self.assertIn("Malaysia", html)
        self.assertRegex(html, r'role="img" aria-labelledby="chart\d+t chart\d+d"')

    def test_latest_jobs_link_to_their_pages(self):
        html = self.page()
        self.assertIn("Engineer 0", html)
        self.assertIn(reverse("opening_detail_bare", args=[Posting.objects.get(title="Engineer 0").pk]), html)

    def test_a_hidden_source_never_appears_anywhere_on_the_page(self):
        html = self.page()
        for text in ("ShouldNeverShow", "HiddenCo", "Remotive"):
            self.assertNotIn(text, html)

    def test_credits_the_sources_that_ask_for_it(self):
        html = self.page()
        self.assertIn('href="https://remoteok.com"', html)
        self.assertIn("Remote OK", html)

    def test_uses_the_admin_text_and_keeps_the_existing_promises(self):
        SiteConfig.objects.filter(pk=1).update(landing_headline="My own headline", landing_github_url="https://github.com/example/stillopen", signup_mode="open")
        html = self.page()
        self.assertIn("My own headline", html)
        self.assertIn("https://github.com/example/stillopen", html)
        self.assertIn("Create a free account", html)
        self.assertNotIn("Open dashboard", html)

    def test_no_third_party_requests_and_a_skip_link(self):
        html = self.page()
        self.assertNotRegex(html, r'(?:src|href)="https?://(?!(?:localhost|testserver|remoteok|himalayas|jobicy|arbeitnow|github))')
        self.assertIn('class="so-skip"', html)
        self.assertIn('<main id="main">', html)

    def test_the_footer_credits_sources_and_offers_a_removal_contact(self):
        SiteConfig.objects.filter(pk=1).update(contact_email="jobs@example.com")
        html = self.page()
        self.assertIn("Job posts belong to the employers and sites that published them", html)
        self.assertIn("mailto:jobs@example.com", html)

    def test_with_no_jobs_yet_it_still_renders_without_numbers(self):
        Posting.objects.all().delete()
        cache.clear()
        html = self.page()
        self.assertEqual(self.client.get(reverse("landing")).status_code, 200)
        self.assertNotIn("open jobs right now", html)
        self.assertIn("Stop visiting job sites one by one", html)

    def test_never_leaks_a_persons_tracked_jobs(self):
        from tracker.models import Application, Status
        Application.objects.create(company="SecretCorp", role="Hidden", status=Status.objects.get(name="Evaluated"))
        self.assertNotIn("SecretCorp", self.page())


class Stats(PublicTestCase):
    def test_a_fresh_import_does_not_pose_as_news(self):
        s = source()
        for i in range(10):
            posting(s, title=f"J{i}", company=f"C{i}")  # all first seen just now
        stats = public.stats()
        self.assertIsNone(stats["new_today"])
        self.assertEqual(stats["by_day"], [])

    def test_new_today_and_days_appear_once_there_is_history(self):
        s = source()
        for i in range(10):
            posting(s, title=f"Old{i}", company=f"C{i}", first_days_ago=5 + i % 3)
        posting(s, title="Today1", company="N1")
        posting(s, title="Today2", company="N2")
        stats = public.stats(refresh=True)
        self.assertEqual(stats["new_today"], 2)
        self.assertEqual(len(stats["by_day"]), 14)
        self.assertEqual(sum(d["n"] for d in stats["by_day"]), 12)

    def test_cached_for_a_while(self):
        s = source()
        posting(s)
        self.assertEqual(public.stats()["total"], 1)
        posting(s, title="Another", company="B")
        self.assertEqual(public.stats()["total"], 1)  # cached
        self.assertEqual(public.stats(refresh=True)["total"], 2)

    def test_country_and_day_rows_for_the_charts(self):
        s = source()
        for i in range(4):
            posting(s, country="MY", location="KL", company=f"A{i}", remote=i == 0)
        posting(s, country="BD", location="Dhaka", company="B")
        rows = landing_content.country_rows(public.stats())
        self.assertEqual(rows[0], ("Malaysia", 4))
        self.assertIn(("Remote (any place)", 1), rows)


class Charts(TestCase):
    def test_horizontal_bars_scale_label_and_escape(self):
        svg = charts.hbar_svg([("<b>Big</b>", 100), ("Small", 10)], "Title <x>", "Desc")
        self.assertIn("&lt;b&gt;Big&lt;/b&gt;", svg)
        self.assertNotIn("<b>Big</b>", svg)
        self.assertIn("Title &lt;x&gt;", svg)
        widths = [int(w) for w in re.findall(r'class="so-bar"[^>]*width="(\d+)"', svg)]
        self.assertGreater(widths[0], widths[1] * 5)
        self.assertIn("<title", svg)
        self.assertIn("<desc", svg)

    def test_numbers_are_readable_and_nothing_breaks_on_empty_or_zero(self):
        self.assertEqual(charts.hbar_svg([], "t"), "")
        self.assertEqual(charts.column_svg([], "t"), "")
        self.assertEqual(charts.donut_svg([], "t"), "")
        self.assertEqual(charts.donut_svg([("a", 0)], "t"), "")
        self.assertIn("12.9k", charts.hbar_svg([("US", 12900)], "t"))
        self.assertIn("1,096", charts.hbar_svg([("UK", 1096)], "t"))
        self.assertIn('width="0"', charts.hbar_svg([("none", 0), ("x", 5)], "t"))

    def test_columns_mark_the_peak_and_label_days(self):
        svg = charts.column_svg([(str(d), d) for d in range(1, 15)], "t")
        self.assertEqual(svg.count('class="so-bar"'), 14)
        self.assertIn(">14<", svg)

    def test_donut_segments_are_stroked_rings_never_filled_and_add_to_a_whole(self):
        svg = charts.donut_svg([("A", 30), ("B", 10)], "t")
        self.assertEqual(svg.count("so-ring "), 2)
        self.assertIn('fill="none"', svg)
        arcs = [float(a) for a in re.findall(r'stroke-dasharray="([\d.]+) ', svg)]
        self.assertAlmostEqual(sum(arcs), 100, places=1)
        self.assertIn(">40<", svg)

    def test_every_chart_gets_its_own_ids_so_screen_readers_are_not_confused(self):
        a, b = charts.hbar_svg([("x", 1)], "t"), charts.hbar_svg([("x", 1)], "t")
        self.assertNotEqual(re.search(r'id="(chart\d+)t"', a).group(1), re.search(r'id="(chart\d+)t"', b).group(1))


class RobotsAndSitemap(PublicTestCase):
    def test_robots_allows_public_pages_blocks_private_ones_and_points_to_the_sitemap(self):
        text = self.client.get(reverse("robots")).content.decode()
        self.assertIn("Allow: /", text)
        for path in ("/dashboard/", "/accounts/", "/admin/", "/api/", "/profile/", "/cv/"):
            self.assertIn(f"Disallow: {path}", text)
        self.assertIn("Sitemap: http://testserver/sitemap.xml", text)

    def test_sitemap_lists_the_public_pages_and_only_adds_openings_when_allowed(self):
        p = posting(source(), title="Listed & <Co>", company="X")
        xml = self.client.get(reverse("sitemap")).content.decode()
        self.assertIn("<loc>http://testserver/</loc>", xml)
        self.assertIn("<loc>http://testserver/openings/</loc>", xml)
        self.assertNotIn(f"/openings/{p.pk}/", xml)
        SiteConfig.objects.filter(pk=1).update(public_details_indexable=True)
        xml = self.client.get(reverse("sitemap")).content.decode()
        self.assertIn(f"/openings/{p.pk}/", xml)
        self.assertIn("<lastmod>", xml)
        self.assertNotIn("<Co>", xml)

    def test_sitemap_leaves_out_hidden_stale_and_private(self):
        SiteConfig.objects.filter(pk=1).update(public_details_indexable=True)
        hidden = posting(source(show_publicly=False))
        stale = posting(source(), seen_days_ago=20)
        xml = self.client.get(reverse("sitemap")).content.decode()
        self.assertNotIn(f"/openings/{hidden.pk}/", xml)
        self.assertNotIn(f"/openings/{stale.pk}/", xml)

    def test_board_off_removes_the_openings_from_the_sitemap(self):
        SiteConfig.objects.filter(pk=1).update(public_board_enabled=False)
        self.assertNotIn("/openings/", self.client.get(reverse("sitemap")).content.decode())


class KeepingItFresh(PublicTestCase):
    def test_refresh_marks_what_is_still_listed_and_leaves_the_rest_to_expire(self):
        src = source("remoteok", "Remote OK")
        still = posting(src, url="https://r.test/1", seen_days_ago=2)
        gone = posting(src, url="https://r.test/2", seen_days_ago=2)
        hidden_src = source("remotive", "Remotive", show_publicly=False)
        with mock.patch("tracker.services.scan.fetch_remoteok", return_value=[{"title": "T", "url": "https://r.test/1", "location": "Remote", "company": "C", "description": "text"}]) as fetch, \
                mock.patch("tracker.services.scan.fetch_remotive") as not_called:
            result = public.refresh_now()
        fetch.assert_called_once()
        not_called.assert_not_called()  # a source that may not be shown is not even read for the board
        self.assertEqual(result, {"sources": 1, "errors": 0, "postings": 1})
        still.refresh_from_db(); gone.refresh_from_db()
        self.assertGreater(still.last_seen_at, timezone.now() - timedelta(minutes=1))
        self.assertLess(gone.last_seen_at, timezone.now() - timedelta(days=1))
        self.assertTrue(Posting.objects.get(pk=still.pk).excerpt == "text")

    def test_a_source_that_fails_is_counted_not_fatal(self):
        source("remoteok", "Remote OK")
        with mock.patch("tracker.services.scan.fetch_remoteok", side_effect=scan.FetchError("HTTP 503")):
            self.assertEqual(public.refresh_now()["errors"], 1)

    def test_the_command_reports(self):
        from io import StringIO
        out = StringIO()
        with mock.patch("tracker.services.public.refresh_now", return_value={"sources": 3, "errors": 1, "postings": 40}):
            call_command("refresh_postings", stdout=out)
        self.assertIn("Read 3 public source(s); 40 opening(s) seen; 1 source(s) did not answer.", out.getvalue())

    @override_settings(STILLOPEN_PUBLIC_AUTO_REFRESH=True)
    def test_a_visitor_triggers_one_background_refresh_when_stale_and_only_one(self):
        posting(source(), seen_days_ago=2)  # stale: older than the refresh interval
        with mock.patch("tracker.services.public.threading.Thread") as thread:
            self.assertTrue(public.refresh_if_stale())
            self.assertFalse(public.refresh_if_stale())  # locked and throttled
        thread.assert_called_once()

    @override_settings(STILLOPEN_PUBLIC_AUTO_REFRESH=True)
    def test_nothing_starts_when_fresh_or_switched_off(self):
        posting(source(), seen_days_ago=0)
        with mock.patch("tracker.services.public.threading.Thread") as thread:
            self.assertFalse(public.refresh_if_stale())
        thread.assert_not_called()
        Posting.objects.update(last_seen_at=timezone.now() - timedelta(days=2))
        with override_settings(STILLOPEN_PUBLIC_AUTO_REFRESH=False), mock.patch("tracker.services.public.threading.Thread") as thread:
            self.assertFalse(public.refresh_if_stale())
        thread.assert_not_called()

    @override_settings(STILLOPEN_PUBLIC_AUTO_REFRESH=True)
    def test_an_empty_site_counts_as_stale_and_refreshes(self):
        with mock.patch("tracker.services.public.threading.Thread") as thread:
            self.assertTrue(public.refresh_if_stale())
        thread.assert_called_once()

    @override_settings(STILLOPEN_PUBLIC_AUTO_REFRESH=True)
    def test_visiting_the_landing_page_never_waits_for_it_and_never_fails(self):
        with mock.patch("tracker.services.public.threading.Thread"):
            self.assertEqual(self.client.get(reverse("landing")).status_code, 200)


class StandardLook(PublicTestCase):
    def test_light_by_default_with_the_theme_script_and_brand_css_on_every_kind_of_page(self):
        user = User.objects.create_user("look", password="x" * 14)
        from tracker.models import UserProfile
        UserProfile.objects.filter(user=user).update(onboarding_done=True, target_roles="x")
        pages = [self.client.get(reverse(n)) for n in ("landing", "openings", "privacy", "terms", "account_login", "account_signup")]
        self.client.force_login(user)
        pages.append(self.client.get(reverse("dashboard")))
        for r in pages:
            html = r.content.decode()
            self.assertEqual(r.status_code, 200)
            self.assertIn('data-bs-theme="light"', html)
            self.assertIn("/static/js/theme.js", html)
            self.assertIn("/static/css/stillopen.css", html)
            self.assertIn("data-theme-toggle", html)

    def test_the_theme_script_defaults_to_light_and_remembers_a_dark_choice(self):
        from pathlib import Path
        js = (Path(__file__).resolve().parent.parent / "static" / "js" / "theme.js").read_text(encoding="utf-8")
        self.assertIn("saved === 'dark' ? 'dark' : 'light'", js)
        self.assertIn("localStorage", js)
        self.assertNotIn("prefers-color-scheme", js)

    def test_the_public_header_has_standard_navigation(self):
        html = self.client.get(reverse("landing")).content.decode()
        for text in ("Browse jobs", "How it works", "FAQ", "Sign in"):
            self.assertIn(text, html)
        self.assertIn('lang="en"', html)
        self.assertIn('rel="canonical"', html)
        self.assertIn('property="og:title"', html)


class TextIsCleanBeforeItIsShown(TestCase):
    def test_escaped_html_from_greenhouse_becomes_plain_text(self):
        raw = "&lt;div class=&quot;content-intro&quot;&gt;&lt;p&gt;&lt;a href=&quot;https://x.test&quot;&gt;Xendit&lt;/a&gt; is a payments platform.&lt;/p&gt;&lt;/div&gt;"
        out = scan._blurb(raw)
        self.assertEqual(out, "Xendit is a payments platform.")
        self.assertNotIn("<", out)
        self.assertNotIn("&lt;", out)

    def test_ordinary_html_still_works_and_plain_text_is_untouched(self):
        self.assertEqual(scan._blurb("<p>Build <b>APIs</b></p>"), "Build APIs")
        self.assertEqual(scan._blurb("Just plain text, 5 < 6."), "Just plain text, 5 < 6.")
        self.assertEqual(scan._blurb(""), "")
        self.assertEqual(scan._blurb(None), "")

    def test_the_public_excerpt_never_carries_markup_even_if_the_source_text_did(self):
        out = scan.excerpt_of('<div class="a"><p>Hello &amp; welcome</p><script>alert(1)</script></div>')
        self.assertNotIn("<", out)
        self.assertIn("Hello & welcome", out)

    def test_the_greenhouse_connector_applies_it(self):
        resp = mock.Mock(status_code=200)
        resp.json.return_value = {"jobs": [{"title": "Eng", "absolute_url": "https://x.test/1", "location": {"name": "KL"}, "content": "&lt;p&gt;We build &lt;b&gt;things&lt;/b&gt;&lt;/p&gt;"}]}
        with mock.patch("tracker.services.scan.safe_get", return_value=resp):
            self.assertEqual(scan.fetch_greenhouse("x")[0]["description"], "We build things")


class BoardFilters(PublicTestCase):
    def setUp(self):
        super().setUp()
        self.src = source("greenhouse", "Acme")
        posting(self.src, title="Visa job", country="DE", sponsorship="yes", relocation="yes", employment_type="full_time", seniority="senior")
        posting(self.src, title="No visa job", country="DE", sponsorship="no", employment_type="contract", seniority="junior", first_days_ago=20)
        posting(self.src, title="Silent job", country="MY")

    def titles(self, **q):
        return {x["p"].title for x in self.client.get(reverse("openings"), q).context["rows"]}

    def test_visa_relocation_type_level_and_age_filters(self):
        self.assertEqual(self.titles(visa="1"), {"Visa job"})
        self.assertEqual(self.titles(relocation="1"), {"Visa job"})
        self.assertEqual(self.titles(type="contract"), {"No visa job"})
        self.assertEqual(self.titles(level="senior"), {"Visa job"})
        self.assertEqual(self.titles(within="7"), {"Visa job", "Silent job"})
        self.assertEqual(self.titles(visa="1", country="MY"), set())

    def test_junk_filter_values_are_ignored(self):
        self.assertEqual(len(self.titles(type="<x>", level="zzz", within="-1")), 3)

    def test_every_country_in_the_world_is_selectable_and_a_quiet_one_says_so(self):
        r = self.client.get(reverse("openings"), {"country": "BD"})
        self.assertContains(r, 'value="BD"')
        self.assertContains(r, 'value="ZW"')
        self.assertContains(r, "None of the sources we read have an opening in Bangladesh")
        self.assertEqual(len(r.context["countries_with_jobs"]) + len(r.context["countries_without"]), 249)

    def test_cards_show_the_visa_badge(self):
        self.assertContains(self.client.get(reverse("openings")), "Visa sponsorship</span>")


class TermsRecorded(PublicTestCase):
    def test_a_scan_records_what_the_posting_says(self):
        src = source("greenhouse", "Acme")
        scan.record_sightings(src, [
            {"title": "Senior Engineer", "url": "https://x.test/1", "location": "Berlin, Germany", "company": "Acme", "description": "<p>We offer visa sponsorship and a relocation package. Full-time.</p>"},
            {"title": "Cook", "url": "https://x.test/2", "location": "Berlin, Germany", "company": "Acme", "description": "Make food."},
        ])
        a, b = Posting.objects.get(url="https://x.test/1"), Posting.objects.get(url="https://x.test/2")
        self.assertEqual((a.sponsorship, a.relocation, a.employment_type, a.seniority), ("yes", "yes", "full_time", "senior"))
        self.assertEqual((b.sponsorship, b.relocation), ("", ""))
