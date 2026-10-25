"""Reading a person's own job-alert emails. THE FIXTURES BELOW ARE REPRESENTATIVE LAYOUTS WRITTEN FOR THESE TESTS, not captured from live mail:
they follow the usual shape of each service's alert (title link, company, place, pay, redirect and tracking links), and a real alert may differ."""
from email.message import EmailMessage

from django.core.cache import cache
from django.test import SimpleTestCase, TestCase

from tracker.models import Application, Event
from tracker.services import emailimport as ei
from tracker.tests_api import job, person

LINKEDIN_HTML = """<html><head><style>.x{color:red}</style><script>alert('x')</script></head><body>
<div style="display:none">Preheader text that must not become a job</div>
<table><tr><td><h2>Your job alert for software engineer in Berlin</h2></td></tr>
<tr><td><a href="https://www.linkedin.com/comm/jobs/view/3812345678/?trackingId=abc%3D%3D&refId=r1&midToken=m&midSig=s&trk=eml-jobalert&lipi=urn%3Ali%3Apage"><img src="logo.png"></a></td>
<td><a href="https://www.linkedin.com/comm/jobs/view/3812345678/?trackingId=abc%3D%3D&refId=r1&trk=eml-jobalert"><span>Senior Software Engineer</span></a>
<p>Acme Robotics</p><p>Berlin, Berlin, Germany</p><p>Actively recruiting</p></td></tr>
<tr><td><a href="https://www.linkedin.com/comm/jobs/view/3899999999/?trackingId=zzz&eid=e">Backend Developer (with verification)</a>
<p>Globex GmbH &middot; Hamburg, Germany (Hybrid)</p></td></tr>
<tr><td><a href="https://www.linkedin.com/comm/jobs/search?keywords=engineer&trk=see-all">See all jobs</a></td></tr>
<tr><td><a href="https://www.linkedin.com/e/v2?e=unsub&t=unsubscribe">Unsubscribe</a> <a href="https://www.linkedin.com/help/linkedin">Help</a>
<a href="javascript:alert(1)">Evil</a> <a href="data:text/html,hi">Data</a></td></tr></table></body></html>"""

LINKEDIN_TEXT = """Your job alert for software engineer in Berlin
2 new jobs

Senior Software Engineer
Acme Robotics
Berlin, Germany
View job: https://www.linkedin.com/comm/jobs/view/3812345678?trackingId=abc&refId=r1&lipi=zzz

Data Engineer
Initech
Remote
View job: https://www.linkedin.com/comm/jobs/view/3800000001?trackingId=q

Unsubscribe: https://www.linkedin.com/e/v2?e=unsub
"""

INDEED_HTML = """<html><body><h1>New jobs for developer in London</h1>
<table>
<tr><td><h2><a href="https://uk.indeed.com/rc/clk?jk=0123456789abcdef&fccid=1&vjs=3&tk=1abc">Python Developer</a></h2>
<div>Northwind Traders - London</div><div>&pound;55,000 - &pound;65,000 a year</div><div><a href="https://uk.indeed.com/rc/clk?jk=0123456789abcdef&fccid=1">View job</a></div></td></tr>
<tr><td><h2><a href="https://uk.indeed.com/viewjob?jk=fedcba9876543210&from=ja">Support Engineer</a></h2>
<div>Contoso Ltd - Manchester M1</div></td></tr>
<tr><td><a href="https://www.indeed.com/account/settings">Manage your job alerts</a> <a href="https://uk.indeed.com/privacy">Privacy</a></td></tr>
</table></body></html>"""

GLASSDOOR_HTML = """<html><body><p>Jobs for you</p>
<div class="job"><a href="https://www.glassdoor.com/partner/jobListing.htm?pos=101&ao=1136043&jobListingId=1009876543&s=58&guid=0000">Product Designer</a>
<div>Fabrikam</div><div>Dubai, United Arab Emirates</div><div>$90K - $110K (Employer est.)</div></div>
<div class="job"><a href="https://www.glassdoor.com/job-listing/data-analyst-wingtip-JV_IC1.htm?jl=1009876544&utm_source=x">Data Analyst</a>
<div>Wingtip Toys</div><div>Remote</div></div>
<a href="https://www.glassdoor.com/member/home/index.htm">Settings</a></body></html>"""

GOOGLE_HTML = """<html><body><div><a href="https://www.google.com/url?q=https%3A%2F%2Fcareers.example-corp.com%2Fjobs%2F8841%3Futm_source%3Dgoogle%26gh_jid%3D8841&sa=D&ust=1">Site Reliability Engineer</a>
<div>Example Corp</div><div>Kuala Lumpur, Malaysia</div></div>
<div><a href="https://www.google.com/url?q=https://jobs.lever.co/acme/abc-123?lever-source=google&sa=D">Platform Engineer</a><div>Acme</div><div>Remote</div></div></body></html>"""

GENERIC_HTML = """<ul>
<li><a href="https://careers.stark.example/openings/771">Mechanical Engineer</a> <br>Stark Industries<br>Dhaka, Bangladesh</li>
<li><a href="https://careers.stark.example/openings/772">Electrical Engineer at Stark Industries</a></li>
<li><a href="https://twitter.com/stark">Follow us</a></li>
<li><a href="https://careers.stark.example/openings/771">Mechanical Engineer</a></li>
</ul>"""

PLAIN_FORWARD = """---------- Forwarded message ---------
From: Jobs <jobs@example.com>
Subject: jobs for you

Frontend Developer
Pied Piper
Palo Alto, CA
https://jobs.example.org/apply/55?utm_source=mail&utm_campaign=x

Mobile Developer
Hooli
Remote
https://jobs.example.org/apply/56?trk=abc
"""


def titles(found):
    return [r["title"] for r in found["rows"]]


class Layouts(SimpleTestCase):
    def test_linkedin_html(self):
        rows = ei.read(html=LINKEDIN_HTML)["rows"]
        self.assertEqual([r["title"] for r in rows], ["Senior Software Engineer", "Backend Developer"])
        first = rows[0]
        self.assertEqual(first["url"], "https://www.linkedin.com/jobs/view/3812345678/")
        self.assertEqual((first["company"], first["location"]), ("Acme Robotics", "Berlin, Berlin, Germany"))
        self.assertEqual((rows[1]["company"], rows[1]["location"]), ("Globex GmbH", "Hamburg, Germany (Hybrid)"))
        self.assertEqual(rows[1]["url"], "https://www.linkedin.com/jobs/view/3899999999/")
        blob = str(rows)
        for bad in ("Preheader", "alert(", "unsubscribe", "trackingId", "javascript:", "data:"):
            self.assertNotIn(bad, blob)

    def test_linkedin_plain_text(self):
        rows = ei.read(text=LINKEDIN_TEXT)["rows"]
        self.assertEqual(titles({"rows": rows}), ["Senior Software Engineer", "Data Engineer"])
        self.assertEqual(rows[0]["company"], "Acme Robotics")
        self.assertEqual(rows[0]["location"], "Berlin, Germany")
        self.assertEqual(rows[1]["url"], "https://www.linkedin.com/jobs/view/3800000001/")

    def test_indeed(self):
        rows = ei.read(html=INDEED_HTML)["rows"]
        self.assertEqual(titles({"rows": rows}), ["Python Developer", "Support Engineer"])
        self.assertEqual((rows[0]["company"], rows[0]["location"]), ("Northwind Traders", "London"))
        self.assertIn("55,000", rows[0]["salary"])
        self.assertEqual(rows[0]["url"], "https://uk.indeed.com/viewjob?jk=0123456789abcdef")
        self.assertEqual(rows[1]["company"], "Contoso Ltd")

    def test_glassdoor(self):
        rows = ei.read(html=GLASSDOOR_HTML)["rows"]
        self.assertEqual(titles({"rows": rows}), ["Product Designer", "Data Analyst"])
        self.assertEqual((rows[0]["company"], rows[0]["location"]), ("Fabrikam", "Dubai, United Arab Emirates"))
        self.assertIn("90K", rows[0]["salary"])
        self.assertEqual(rows[0]["url"], "https://www.glassdoor.com/partner/jobListing.htm?jobListingId=1009876543")
        self.assertNotIn("guid", rows[0]["url"])

    def test_google_redirects_are_unwrapped_as_text(self):
        rows = ei.read(html=GOOGLE_HTML)["rows"]
        self.assertEqual(rows[0]["url"], "https://careers.example-corp.com/jobs/8841?gh_jid=8841")
        self.assertEqual(rows[1]["url"], "https://jobs.lever.co/acme/abc-123?lever-source=google")
        self.assertEqual((rows[0]["company"], rows[0]["location"]), ("Example Corp", "Kuala Lumpur, Malaysia"))

    def test_generic_list(self):
        rows = ei.read(html=GENERIC_HTML)["rows"]
        self.assertEqual(len(rows), 2)  # the repeated link is one job, Twitter is not a job
        self.assertEqual((rows[0]["company"], rows[0]["location"]), ("Stark Industries", "Dhaka, Bangladesh"))
        self.assertEqual((rows[1]["title"], rows[1]["company"]), ("Electrical Engineer", "Stark Industries"))

    def test_plain_forward_title_company_location_url(self):
        rows = ei.read(text=PLAIN_FORWARD)["rows"]
        self.assertEqual(titles({"rows": rows}), ["Frontend Developer", "Mobile Developer"])
        self.assertEqual((rows[0]["company"], rows[0]["location"], rows[0]["url"]), ("Pied Piper", "Palo Alto, CA", "https://jobs.example.org/apply/55"))

    def test_eml_file_with_html_part(self):
        msg = EmailMessage()
        msg["Subject"] = "Your job alert"
        msg.set_content("plain version without links")
        msg.add_alternative(INDEED_HTML, subtype="html")
        found = ei.read(eml=bytes(msg))
        self.assertEqual(len(found["rows"]), 2)
        self.assertEqual(found["subject"], "Your job alert")

    def test_a_paste_without_links_still_offers_the_jobs_without_a_link(self):
        found = ei.read(text="Your job alert\n\nSenior Software Engineer\nAcme Robotics\nBerlin, Germany\nView job\n\nData Engineer\nInitech\nRemote\nView job\n")
        self.assertEqual(titles(found), ["Senior Software Engineer", "Data Engineer"])
        self.assertEqual(found["rows"][0]["url"], "")
        self.assertTrue(any(".eml" in p for p in found["problems"]))


class Cleaning(SimpleTestCase):
    def test_hostile_links_never_become_rows(self):
        html = '<a href="javascript:alert(1)">Fake Job Engineer</a><a href="data:text/html;base64,AAAA">Another Job</a><a href="ftp://x/job/1">Ftp Job</a><a href="https://user:pw@evil.example/jobs/1">Cred Job</a>'
        found = ei.read(html=html)
        self.assertEqual(found["rows"], [])
        self.assertTrue(found["problems"])

    def test_scripts_are_not_run_or_read(self):
        found = ei.read(html='<script>var x = "<a href=\'https://evil.example/jobs/1\'>Evil Job</a>"</script><a href="https://ok.example/jobs/2">Real Job Title</a>')
        self.assertEqual(titles(found), ["Real Job Title"])

    def test_markup_in_text_stays_text(self):
        found = ei.read(html='<a href="https://ok.example/jobs/2">&lt;img src=x onerror=alert(1)&gt; Engineer</a><p>Acme</p>')
        self.assertEqual(found["rows"][0]["title"], "<img src=x onerror=alert(1)> Engineer")  # shown by React as plain text

    def test_empty_huge_and_garbage(self):
        for empty in ("", "   \n  "):
            with self.assertRaises(ei.EmailProblem):
                ei.read(text=empty)
        with self.assertRaises(ei.EmailProblem):
            ei.read(text="x" * (ei.MAX_BYTES + 1))
        with self.assertRaises(ei.EmailProblem):
            ei.read(eml=b"x" * (ei.MAX_BYTES + 1))
        self.assertEqual(ei.read(text="\x00\x01\x02 binary \xff junk")["rows"], [])
        self.assertEqual(ei.read(text="<<<<>>>>" * 1000)["rows"], [])

    def test_non_english_input(self):
        found = ei.read(text="Softwareentwickler (m/w/d)\nMüller Technik GmbH\nMünchen, Deutschland\nhttps://karriere.example.de/stellen/42?utm_source=x\n")
        self.assertEqual(found["rows"][0]["title"], "Softwareentwickler (m/w/d)")
        self.assertEqual(found["rows"][0]["company"], "Müller Technik GmbH")
        arabic = ei.read(text="مهندس برمجيات\nشركة الأمل\nدبي\nhttps://jobs.example.ae/job/9\n")
        self.assertEqual(arabic["rows"][0]["title"], "مهندس برمجيات")

    def test_more_than_the_cap_is_cut_with_a_message(self):
        text = "".join(f"Role number {n}\nCo {n}\nhttps://jobs.example.org/apply/{n}\n\n" for n in range(ei.MAX_JOBS + 20))
        found = ei.read(text=text)
        self.assertEqual(len(found["rows"]), ei.MAX_JOBS)
        self.assertTrue(any("more than" in p for p in found["problems"]))

    def test_every_row_is_bounded(self):
        found = ei.read(text="T" * 150 + "\n" + "C" * 150 + "\n" + "L" * 150 + "\nhttps://jobs.example.org/apply/1\n")
        row = found["rows"][0]
        self.assertLessEqual(len(row["title"]), 200)
        self.assertLessEqual(len(row["company"]), 160)
        self.assertLessEqual(len(row["location"]), 160)


class Adding(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        self.found = ei.read(html=LINKEDIN_HTML)

    def test_preview_flags_a_job_already_tracked(self):
        job(self.a, company="Acme Robotics", role="Senior Software Engineer")
        out = ei.check(self.a, self.found)
        self.assertEqual(out["found"], 2)
        self.assertEqual(out["will_add"], 1)
        self.assertEqual(out["rows"][0]["duplicate"]["company"], "Acme Robotics")
        self.assertFalse(out["rows"][0]["importable"])
        self.assertIsNone(out["rows"][1]["duplicate"])

    def test_preview_flags_a_link_already_tracked(self):
        job(self.a, company="Other", role="Other", url="https://www.linkedin.com/jobs/view/3899999999/")
        self.assertIsNotNone(ei.check(self.a, self.found)["rows"][1]["duplicate"])

    def test_add_only_the_ticked_rows_as_saved_with_a_note(self):
        out = ei.add(self.a, self.found, [1])
        self.assertEqual(out["added"], 1)
        app = Application.objects.get(owner=self.a)
        self.assertEqual((app.role, app.company, app.status.name), ("Backend Developer", "Globex GmbH", "Saved"))
        self.assertEqual(app.url, "https://www.linkedin.com/jobs/view/3899999999/")
        self.assertEqual(app.country, "DE")
        self.assertEqual(app.arrangement, "hybrid")
        self.assertEqual(app.details_source, "detected")
        self.assertEqual(list(Event.objects.filter(application=app).values_list("text", flat=True)), [ei.NOTE])

    def test_add_all_skips_duplicates_and_counts_them(self):
        job(self.a, company="Globex", role="Backend Developer")
        out = ei.add(self.a, self.found, None)
        self.assertEqual((out["added"], out["skipped_count"]), (1, 1))
        again = ei.add(self.a, self.found, None)
        self.assertEqual((again["added"], again["skipped_count"]), (0, 2))

    def test_job_limit_stops_with_the_plain_message(self):
        with self.settings(STILLOPEN_MAX_APPLICATIONS=1):
            job(self.a, company="Existing", role="Thing")
            out = ei.add(self.a, self.found, None)
        self.assertEqual(out["added"], 0)
        self.assertIn("limit of 1 tracked jobs", out["stopped"])

    def test_missing_company_is_saved_as_not_stated(self):
        found = ei.read(text="Lonely Title\nhttps://jobs.example.org/apply/1\n")
        self.assertEqual(found["rows"][0]["company"], "")
        ei.add(self.a, found, None)
        self.assertEqual(Application.objects.get(owner=self.a).company, "Company not stated")

    def test_nothing_touches_another_person(self):
        job(self.b, company="Acme Robotics", role="Senior Software Engineer")
        out = ei.check(self.a, self.found)
        self.assertEqual(out["will_add"], 2)  # bob's job is not alice's duplicate
        ei.add(self.a, self.found, None)
        self.assertEqual(Application.objects.filter(owner=self.b).count(), 1)


# Representative text a person copies by hand from LinkedIn's results page and notifications (no links survive a copy), written for these tests.
RESULTS_TEXT = """Senior Software Engineer
Senior Software Engineer with verification
Acme Robotics
Berlin, Germany (Hybrid)
Promoted
Easy Apply
Data Engineer
Initech
Remote
Actively recruiting
12 applicants
2 days ago
Product Designer
Fabrikam
New York, NY
Be an early applicant
5 hours ago
"""
NOTIFICATIONS_TEXT = """New jobs for you: Backend Developer at Globex GmbH
Job alert: Site Reliability Engineer at Example Corp.
3 new jobs in Hamburg
"""


class VisibleText(TestCase):
    def setUp(self):
        cache.clear()
        self.a = person("alice")

    def test_results_list_with_noise_is_split_into_jobs(self):
        found = ei.read(text=RESULTS_TEXT)
        self.assertEqual(titles(found), ["Senior Software Engineer", "Data Engineer", "Product Designer"])
        self.assertEqual((found["rows"][0]["company"], found["rows"][0]["location"]), ("Acme Robotics", "Berlin, Germany (Hybrid)"))
        self.assertEqual((found["rows"][2]["company"], found["rows"][2]["location"]), ("Fabrikam", "New York, NY"))
        self.assertTrue(all(r["url"] == "" for r in found["rows"]))

    def test_notification_sentences(self):
        found = ei.read(text=NOTIFICATIONS_TEXT)
        self.assertEqual([(r["title"], r["company"]) for r in found["rows"]], [("Backend Developer", "Globex GmbH"), ("Site Reliability Engineer", "Example Corp")])

    def test_preview_marks_no_link_and_flags_duplicates_by_company_and_role(self):
        job(self.a, company="Initech", role="Data Engineer")
        out = ei.check(self.a, ei.read(text=RESULTS_TEXT))
        self.assertIn("No link: you will need to open it on LinkedIn to apply.", out["rows"][0]["problems"])
        self.assertIsNotNone(out["rows"][1]["duplicate"])
        self.assertEqual(out["will_add"], 2)

    def test_added_without_a_posting_link_but_with_a_search_link_in_the_notes(self):
        ei.add(self.a, ei.read(text=RESULTS_TEXT), [0])
        app = Application.objects.get(owner=self.a)
        self.assertEqual(app.url, "")
        self.assertEqual(app.notes, "Find it on LinkedIn: https://www.linkedin.com/jobs/search/?keywords=Senior+Software+Engineer+Acme+Robotics")
        self.assertEqual(app.status.name, "Saved")

    def test_noise_only_and_empty(self):
        self.assertEqual(ei.read(text="Promoted\nEasy Apply\n12 applicants\n2 days ago\nViewed\n")["rows"], [])
        with self.assertRaises(ei.EmailProblem):
            ei.read(text="")
