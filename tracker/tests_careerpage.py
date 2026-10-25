"""The careers page reader. Every page here is a local string served by a fake `safe_get`: the tests never touch the internet.
THE PAGES ARE REPRESENTATIVE of how companies publish JobPosting JSON-LD, written for these tests, not copied from real sites."""
import json
from unittest import mock

from django.test import TestCase

from tracker.services import careerpage as cp
from tracker.services import netguard

HOST = "careers.example.com"


class Resp:
    def __init__(self, text="", status=200, headers=None, url="", ctype="text/html; charset=utf-8"):
        self.text, self.status_code, self.url = text, status, url
        self.content = text.encode()
        self.headers = {"Content-Type": ctype, **(headers or {})}


def ld(*objects, wrap=None):
    data = objects[0] if len(objects) == 1 else list(objects)
    if wrap:
        data = wrap(data)
    return f'<script type="application/ld+json">{json.dumps(data)}</script>'


def job(title="Backend Engineer", **extra):
    base = {
        "@context": "https://schema.org", "@type": "JobPosting", "title": title, "url": f"https://{HOST}/jobs/{title.lower().replace(' ', '-')}",
        "hiringOrganization": {"@type": "Organization", "name": "Example Corp"}, "description": "<p>Build &amp; run <b>services</b>.</p>",
        "jobLocation": {"@type": "Place", "address": {"@type": "PostalAddress", "addressLocality": "Berlin", "addressCountry": "DE"}},
    }
    base.update(extra)
    return base


def page(body: str, head: str = "") -> str:
    return f"<html><head>{head}</head><body>{body}</body></html>"


class Fake:
    """A fake `safe_get` with a clock: each call advances it only by the sleeps the reader asks for, so spacing can be checked exactly."""

    def __init__(self, pages: dict[str, Resp | str], robots: str | Resp | None = "User-agent: *\nAllow: /\n"):
        self.pages, self.calls, self.now = dict(pages), [], 1000.0
        self.times: list[tuple[float, str]] = []
        self.pages.setdefault(f"https://{HOST}/robots.txt", robots if isinstance(robots, Resp) else Resp(robots or "", 200 if robots is not None else 404))

    def get(self, url, timeout=0, headers=None):
        self.calls.append(url)
        self.times.append((self.now, url))
        self.headers = headers
        found = self.pages.get(url)
        if found is None:
            return Resp("", 404, url=url)
        resp = Resp(found, url=url) if isinstance(found, str) else found
        resp.url = resp.url or url
        return resp

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds

    def read(self, url=f"https://{HOST}/careers"):
        return cp.read(url, get=self.get, clock=self.clock, sleep=self.sleep)


LIST = f"https://{HOST}/careers"


class Shapes(TestCase):
    def read(self, html):
        return Fake({LIST: html}).read()

    def test_single_object(self):
        out = self.read(page(ld(job())))
        self.assertEqual(len(out), 1)
        p = out[0]
        self.assertEqual((p["title"], p["company"], p["location"]), ("Backend Engineer", "Example Corp", "Berlin, DE"))
        self.assertEqual(p["url"], f"https://{HOST}/jobs/backend-engineer")
        self.assertIn("Build & run services.", p["description"])
        self.assertNotIn("<b>", p["description"])

    def test_array(self):
        self.assertEqual([p["title"] for p in self.read(page(ld(job("A One"), job("B Two"))))], ["A One", "B Two"])

    def test_graph(self):
        html = page(ld(job("A One"), job("B Two"), wrap=lambda d: {"@context": "https://schema.org", "@graph": [{"@type": "WebSite"}, *d]}))
        self.assertEqual(len(self.read(html)), 2)

    def test_nested_item_list(self):
        items = {"@type": "ItemList", "itemListElement": [{"@type": "ListItem", "position": 1, "item": job("A One")}, {"@type": "ListItem", "position": 2, "item": job("B Two")}]}
        self.assertEqual(len(self.read(page(ld(items)))), 2)

    def test_type_as_list_and_several_blocks(self):
        html = page(ld(job("A One", **{"@type": ["JobPosting", "Thing"]})) + ld(job("B Two")) + "<script type='application/ld+json'>{broken json</script>")
        self.assertEqual(len(self.read(html)), 2)

    def test_remote_pay_type_dates(self):
        node = job(
            "Remote Dev", jobLocationType="TELECOMMUTE", jobLocation=None, applicantLocationRequirements={"@type": "Country", "name": "Germany"},
            baseSalary={"@type": "MonetaryAmount", "currency": "EUR", "value": {"@type": "QuantitativeValue", "minValue": 60000, "maxValue": 80000, "unitText": "YEAR"}},
            employmentType=["FULL_TIME"], datePosted="2026-10-01", validThrough="2026-12-01T00:00",
        )
        p = self.read(page(ld(node)))[0]
        self.assertEqual(p["location"], "Remote (Germany)")
        for fragment in ("Pay: EUR 60000 to 80000 per year", "Employment: Full Time", "Posted: 2026-10-01", "Apply by: 2026-12-01"):
            self.assertIn(fragment, p["description"])

    def test_several_locations_and_missing_url_gets_a_distinct_address(self):
        node = job("Multi", jobLocation=[{"address": {"addressLocality": "Berlin"}}, {"address": {"addressLocality": "Paris"}}])
        node.pop("url")
        node2 = dict(node, title="Multi Two")
        out = self.read(page(ld(node, node2)))
        self.assertEqual(out[0]["location"], "Berlin; Paris")
        self.assertEqual(len({p["url"] for p in out}), 2)

    def test_a_hostile_job_url_is_replaced_by_the_page(self):
        out = self.read(page(ld(job(url="javascript:alert(1)"))))
        self.assertEqual(out[0]["url"], LIST)
        out = self.read(page(ld(job(url="https://www.linkedin.com/jobs/view/123456789/"))))
        self.assertEqual(out[0]["url"], LIST)  # a link to a site we never read is not used either

    def test_no_title_is_skipped_and_page_without_data_is_empty(self):
        self.assertEqual(self.read(page(ld(job(title="")))), [])
        self.assertEqual(self.read(page("<p>No jobs</p>")), [])


class Following(TestCase):
    def test_links_to_opening_pages_are_read_and_off_host_and_other_links_are_not(self):
        listing = page(
            f'<a href="/jobs/1">One</a><a href="/careers/2">Two</a><a href="https://{HOST}/jobs/3#top">Three</a>'
            '<a href="https://evil.example.net/jobs/9">Off host</a><a href="/about">About</a><a href="/files/jobs.pdf">PDF</a>'
            '<a href="mailto:a@b.c">mail</a><a href="javascript:void(0)">js</a><a href="/jobs/1">dup</a>'
        )
        fake = Fake({
            LIST: listing,
            f"https://{HOST}/jobs/1": page(ld(job("Job One", url=f"https://{HOST}/jobs/1"))),
            f"https://{HOST}/careers/2": page(ld(job("Job Two", url=f"https://{HOST}/careers/2"))),
            f"https://{HOST}/jobs/3": page(ld(job("Job Three", url=f"https://{HOST}/jobs/3"))),
        })
        out = fake.read()
        self.assertEqual([p["title"] for p in out], ["Job One", "Job Two", "Job Three"])
        self.assertTrue(all("evil.example.net" not in c for c in fake.calls))
        self.assertNotIn(f"https://{HOST}/about", fake.calls)
        self.assertFalse(any(c.endswith(".pdf") for c in fake.calls))

    def test_page_cap_and_detail_cap(self):
        links = "".join(f'<a href="/jobs/{n}">J{n}</a>' for n in range(80))
        pages = {LIST: page(links)}
        pages.update({f"https://{HOST}/jobs/{n}": page(ld(job(f"Job {n}", url=f"https://{HOST}/jobs/{n}"))) for n in range(80)})
        fake = Fake(pages)
        out = fake.read()
        self.assertEqual(len(out), cp.MAX_DETAIL_PAGES)
        self.assertLessEqual(len(fake.calls), cp.MAX_REQUESTS)
        self.assertEqual(len(fake.calls), 1 + 1 + cp.MAX_DETAIL_PAGES)  # robots.txt, the list, 25 openings

    def test_relative_links_resolve_against_the_page(self):
        fake = Fake({f"https://{HOST}/careers/": page('<a href="../jobs/7">x</a><a href="open/8">y</a>'),
                     f"https://{HOST}/jobs/7": page(ld(job("Seven", url=f"https://{HOST}/jobs/7"))),
                     f"https://{HOST}/careers/open/8": page(ld(job("Eight", url=f"https://{HOST}/careers/open/8")))})
        self.assertEqual([p["title"] for p in fake.read(f"https://{HOST}/careers/")], ["Seven", "Eight"])

    def test_oversize_pages_are_skipped(self):
        big = Resp(page(ld(job("Huge"))))
        big.content = b"x" * (cp.MAX_PAGE_BYTES + 1)
        fake = Fake({LIST: page('<a href="/jobs/1">x</a>'), f"https://{HOST}/jobs/1": big})
        self.assertEqual(fake.read(), [])


class Politeness(TestCase):
    def test_robots_disallow_refuses_with_a_plain_message(self):
        fake = Fake({LIST: page(ld(job()))}, robots="User-agent: *\nDisallow: /careers\n")
        with self.assertRaises(cp.CareerPageError) as caught:
            fake.read()
        self.assertIn("robots.txt says no", str(caught.exception))
        self.assertNotIn(LIST, fake.calls)  # the page itself was never requested

    def test_robots_for_our_own_name_is_obeyed(self):
        fake = Fake({LIST: page(ld(job()))}, robots="User-agent: StillOpen\nDisallow: /\n")
        with self.assertRaises(cp.CareerPageError):
            fake.read()

    def test_a_disallowed_opening_page_is_skipped_others_are_read(self):
        fake = Fake(
            {LIST: page('<a href="/jobs/1">x</a><a href="/jobs/private/2">y</a>'),
             f"https://{HOST}/jobs/1": page(ld(job("One", url=f"https://{HOST}/jobs/1"))),
             f"https://{HOST}/jobs/private/2": page(ld(job("Two", url=f"https://{HOST}/jobs/private/2")))},
            robots="User-agent: *\nDisallow: /jobs/private\n",
        )
        self.assertEqual([p["title"] for p in fake.read()], ["One"])
        self.assertNotIn(f"https://{HOST}/jobs/private/2", fake.calls)

    def test_robots_401_403_means_closed_404_means_open_5xx_means_try_later(self):
        with self.assertRaises(cp.CareerPageError):
            Fake({LIST: page(ld(job()))}, robots=Resp("", 403)).read()
        self.assertEqual(len(Fake({LIST: page(ld(job()))}, robots=Resp("", 404)).read()), 1)
        with self.assertRaises(cp.CareerPageError) as caught:
            Fake({LIST: page(ld(job()))}, robots=Resp("", 503)).read()
        self.assertIn("robots.txt did not answer", str(caught.exception))

    def test_noindex_meta_and_header_are_respected(self):
        meta = '<meta name="robots" content="noindex, follow">'
        with self.assertRaises(cp.CareerPageError):
            Fake({LIST: page(ld(job()), head=meta)}).read()
        with self.assertRaises(cp.CareerPageError):
            Fake({LIST: Resp(page(ld(job())), headers={"X-Robots-Tag": "noindex"})}).read()
        self.assertEqual(len(Fake({LIST: page(ld(job()), head='<meta name="robots" content="index,follow">')}).read()), 1)

    def test_noindex_opening_pages_are_skipped(self):
        fake = Fake({LIST: page('<a href="/jobs/1">x</a><a href="/jobs/2">y</a>'),
                     f"https://{HOST}/jobs/1": page(ld(job("One", url=f"https://{HOST}/jobs/1")), head='<meta name="googlebot" content="noindex">'),
                     f"https://{HOST}/jobs/2": page(ld(job("Two", url=f"https://{HOST}/jobs/2")))})
        self.assertEqual([p["title"] for p in fake.read()], ["Two"])

    def test_one_request_per_second_per_host(self):
        fake = Fake({LIST: page('<a href="/jobs/1">x</a><a href="/jobs/2">y</a>'),
                     f"https://{HOST}/jobs/1": page(ld(job("One", url=f"https://{HOST}/jobs/1"))),
                     f"https://{HOST}/jobs/2": page(ld(job("Two", url=f"https://{HOST}/jobs/2")))})
        fake.read()
        stamps = [t for t, _ in fake.times]
        self.assertGreaterEqual(len(stamps), 4)
        for earlier, later in zip(stamps, stamps[1:]):
            self.assertGreaterEqual(later - earlier, cp.MIN_GAP_SECONDS - 1e-9)

    def test_the_request_names_stillopen_and_a_contact(self):
        fake = Fake({LIST: page(ld(job()))})
        with self.settings(STILLOPEN_BOT_CONTACT="https://stillopen.example/bot"):
            fake.read()
        self.assertIn("StillOpen", fake.headers["User-Agent"])
        self.assertIn("https://stillopen.example/bot", fake.headers["User-Agent"])

    def test_the_run_stops_when_it_takes_too_long(self):
        fake = Fake({LIST: page('<a href="/jobs/1">x</a><a href="/jobs/2">y</a>'),
                     f"https://{HOST}/jobs/1": page(ld(job("One", url=f"https://{HOST}/jobs/1"))),
                     f"https://{HOST}/jobs/2": page(ld(job("Two", url=f"https://{HOST}/jobs/2")))})
        original = fake.get

        def slow(url, **kw):
            fake.now += cp.MAX_RUN_SECONDS  # every request "takes" the whole budget
            return original(url, **kw)

        out = cp.read(LIST, get=slow, clock=fake.clock, sleep=fake.sleep)
        self.assertLessEqual(len(out), 1)

    def test_a_redirect_to_another_host_is_checked_against_that_hosts_robots(self):
        other = "https://www.example.com/careers"
        fake = Fake({LIST: Resp(page(ld(job())), url=other), "https://www.example.com/robots.txt": Resp("User-agent: *\nDisallow: /\n")})
        with self.assertRaises(cp.CareerPageError):
            fake.read()


class Addresses(TestCase):
    def test_only_public_https_without_credentials(self):
        for bad in ("http://careers.example.com/", "ftp://x.example.com/", "https://user:pw@careers.example.com/", "https://careers.example.com:8443/", "https://localhost/", "careers.example.com",
                    "https://" + "a" * 300 + ".example.com/", "https://www.linkedin.com/company/acme/jobs/", "https://uk.indeed.com/cmp/acme/jobs", "javascript:alert(1)", ""):
            with self.assertRaises(ValueError, msg=bad):
                cp.normalise_url(bad)
        self.assertEqual(cp.normalise_url("https://Careers.Example.com/Jobs?x=1#top"), "https://careers.example.com/Jobs?x=1")
        self.assertEqual(cp.normalise_url("https://careers.example.com"), "https://careers.example.com/")

    def test_a_private_address_is_refused_before_any_request(self):
        with mock.patch.object(netguard, "_resolve", return_value=["10.0.0.5"]), mock.patch.object(netguard, "_get_pinned") as sent:
            with self.assertRaises(cp.CareerPageError) as caught:
                cp.read("https://intranet.example.com/careers", clock=lambda: 0.0, sleep=lambda s: None)
        self.assertIn("public website", str(caught.exception))
        sent.assert_not_called()

    def test_a_redirect_to_a_private_address_is_refused(self):
        redirect = Resp("", 302, headers={"location": "http://169.254.169.254/latest/meta-data/"})
        redirect.is_redirect = True
        public = Resp("User-agent: *\nAllow: /\n")
        public.is_redirect = False

        def resolve(host, port):
            return ["93.184.216.34"] if host.endswith("example.com") else ["169.254.169.254"]

        replies = iter([public, redirect])
        with mock.patch.object(netguard, "_resolve", side_effect=resolve), mock.patch.object(netguard, "_get_pinned", side_effect=lambda *a, **k: next(replies)):
            with self.assertRaises(cp.CareerPageError) as caught:
                cp.read("https://careers.example.com/careers", clock=lambda: 0.0, sleep=lambda s: None)
        self.assertIn("public website", str(caught.exception))

    def test_linkedin_indeed_glassdoor_are_never_requested_by_safe_get(self):
        for url in ("https://www.linkedin.com/jobs/view/123456789/", "https://uk.indeed.com/viewjob?jk=0123456789abcdef", "https://www.glassdoor.com/job-listing/x.htm?jl=1"):
            with mock.patch.object(netguard, "_get_pinned") as sent, mock.patch.object(netguard, "_resolve", return_value=["93.184.216.34"]):
                with self.assertRaises(netguard.FetchError):
                    netguard.safe_get(url)
            sent.assert_not_called()
