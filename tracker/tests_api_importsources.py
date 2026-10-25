"""The email-import route, the careers-page route, and LinkedIn links in quick-add, through the JSON API: plain messages, limits, isolation and
"nothing is ever requested from a site that forbids it". Fake pages and fake fetchers only; the tests never touch the internet."""
import json
from email.message import EmailMessage
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from tracker.models import Application, JobSource
from tracker.services import blockedhosts, jobtext, netguard, scan, tracking
from tracker.tests_api import BASE, job, person
from tracker.tests_careerpage import HOST, LIST, Fake, job as ld_job, ld, page

EMAIL = "Backend Engineer\nAcme Robotics\nBerlin, Germany\nhttps://jobs.example.org/apply/1?utm_source=x\n\nData Analyst\nInitech\nRemote\nhttps://jobs.example.org/apply/2\n"


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        self.client.force_login(self.a)

    def post(self, path, body):
        return self.client.post(f"{BASE}{path}", data=json.dumps(body), content_type="application/json")


class EmailRoute(Base):
    def test_preview_adds_nothing_and_flags_duplicates(self):
        job(self.a, company="Initech", role="Data Analyst")
        r = self.post("/jobs/import-email?preview=1", {"text": EMAIL})
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual((data["found"], data["will_add"]), (2, 1))
        self.assertEqual(data["rows"][1]["duplicate"]["company"], "Initech")
        self.assertEqual(Application.objects.filter(owner=self.a).count(), 1)

    def test_real_import_adds_only_the_ticked_rows(self):
        r = self.post("/jobs/import-email", {"text": EMAIL, "selected": [0]})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["added"], 1)
        self.assertEqual(list(Application.objects.filter(owner=self.a).values_list("role", "url")), [("Backend Engineer", "https://jobs.example.org/apply/1")])
        again = self.post("/jobs/import-email", {"text": EMAIL, "selected": [0, 1]}).json()
        self.assertEqual((again["added"], again["skipped_count"]), (1, 1))

    def test_nothing_ticked_and_nothing_found_are_plain_400s(self):
        r = self.post("/jobs/import-email", {"text": EMAIL, "selected": []})
        self.assertEqual((r.status_code, r.json()["error"]), (400, "Tick at least one job to add."))
        self.assertEqual(self.post("/jobs/import-email?preview=1", {"text": "   "}).status_code, 400)
        r = self.post("/jobs/import-email", {"text": "just a sentence of nothing useful here."})
        self.assertEqual(r.status_code, 400)

    def test_multipart_text_and_eml_file(self):
        r = self.client.post(f"{BASE}/jobs/import-email?preview=1", {"text": EMAIL})
        self.assertEqual(r.json()["found"], 2)
        msg = EmailMessage()
        msg["Subject"] = "alert"
        msg.set_content(EMAIL)
        up = SimpleUploadedFile("alert.eml", bytes(msg), content_type="message/rfc822")
        r = self.client.post(f"{BASE}/jobs/import-email", {"file": up, "selected": "0,1"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["added"], 2)

    def test_size_cap(self):
        r = self.post("/jobs/import-email?preview=1", {"text": "x" * (500 * 1024 + 1)})
        self.assertEqual(r.status_code, 400)
        self.assertIn("500 KB", r.json()["error"])
        up = SimpleUploadedFile("big.eml", b"x" * (500 * 1024 + 1))
        r = self.client.post(f"{BASE}/jobs/import-email?preview=1", {"file": up})
        self.assertEqual(r.status_code, 400)

    def test_job_limit_message(self):
        with self.settings(STILLOPEN_MAX_APPLICATIONS=1):
            job(self.a, company="Existing", role="Thing")
            data = self.post("/jobs/import-email", {"text": EMAIL}).json()
        self.assertEqual(data["added"], 0)
        self.assertIn("limit of 1 tracked jobs", data["stopped"])

    @override_settings(STILLOPEN_IMPORTS_PER_HOUR=3)
    def test_throttle(self):
        codes = [self.post("/jobs/import-email?preview=1", {"text": EMAIL}).status_code for _ in range(4)]
        self.assertEqual(codes, [200, 200, 200, 429])

    def test_isolation_between_people(self):
        job(self.b, company="Initech", role="Data Analyst")
        self.assertEqual(self.post("/jobs/import-email?preview=1", {"text": EMAIL}).json()["will_add"], 2)
        self.post("/jobs/import-email", {"text": EMAIL})
        self.assertEqual(Application.objects.filter(owner=self.b).count(), 1)
        self.assertEqual(Application.objects.filter(owner=self.a).count(), 2)

    def test_a_hostile_email_is_data(self):
        html = '<a href="javascript:alert(1)">Job Hacker</a><script>x</script><a href="https://ok.example/jobs/1">&lt;script&gt;alert(1)&lt;/script&gt; Engineer</a><p>Acme</p>'
        data = self.post("/jobs/import-email?preview=1", {"html": html}).json()
        self.assertEqual(data["found"], 1)
        self.assertNotIn("javascript:", json.dumps(data))
        self.assertEqual(data["rows"][0]["title"], "<script>alert(1)</script> Engineer")  # plain text; React renders it as text


@override_settings(STILLOPEN_SOURCE_ADDS_PER_HOUR=1000)
class CareersPage(Base):
    def add(self, url="https://careers.example.com/careers", name="", pages=None, robots="User-agent: *\nAllow: /\n"):
        from tracker.services import careerpage

        fake = Fake(pages if pages is not None else {LIST: page(ld(ld_job()))}, robots=robots)
        self.fake = fake
        read = lambda token: careerpage.read(token, get=fake.get, clock=fake.clock, sleep=fake.sleep)  # noqa: E731
        with mock.patch("tracker.forms.check_public_url"), mock.patch.object(scan, "fetch_careerpage", read):
            return self.post("/sources/careers-page", {"url": url, "name": name})

    def test_add_checks_the_page_once_and_saves_the_normalised_address(self):
        r = self.add(url="https://Careers.Example.com/careers#x", name="Example")
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual(data["openings"], 1)
        self.assertIn("We found 1 opening", data["message"])
        src = JobSource.objects.get(owner=self.a)
        self.assertEqual((src.connector, src.board_token, src.name), ("careerpage", "https://careers.example.com/careers", "Example"))
        self.assertEqual(data["source"]["host"], "careers.example.com")

    def test_name_defaults_to_the_host(self):
        self.add()
        self.assertEqual(JobSource.objects.get(owner=self.a).name, "careers.example.com")

    def test_no_list_found_is_the_plain_message_and_nothing_is_saved(self):
        r = self.add(pages={LIST: page("<p>Welcome</p>")})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"], "We could not find a list of openings on that page. Try a page that lists jobs, or paste single job links into Add job.")
        self.assertFalse(JobSource.objects.exists())

    def test_robots_disallow_is_refused_in_plain_words(self):
        r = self.add(robots="User-agent: *\nDisallow: /\n")
        self.assertEqual(r.status_code, 400)
        self.assertIn("robots.txt says no", r.json()["error"])
        self.assertFalse(JobSource.objects.exists())

    def test_bad_addresses_are_field_errors(self):
        for bad in ("http://careers.example.com/", "https://user:pw@careers.example.com/", "https://careers.example.com:8080/", "not a url", "https://www.linkedin.com/company/x/jobs/"):
            r = self.add(url=bad)
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn("board_token", r.json()["fields"], bad)
        self.assertFalse(JobSource.objects.exists())

    def test_a_private_address_is_refused(self):
        with mock.patch.object(netguard, "_resolve", return_value=["192.168.1.9"]):
            r = self.post("/sources/careers-page", {"url": "https://intranet.example.com/jobs"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("not a public website", r.json()["fields"]["board_token"][0])

    def test_duplicate_is_information_not_a_problem(self):
        self.add()
        r = self.add()
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["info"], "You already added that board.")
        self.assertEqual(JobSource.objects.count(), 1)

    @override_settings(STILLOPEN_MAX_OWN_SOURCES=1)
    def test_the_per_person_cap_covers_careers_pages(self):
        self.assertEqual(self.add().status_code, 200)
        r = self.add(url="https://careers.example.com/other")
        self.assertEqual(r.status_code, 400)
        self.assertIn("up to 1 boards", r.json()["error"])

    @override_settings(STILLOPEN_SOURCE_ADDS_PER_HOUR=1)
    def test_the_hourly_limit_applies(self):
        self.assertEqual(self.add().status_code, 200)
        self.assertEqual(self.add(url="https://careers.example.com/two").status_code, 429)

    def test_the_generic_add_route_does_not_offer_or_accept_it_as_a_company_token(self):
        data = self.client.get(f"{BASE}/sources").json()
        self.assertNotIn("careerpage", [c["value"] for c in data["connectors"]])
        r = self.post("/sources", {"connector": "careerpage", "board_token": "http://169.254.169.254/", "name": ""})
        self.assertEqual(r.status_code, 400)

    def test_isolation(self):
        self.add()
        src = JobSource.objects.get(owner=self.a)
        self.client.force_login(self.b)
        self.assertEqual(self.client.get(f"{BASE}/sources").json()["mine"], [])
        self.assertEqual(self.client.post(f"{BASE}/sources/{src.pk}/toggle").status_code, 404)
        self.assertEqual(self.client.delete(f"{BASE}/sources/{src.pk}").status_code, 404)
        self.assertNotIn(src, list(scan.searchable_sources(self.b)))
        self.assertIn(src, list(scan.searchable_sources(self.a)))

    def test_the_scan_reads_it_through_the_connector_and_it_is_never_public(self):
        fake = Fake({LIST: page(ld(ld_job("Platform Engineer")))})
        src = JobSource.objects.create(owner=self.a, name="Example", connector="careerpage", board_token=LIST)
        from tracker.services import careerpage

        with mock.patch.object(scan, "fetch_careerpage", lambda t: careerpage.read(t, get=fake.get, clock=fake.clock, sleep=fake.sleep)):
            postings = scan._fetch_cached(src)
        self.assertEqual(postings[0]["title"], "Platform Engineer")
        self.assertFalse(src.show_publicly)
        from tracker.services import public

        self.assertNotIn(src.pk, list(public.public_sources().values_list("pk", flat=True)) if hasattr(public, "public_sources") else [])


class BlockedLinks(Base):
    VARIANTS = {
        "https://www.linkedin.com/jobs/view/3812345678/": "3812345678",
        "https://www.linkedin.com/jobs/view/senior-engineer-at-acme-3812345678?trackingId=abc&refId=x": "3812345678",
        "https://www.linkedin.com/comm/jobs/view/3812345678?trk=eml": "3812345678",
        "https://uk.linkedin.com/jobs/collections/recommended/?currentJobId=3812345678&discover=true": "3812345678",
        "https://www.linkedin.com/jobs/search/?keywords=engineer&currentJobId=3812345678": "3812345678",
    }

    def test_every_variant_is_canonicalised_and_nothing_is_requested(self):
        for variant, job_id in self.VARIANTS.items():
            with mock.patch.object(tracking, "fetch_prefill") as read, mock.patch.object(jobtext, "safe_get") as get, mock.patch.object(netguard, "_get_pinned") as sent:
                r = self.post("/quickadd", {"url": variant})
            self.assertEqual(r.status_code, 200, variant)
            data = r.json()
            self.assertEqual(data["blocked_host"], "linkedin")
            self.assertEqual(data["url"], f"https://www.linkedin.com/jobs/view/{job_id}/")
            self.assertEqual(data["message"], "LinkedIn does not let other apps read its pages, so we have kept the link and need the text from you: open the job on LinkedIn, select the description, copy and paste it below.")
            read.assert_not_called()
            get.assert_not_called()
            sent.assert_not_called()

    def test_short_links_are_never_followed(self):
        with mock.patch.object(netguard, "_get_pinned") as sent:
            data = self.post("/quickadd", {"url": "https://lnkd.in/abc123"}).json()
        self.assertEqual(data["blocked_host"], "linkedin")
        self.assertEqual(data["url"], "https://lnkd.in/abc123")
        sent.assert_not_called()

    def test_indeed_glassdoor_and_others_get_the_same_treatment(self):
        for url, host, label in (
            ("https://uk.indeed.com/viewjob?jk=0123456789abcdef&from=ja", "indeed", "Indeed"),
            ("https://www.glassdoor.com/job-listing/x-JV.htm?jl=1009&utm_source=y", "glassdoor", "Glassdoor"),
            ("https://www.ziprecruiter.com/c/Acme/Job/Dev", "ziprecruiter", "ZipRecruiter"),
        ):
            with mock.patch.object(netguard, "_get_pinned") as sent:
                data = self.post("/quickadd", {"url": url}).json()
            self.assertEqual(data["blocked_host"], host)
            self.assertTrue(data["message"].startswith(f"{label} does not let other apps read its pages"))
            self.assertNotIn("utm_source", data["url"])
            sent.assert_not_called()

    def test_other_links_still_go_through_the_normal_reader(self):
        with mock.patch.object(tracking, "fetch_prefill", return_value={"url": "https://jobs.example.org/1", "role": "Dev", "company": "Acme", "description": "x"}) as read:
            data = self.post("/quickadd", {"url": "https://jobs.example.org/1"}).json()
        read.assert_called_once()
        self.assertNotIn("blocked_host", data)

    def test_the_duplicate_link_is_flagged(self):
        job(self.a, company="Acme", role="Dev", url="https://www.linkedin.com/jobs/view/3812345678/")
        data = self.post("/quickadd", {"url": "https://www.linkedin.com/jobs/view/3812345678/?trackingId=z"}).json()
        self.assertEqual(data["duplicate"]["company"], "Acme")

    def test_the_text_readers_refuse_before_any_request(self):
        for fetch in (jobtext.fetch_posting, jobtext.fetch_description):
            with mock.patch.object(netguard, "_get_pinned") as sent, mock.patch.object(netguard, "_resolve", return_value=["93.184.216.34"]):
                with self.assertRaises(jobtext.FetchError):
                    fetch("https://www.linkedin.com/jobs/view/3812345678/", mock.Mock(careerops_path="", restricted=True))
            sent.assert_not_called()

    def test_helpers(self):
        self.assertEqual(blockedhosts.blocked_site("https://de.indeed.com/viewjob?jk=abc"), "indeed")
        self.assertEqual(blockedhosts.blocked_site("https://notlinkedin.com/x"), "")
        self.assertEqual(blockedhosts.blocked_site("https://evil.example/linkedin.com/jobs/view/1"), "")
        self.assertEqual(blockedhosts.clean_link("https://jobs.example.org/a?utm_source=x&gh_jid=77&trk=y#frag"), "https://jobs.example.org/a?gh_jid=77")
        self.assertEqual(blockedhosts.clean_link("javascript:alert(1)"), "")
        self.assertEqual(blockedhosts.clean_link("data:text/html,x"), "")
        self.assertEqual(blockedhosts.clean_link("https://u:p@x.example/"), "")
        self.assertEqual(blockedhosts.clean_link("https://www.google.com/url?q=https%3A%2F%2Fa.example%2Fjobs%2F1%3Futm_source%3Dx&sa=D"), "https://a.example/jobs/1")
