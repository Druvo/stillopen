"""The person's own LinkedIn data export (Saved Jobs / Job Applications, or the whole zip). THE FIXTURES ARE REPRESENTATIVE of LinkedIn's CSV
layout, written for these tests, not captured from a real export (header names vary by export version, so the reader matches them loosely)."""
import io
import json
import zipfile

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, TestCase

from tracker.models import Application, Event
from tracker.services import linkedinexport as lx
from tracker.tests_api import BASE, job, person

SAVED = (
    "Saved Date,Job Url,Job Title,Company Name\n"
    '"10/22/25, 9:14 PM",https://www.linkedin.com/jobs/view/3812345678/?trackingId=abc&refId=x,Backend Engineer,Acme\n'
    "2025-10-20 08:00:00 UTC,https://www.linkedin.com/comm/jobs/view/3800000001?trk=eml,Data Engineer,Initech\n"
    ",,,\n"
    "10/19/25,javascript:alert(1),Evil Role,Evil Co\n"
    "10/18/25,https://www.linkedin.com/jobs/view/3800000002/,,Nameless\n"
)
APPLIED = (
    "Application Date,Contact Email,Contact Phone Number,Company Name,Job Title,Job Url,Resume Name,Question And Answers\n"
    '"10/23/25, 7:00 AM",secret.person@example.org,+1 555 010 9999,Globex,Platform Engineer,https://www.linkedin.com/jobs/view/3899999999/,My Resume 2025.pdf,"Why us? | I love SECRETANSWER"\n'
    "2025-10-21 10:00:00 UTC,secret.person@example.org,+1 555 010 9999,Acme,Backend Engineer,https://www.linkedin.com/jobs/view/3812345678/?trk=x,cv.pdf,\n"
)


def make_zip(files: dict[str, bytes | str], compression=zipfile.ZIP_DEFLATED) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression) as z:
        for name, data in files.items():
            z.writestr(name, data)
    return buf.getvalue()


EXPORT = {
    "Saved Jobs.csv": SAVED,
    "Job Applications.csv": APPLIED,
    "Profile.csv": "First Name,Last Name\nSecret,Person\n",
    "Connections.csv": "First Name,Email\nA,a@example.org\n",
    "Jobs/Job Applicant Saved Answers.csv": "Question,Answer\nQ,SECRETANSWER2\n",
}


class Reading(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")

    def test_dates_both_styles(self):
        self.assertEqual(lx.parse_date("10/22/25, 9:14 PM").isoformat(), "2025-10-22")
        self.assertEqual(lx.parse_date("22/10/2025").isoformat(), "2025-10-22")  # first number cannot be a month
        self.assertEqual(lx.parse_date("2025-10-21 10:00:00 UTC").isoformat(), "2025-10-21")
        self.assertIsNone(lx.parse_date("not a date"))

    def test_zip_preview_counts_per_file_and_ignores_the_rest(self):
        report = lx.read(self.a, make_zip(EXPORT), preview=True)
        by_kind = {f["kind"]: f for f in report["files"]}
        self.assertEqual(by_kind["applied"]["found"], 2)
        self.assertEqual(by_kind["applied"]["new"], 2)
        # saved: 2 good rows (one of them also applied -> a duplicate), 2 unreadable (bad link, no title); the blank row is not counted
        self.assertEqual((by_kind["saved"]["found"], by_kind["saved"]["new"], by_kind["saved"]["duplicates"], by_kind["saved"]["unreadable"]), (4, 1, 1, 2))
        self.assertEqual(report["ignored_files"], 3)
        self.assertEqual(report["will_add"], 3)
        self.assertFalse(Application.objects.filter(owner=self.a).exists())  # a preview adds nothing

    def test_real_import_statuses_dates_notes_and_clean_links(self):
        report = lx.read(self.a, make_zip(EXPORT), preview=False)
        self.assertEqual(report["added"], 3)
        got = {a.role: a for a in Application.objects.filter(owner=self.a)}
        applied = got["Platform Engineer"]
        self.assertEqual((applied.status.name, applied.applied_date.isoformat(), applied.applied_channel), ("Applied", "2025-10-23", "linkedin"))
        self.assertEqual(applied.url, "https://www.linkedin.com/jobs/view/3899999999/")
        self.assertEqual(got["Backend Engineer"].status.name, "Applied")  # applied wins over saved
        self.assertEqual(got["Data Engineer"].status.name, "Saved")
        self.assertEqual(got["Data Engineer"].url, "https://www.linkedin.com/jobs/view/3800000001/")
        text = Event.objects.get(application=applied).text
        self.assertEqual(text, "Imported from your LinkedIn data (application sent 2025-10-23)")

    def test_privacy_nothing_personal_is_kept_or_returned(self):
        reports = [lx.read(self.a, make_zip(EXPORT), preview=True), lx.read(self.a, make_zip(EXPORT), preview=False)]
        blob = json.dumps(reports, default=str)
        stored = " ".join(
            [str(v) for a in Application.objects.all() for v in a.__dict__.values()] + list(Event.objects.values_list("text", flat=True))
        )
        for secret in ("secret.person@example.org", "555 010", "SECRETANSWER", "Resume 2025", "cv.pdf", "Secret", "a@example.org"):
            self.assertNotIn(secret, blob)
            self.assertNotIn(secret, stored)

    def test_a_single_csv_works_and_the_wrong_csv_is_refused(self):
        report = lx.read(self.a, APPLIED.encode(), preview=True)
        self.assertEqual(report["will_add"], 2)
        with self.assertRaises(Exception):
            lx.read(self.a, b"a,b\n1,2\n", preview=True)

    def test_dedupe_against_the_tracker_by_link_and_by_company_and_role(self):
        job(self.a, company="Someone", role="Else", url="https://www.linkedin.com/jobs/view/3812345678/")
        job(self.a, company="Globex Inc", role="Senior Platform Engineer")
        report = lx.read(self.a, make_zip(EXPORT), preview=False)
        self.assertEqual(report["added"], 1)  # only Data Engineer is new
        self.assertEqual(report["skipped_count"], 3)

    def test_job_limit(self):
        with self.settings(STILLOPEN_MAX_APPLICATIONS=2):
            report = lx.read(self.a, make_zip(EXPORT), preview=False)
        self.assertEqual(report["added"], 2)
        self.assertIn("limit of 2", report["stopped"])

    def test_another_person_is_untouched(self):
        job(self.b, company="Globex", role="Platform Engineer")
        report = lx.read(self.a, make_zip(EXPORT), preview=True)
        self.assertEqual(report["will_add"], 3)


class ZipSafety(SimpleTestCase):
    def refused(self, raw, fragment=""):
        with self.assertRaises(lx.ImportProblem) as caught:
            lx.read(None, raw, preview=True)
        self.assertIn(fragment, str(caught.exception))

    def test_not_a_zip(self):
        self.refused(b"PK\x03\x04 broken", "could not open")

    def test_wrong_entries_only(self):
        self.refused(make_zip({"Profile.csv": "a,b\n", "readme.txt": "x"}), "Saved Jobs.csv")

    def test_path_tricks(self):
        for name in ("../Saved Jobs.csv", "/etc/Saved Jobs.csv", "a/../../Saved Jobs.csv", "C:/x/Saved Jobs.csv"):
            self.refused(make_zip({name: SAVED}), "file names we do not trust")

    def test_oversize_entry_and_bomb(self):
        self.refused(make_zip({"Saved Jobs.csv": b"a" * (lx.MAX_ENTRY + 1)}), "far bigger")
        self.refused(make_zip({"Saved Jobs.csv": b"a" * (3 * 1024 * 1024)}), "far bigger")  # under the cap but compresses 1000:1

    def test_oversize_zip(self):
        self.refused(b"PK\x03\x04" + b"0" * (lx.MAX_ZIP + 1), "25 MB")

    def test_too_many_entries(self):
        files = {f"f{n}.txt": "x" for n in range(lx.MAX_MEMBERS + 1)}
        self.refused(make_zip(files, compression=zipfile.ZIP_STORED), "too many files")

    def test_nested_zip_is_ignored_not_opened(self):
        inner = make_zip({"Saved Jobs.csv": SAVED})
        self.refused(make_zip({"inner.zip": inner}), "Saved Jobs.csv")


class Api(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        self.client.force_login(self.a)

    def upload(self, name, data, preview=True):
        return self.client.post(f"{BASE}/jobs/import" + ("?preview=1" if preview else ""), {"file": SimpleUploadedFile(name, data)})

    def test_zip_through_the_existing_route(self):
        r = self.upload("linkedin-data.zip", make_zip(EXPORT))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["source"], "linkedin")
        self.assertEqual(Application.objects.filter(owner=self.a).count(), 0)
        r = self.upload("linkedin-data.zip", make_zip(EXPORT), preview=False)
        self.assertEqual(r.json()["added"], 3)
        self.assertNotIn("secret.person", r.content.decode())
        self.assertEqual(Application.objects.filter(owner=self.b).count(), 0)

    def test_unsafe_zip_is_a_plain_400(self):
        r = self.upload("x.zip", make_zip({"../Saved Jobs.csv": SAVED}))
        self.assertEqual(r.status_code, 400)
        self.assertIn("do not trust", r.json()["error"])

    def test_big_non_linkedin_csv_still_hits_the_one_megabyte_rule(self):
        r = self.upload("big.csv", b"company,role\n" + b"Acme,Dev\n" * 200000)
        self.assertEqual(r.status_code, 400)
        self.assertIn("1 MB", r.json()["error"])

    def test_plain_spreadsheet_import_is_unchanged(self):
        r = self.upload("jobs.csv", b"Company,Role\nAcme,Dev\n")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("source", r.json())
