"""Looking after tracked jobs through the JSON API: remove, bulk, undo, history, spreadsheet in and out, duplicates, replies, source health.

Every call must stay inside the signed-in person's own rows: another person's id is a 404 and nothing is changed."""
import csv
import io
import json
from datetime import date, timedelta
from unittest import mock

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone

from tracker.models import (
    Application, CoverLetter, CVVersion, Event, Interview, JobSource, Offer, Posting, ScanLogEntry, ScanRun, Status,
)
from tracker.prep_models import PrepPlan
from tracker.services import board, careerops, stats
from tracker.tests import close_quietly
from tracker.tests_api import BASE, job, person


class Base(TestCase):
    def setUp(self):
        cache.clear()
        self.a, self.b = person("alice"), person("bob")
        self.client.force_login(self.a)
        self.applied = Status.objects.get(name="Applied")
        self.evaluated = Status.objects.get(name="Evaluated")

    def post(self, path, body=None):
        return self.client.post(f"{BASE}{path}", data=json.dumps(body if body is not None else {}), content_type="application/json")

    def patch(self, path, body):
        return self.client.patch(f"{BASE}{path}", data=json.dumps(body), content_type="application/json")


class StatusNames(Base):
    def test_the_two_confusing_names_are_plain_now(self):
        names = set(Status.objects.values_list("name", flat=True))
        self.assertIn("Not for me", names)
        self.assertIn("Skipped", names)
        self.assertNotIn("Discarded", names)
        self.assertNotIn("SKIP", names)

    def test_old_names_still_find_the_new_status(self):
        self.assertEqual(board.find_status("Discarded").name, "Not for me")
        self.assertEqual(board.find_status("skip").name, "Skipped")
        self.assertEqual(board.find_status("evaluated").name, "Evaluated")
        self.assertIsNone(board.find_status("Nonsense"))

    def test_the_career_ops_import_maps_old_names_to_the_new_status(self):
        self.assertEqual(careerops._status("Discarded").name, "Not for me")
        self.assertEqual(careerops._status("SKIP").name, "Skipped")
        self.assertFalse(Status.objects.filter(name__in=["Discarded", "SKIP"]).exists())

    def test_the_dashboard_has_a_friendly_label_and_keeps_the_stored_name(self):
        data = self.client.get(f"{BASE}/dashboard").json()
        by_name = {s["name"]: s for s in data["statuses"]}
        self.assertEqual(by_name["Evaluated"]["label"], "Checked")
        self.assertEqual(by_name["Applied"]["label"], "Applied")
        self.assertEqual(by_name["Not for me"]["label"], "Not for me")


class RemoveJob(Base):
    def make(self, owner=None):
        app = job(owner or self.a)
        CVVersion.objects.create(owner=app.owner, application=app, kind="tailored", content="cv")
        CoverLetter.objects.create(owner=app.owner, application=app, content="hello")
        Interview.objects.create(owner=app.owner, application=app, scheduled_at=timezone.now() + timedelta(days=2))
        Interview.objects.create(owner=app.owner, application=app, scheduled_at=timezone.now() + timedelta(days=3))
        Event.objects.create(application=app, text="Added")
        return app

    def test_the_preview_says_exactly_what_goes(self):
        app = self.make()
        data = self.client.get(f"{BASE}/jobs/{app.pk}/remove-preview").json()
        self.assertEqual(data["counts"]["interviews"], 2)
        self.assertEqual(data["counts"]["tailored_cvs"], 1)
        self.assertEqual(data["text"], "This also removes its tailored CV, its cover letter, 2 interviews and its history.")
        self.assertTrue(Application.objects.filter(pk=app.pk).exists())

    def test_nothing_attached_says_so(self):
        app = job(self.a)
        self.assertEqual(self.client.get(f"{BASE}/jobs/{app.pk}/remove-preview").json()["text"], "Nothing else is attached to it.")

    def test_removing_takes_the_job_and_what_hangs_off_it(self):
        app = self.make()
        plan = PrepPlan.objects.create(owner=self.a, application=app, title="Plan", status="active")
        r = self.client.delete(f"{BASE}/jobs/{app.pk}")
        self.assertEqual(r.status_code, 200)
        self.assertFalse(Application.objects.filter(pk=app.pk).exists())
        self.assertFalse(Interview.objects.filter(application_id=app.pk).exists())
        self.assertFalse(CVVersion.objects.filter(application_id=app.pk).exists())
        self.assertFalse(Event.objects.filter(application_id=app.pk).exists())
        plan.refresh_from_db()  # the prep plan stays, no longer linked
        self.assertIsNone(plan.application_id)

    def test_a_job_whose_sent_cv_is_its_own_tailored_cv_can_still_be_removed(self):
        app = job(self.a)
        cv = CVVersion.objects.create(owner=self.a, application=app, kind="tailored", content="cv")
        app.applied_cv = cv
        app.save()
        self.assertEqual(self.client.delete(f"{BASE}/jobs/{app.pk}").status_code, 200)
        self.assertFalse(CVVersion.objects.filter(pk=cv.pk).exists())

    def test_someone_elses_job_is_a_404_and_stays(self):
        theirs = self.make(self.b)
        self.assertEqual(self.client.delete(f"{BASE}/jobs/{theirs.pk}").status_code, 404)
        self.assertEqual(self.client.get(f"{BASE}/jobs/{theirs.pk}/remove-preview").status_code, 404)
        self.assertTrue(Application.objects.filter(pk=theirs.pk).exists())
        self.assertEqual(Interview.objects.filter(application=theirs).count(), 2)


class Bulk(Base):
    def test_remove_several(self):
        a1, a2, keep = job(self.a), job(self.a), job(self.a)
        r = self.post("/jobs/bulk", {"ids": [a1.pk, a2.pk], "action": "remove"})
        self.assertEqual(r.json(), {"ok": True, "removed": 2})
        self.assertEqual(list(Application.objects.values_list("pk", flat=True)), [keep.pk])

    def test_a_foreign_id_makes_the_whole_call_a_404_and_changes_nothing(self):
        mine, theirs = job(self.a), job(self.b)
        for body in ({"ids": [mine.pk, theirs.pk], "action": "remove"}, {"ids": [mine.pk, theirs.pk], "action": "status", "status_id": self.applied.pk}, {"ids": [mine.pk, 999999], "action": "remove"}):
            self.assertEqual(self.post("/jobs/bulk", body).status_code, 404)
        self.assertEqual(Application.objects.count(), 2)
        mine.refresh_from_db()
        theirs.refresh_from_db()
        self.assertEqual((mine.status_id, theirs.status_id), (self.evaluated.pk, self.evaluated.pk))
        self.assertFalse(Event.objects.exists())

    def test_move_several_to_a_status(self):
        a1, a2 = job(self.a), job(self.a)
        not_for_me = Status.objects.get(name="Not for me")
        r = self.post("/jobs/bulk", {"ids": [a1.pk, a2.pk], "action": "status", "status_id": not_for_me.pk}).json()
        self.assertEqual(sorted(r["changed"]), sorted([a1.pk, a2.pk]))
        self.assertEqual(r["status"]["label"], "Not for me")
        self.assertEqual(Application.objects.filter(status=not_for_me).count(), 2)

    def test_validation(self):
        mine = job(self.a)
        self.assertEqual(self.post("/jobs/bulk", {"ids": [], "action": "remove"}).status_code, 400)
        self.assertEqual(self.post("/jobs/bulk", {"ids": [mine.pk], "action": "explode"}).status_code, 400)
        self.assertEqual(self.post("/jobs/bulk", {"ids": [mine.pk], "action": "status"}).status_code, 400)
        self.assertEqual(self.post("/jobs/bulk", {"ids": [mine.pk], "action": "status", "status_id": 99999}).status_code, 404)
        self.assertEqual(self.post("/jobs/bulk", {"ids": list(range(1, 502)), "action": "remove"}).status_code, 400)
        self.assertEqual(self.client.post(f"{BASE}/jobs/bulk", data="[]", content_type="application/json").status_code, 422)
        self.assertTrue(Application.objects.filter(pk=mine.pk).exists())

    def test_the_preview_adds_the_jobs_up(self):
        a1, a2 = job(self.a), job(self.a)
        Interview.objects.create(owner=self.a, application=a1, scheduled_at=timezone.now())
        Interview.objects.create(owner=self.a, application=a2, scheduled_at=timezone.now())
        data = self.post("/jobs/bulk", {"ids": [a1.pk, a2.pk], "action": "preview"}).json()
        self.assertEqual(data["counts"]["interviews"], 2)
        self.assertIn("2 interviews", data["text"])
        self.assertEqual(Application.objects.count(), 2)


class UndoAMove(Base):
    def test_undo_puts_back_the_status_the_applied_date_the_follow_up_and_the_timeline(self):
        app = job(self.a)
        self.assertEqual(self.patch(f"/jobs/{app.pk}/status", {"status": self.applied.pk}).status_code, 200)
        app.refresh_from_db()
        self.assertIsNotNone(app.applied_date)
        self.assertIsNotNone(app.follow_up_date)
        self.assertEqual(app.events.count(), 1)
        r = self.post(f"/jobs/{app.pk}/status/undo")
        self.assertEqual(r.status_code, 200)
        app.refresh_from_db()
        self.assertEqual(app.status_id, self.evaluated.pk)
        self.assertIsNone(app.applied_date)
        self.assertIsNone(app.follow_up_date)
        self.assertEqual(app.events.count(), 0)
        self.assertEqual(r.json()["status"]["name"], "Evaluated")

    def test_it_only_works_for_a_few_minutes(self):
        app = job(self.a)
        self.patch(f"/jobs/{app.pk}/status", {"status": self.applied.pk})
        Event.objects.filter(application=app).update(happened_at=timezone.now() - timedelta(minutes=board.UNDO_MINUTES + 1))
        self.assertEqual(self.post(f"/jobs/{app.pk}/status/undo").status_code, 400)
        app.refresh_from_db()
        self.assertEqual(app.status_id, self.applied.pk)

    def test_it_does_not_undo_past_a_later_move(self):
        app = job(self.a)
        self.patch(f"/jobs/{app.pk}/status", {"status": self.applied.pk})
        app.refresh_from_db()
        app.status = Status.objects.get(name="Interview")  # moved some other way since (not through the status call)
        app.save()
        self.assertEqual(self.post(f"/jobs/{app.pk}/status/undo").status_code, 400)

    def test_nothing_to_undo(self):
        self.assertEqual(self.post(f"/jobs/{job(self.a).pk}/status/undo").status_code, 400)

    def test_someone_elses_job_is_a_404(self):
        theirs = job(self.b)
        self.client.force_login(self.b)
        self.patch(f"/jobs/{theirs.pk}/status", {"status": self.applied.pk})
        self.client.force_login(self.a)
        self.assertEqual(self.post(f"/jobs/{theirs.pk}/status/undo").status_code, 404)
        theirs.refresh_from_db()
        self.assertEqual(theirs.status_id, self.applied.pk)

    def test_bulk_undo(self):
        a1, a2 = job(self.a), job(self.a)
        self.post("/jobs/bulk", {"ids": [a1.pk, a2.pk], "action": "status", "status_id": self.applied.pk})
        r = self.post("/jobs/bulk", {"ids": [a1.pk, a2.pk], "action": "undo"}).json()
        self.assertEqual(sorted(r["undone"]), sorted([a1.pk, a2.pk]))
        self.assertEqual(Application.objects.filter(status=self.evaluated).count(), 2)
        self.assertFalse(Event.objects.exists())


class FollowUpDefault(Base):
    def test_a_move_to_applied_sets_the_default_follow_up_and_says_so(self):
        app = job(self.a)
        self.patch(f"/jobs/{app.pk}/status", {"status": self.applied.pk})
        app.refresh_from_db()
        self.assertEqual(app.follow_up_date, app.applied_date + timedelta(days=7))
        self.assertIn("Follow up on", app.events.get().text)

    def test_an_existing_follow_up_is_kept(self):
        app = job(self.a, follow_up_date=date(2030, 1, 1))
        self.patch(f"/jobs/{app.pk}/status", {"status": self.applied.pk})
        app.refresh_from_db()
        self.assertEqual(app.follow_up_date, date(2030, 1, 1))

    def test_endings_and_later_steps_do_not_get_one(self):
        rejected = job(self.a)
        self.patch(f"/jobs/{rejected.pk}/status", {"status": Status.objects.get(name="Rejected").pk})
        rejected.refresh_from_db()
        self.assertIsNone(rejected.follow_up_date)
        step = job(self.a, status=self.applied, applied_date=date(2026, 10, 1))
        self.patch(f"/jobs/{step.pk}/status", {"status": Status.objects.get(name="Interview").pk})
        step.refresh_from_db()
        self.assertIsNone(step.follow_up_date)

    def test_the_apply_assistant_still_decides_its_own(self):
        app = job(self.a)
        r = self.post(f"/jobs/{app.pk}/applied", {"days": 3})
        self.assertEqual(r.status_code, 200)
        app.refresh_from_db()
        self.assertEqual(app.follow_up_date, app.applied_date + timedelta(days=3))


class History(Base):
    def test_newest_first_with_plain_kinds(self):
        app = job(self.a)
        old = Event.objects.create(application=app, kind="note", text="Added")
        Event.objects.filter(pk=old.pk).update(happened_at=timezone.now() - timedelta(days=3))
        Event.objects.create(application=app, kind="applied", text="Applied. Follow up on 01 Nov 2026.")
        data = self.client.get(f"{BASE}/jobs/{app.pk}/history").json()
        self.assertEqual([i["text"] for i in data["items"]], ["Applied. Follow up on 01 Nov 2026.", "Added"])
        self.assertEqual(data["items"][0]["kind_label"], "Applied")
        self.assertFalse(data["capped"])
        self.assertRegex(data["items"][0]["date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_empty_and_capped(self):
        app = job(self.a)
        self.assertEqual(self.client.get(f"{BASE}/jobs/{app.pk}/history").json(), {"items": [], "capped": False})
        Event.objects.bulk_create([Event(application=app, text=f"n{i}") for i in range(130)])
        data = self.client.get(f"{BASE}/jobs/{app.pk}/history").json()
        self.assertEqual(len(data["items"]), 100)
        self.assertTrue(data["capped"])

    def test_someone_elses_is_a_404(self):
        theirs = job(self.b)
        Event.objects.create(application=theirs, text="secret")
        r = self.client.get(f"{BASE}/jobs/{theirs.pk}/history")
        self.assertEqual(r.status_code, 404)
        self.assertNotIn("secret", r.content.decode())


class SuggestStatus(Base):
    def interview_body(self, app):
        return {"application": app.pk, "scheduled_at": (timezone.now() + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M"), "kind": "video"}

    def test_an_interview_for_a_job_that_is_not_there_yet_suggests_the_move(self):
        app = job(self.a)
        r = self.post("/interviews", self.interview_body(app)).json()
        self.assertEqual(r["suggest_status"]["name"], "Interview")
        app.refresh_from_db()
        self.assertEqual(app.status_id, self.evaluated.pk)  # never automatic

    def test_no_suggestion_when_already_there_or_past_it_or_ended(self):
        for name in ("Interview", "Offer", "Rejected", "Hired"):
            app = job(self.a, status=Status.objects.get(name=name))
            self.assertIsNone(self.post("/interviews", self.interview_body(app)).json()["suggest_status"], name)

    def test_an_offer_suggests_the_offer_status(self):
        app = job(self.a, status=Status.objects.get(name="Interview"))
        r = self.post("/offers", {"application": app.pk, "base": "50000", "currency": "USD"}).json()
        self.assertEqual(r["suggest_status"]["name"], "Offer")
        offer_id = r["id"]
        r = self.patch(f"/offers/{offer_id}", {"notes": "x"}).json()
        self.assertEqual(r["suggest_status"]["name"], "Offer")

    def test_editing_an_interview_also_suggests(self):
        app = job(self.a)
        item = self.post("/interviews", self.interview_body(app)).json()["id"]
        self.assertEqual(self.patch(f"/interviews/{item}", {"notes": "bring a laptop"}).json()["suggest_status"]["name"], "Interview")


class HideWeak(Base):
    def test_saved_with_the_other_preferences(self):
        self.assertFalse(self.client.get(f"{BASE}/preferences").json()["hide_weak"])
        r = self.client.put(f"{BASE}/preferences", data=json.dumps({"hide_weak": True}), content_type="application/json")
        self.assertTrue(r.json()["hide_weak"])
        self.assertTrue(self.client.get(f"{BASE}/me").json()["preferences"]["hide_weak"])
        bad = self.client.put(f"{BASE}/preferences", data=json.dumps({"hide_weak": "yes"}), content_type="application/json")
        self.assertEqual(bad.status_code, 400)


class SourceHealth(Base):
    def searched(self, owner, entries):
        run = ScanRun.objects.create(owner=owner, running=False, total=len(entries), done=len(entries))
        for name, error in entries:
            ScanLogEntry.objects.create(run=run, source_name=name, connector="greenhouse", error=error)
        return run

    def test_own_and_shared_boards_show_when_they_last_worked_and_what_went_wrong(self):
        mine = JobSource.objects.create(owner=self.a, name="Acme", connector="greenhouse", board_token="acme")
        shared = JobSource.objects.create(owner=None, name="RemoteOK", connector="remoteok", board_token="")
        self.searched(self.a, [("Acme", ""), ("RemoteOK", "")])
        self.searched(self.a, [("Acme", "HTTP 500"), ("RemoteOK", "")])
        self.searched(self.a, [("Acme", "HTTP 503"), ("RemoteOK", "")])
        data = self.client.get(f"{BASE}/sources").json()
        health = next(s for s in data["mine"] if s["id"] == mine.pk)["health"]
        self.assertEqual(health["state"], "error")
        self.assertEqual(health["error"], "HTTP 503")
        self.assertIsNotNone(health["last_ok_at"])
        self.assertIsNotNone(health["since"])
        remote = next(s for s in data["shared_health"] if s["name"] == shared.name)["health"]
        self.assertEqual(remote["state"], "ok")
        self.assertEqual(data["trouble"], {"total": 2, "trouble": 1})

    def test_a_board_no_search_has_read_is_unknown_and_other_people_are_not_in_it(self):
        mine = JobSource.objects.create(owner=self.a, name="Acme", connector="greenhouse", board_token="acme")
        self.searched(self.b, [("Acme", "HTTP 500")])
        data = self.client.get(f"{BASE}/sources").json()
        self.assertEqual(next(s for s in data["mine"] if s["id"] == mine.pk)["health"]["state"], "unknown")
        self.assertIsNone(data["trouble"])
        self.assertNotIn("HTTP 500", json.dumps(data))

    def test_the_dashboard_says_how_many_had_trouble_in_the_last_search(self):
        self.assertIsNone(self.client.get(f"{BASE}/dashboard").json()["source_trouble"])
        self.searched(self.a, [("A", ""), ("B", "HTTP 500"), ("C", "timed out")])
        self.assertEqual(self.client.get(f"{BASE}/dashboard").json()["source_trouble"], {"total": 3, "trouble": 2})


class Export(Base):
    def test_signed_out_is_sent_to_sign_in(self):
        self.client.logout()
        r = self.client.get("/jobs/export.csv")
        self.assertEqual(r.status_code, 302)
        self.assertIn("/accounts/login/", r["Location"])

    def test_only_my_jobs_in_a_download_with_excel_friendly_bytes(self):
        job(self.a, company="Acme", role="Dev", notes="Café", url="https://a.example/1", applied_date=date(2026, 10, 1), score=4.0)
        job(self.b, company="BobCo", role="Secret")
        r = self.client.get("/jobs/export.csv")
        self.assertEqual(r.status_code, 200)
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertIn("no-store", r["Cache-Control"])
        body = r.content
        self.assertTrue(body.startswith(b"\xef\xbb\xbf"))
        text = body.decode("utf-8-sig")
        self.assertNotIn("BobCo", text)
        rows = list(csv.reader(io.StringIO(text)))
        self.assertEqual(rows[0], ["Company", "Role", "Link", "Status", "Found", "Applied", "Follow up", "Deadline", "Location", "Country", "Match %", "Notes"])
        self.assertEqual(rows[1][:4], ["Acme", "Dev", "https://a.example/1", "Evaluated"])
        self.assertEqual((rows[1][5], rows[1][10], rows[1][11]), ("2026-10-01", "80", "Café"))

    def test_formula_looking_cells_become_plain_text(self):
        for bad in ("=HYPERLINK(\"http://x\")", "+1 555", "-2+3", "@sum", "\tTab"):
            job(self.a, company=bad, role="r", notes=bad)
        rows = list(csv.reader(io.StringIO(self.client.get("/jobs/export.csv").content.decode("utf-8-sig"))))[1:]
        for row in rows:
            self.assertTrue(row[0].startswith("'"), row[0])
            self.assertTrue(row[11].startswith("'"), row[11])

    def test_only_get(self):
        self.assertEqual(self.client.post("/jobs/export.csv").status_code, 405)


def upload(client, text, preview=False, name="jobs.csv", raw=None):
    data = raw if raw is not None else text.encode("utf-8")
    url = f"{BASE}/jobs/import" + ("?preview=1" if preview else "")
    return client.post(url, {"file": SimpleUploadedFile(name, data, content_type="text/csv")})


GOOD = "Title,Employer,Link,Status,Date\nSenior Backend Engineer,Acme Inc.,https://acme.example/1,Applied,25/10/2026\nData Analyst,Globex,,,2026-10-20\n"


class Import(Base):
    def test_preview_changes_nothing_and_says_what_would_happen(self):
        r = upload(self.client, GOOD, preview=True).json()
        self.assertTrue(r["preview"])
        self.assertEqual((r["will_add"], r["skipped_count"], r["problem_count"]), (2, 0, 0))
        self.assertEqual([row["company"] for row in r["rows"]], ["Acme Inc.", "Globex"])
        self.assertEqual(r["rows"][0]["status"], "Applied")
        self.assertEqual(r["rows"][1]["status"], "Saved")
        self.assertEqual(Application.objects.count(), 0)

    def test_the_real_import_adds_the_jobs_with_a_note_and_the_right_dates(self):
        r = upload(self.client, GOOD).json()
        self.assertEqual(r["added"], 2)
        acme = Application.objects.get(company="Acme Inc.")
        self.assertEqual((acme.owner, acme.role, acme.status.name, acme.found_date), (self.a, "Senior Backend Engineer", "Applied", date(2026, 10, 25)))
        self.assertEqual(Application.objects.get(company="Globex").status.name, "Saved")
        self.assertEqual(acme.events.get().text, "Imported from a spreadsheet")
        self.assertEqual(acme.details_source, "")

    def test_columns_are_found_by_name_in_any_order_case_and_separator(self):
        r = upload(self.client, "NOTES;POSITION;company;Location;country\nhello;Dev;Acme;Kuala Lumpur;Malaysia\n").json()
        self.assertEqual(r["added"], 1)
        app = Application.objects.get()
        self.assertEqual((app.role, app.notes, app.location_text, app.country, app.details_source), ("Dev", "hello", "Kuala Lumpur", "MY", "manual"))

    def test_a_file_without_company_and_role_columns_is_refused_with_help(self):
        r = upload(self.client, "Name,Thing\nA,B\n")
        self.assertEqual(r.status_code, 400)
        self.assertIn("Company", r.json()["error"])

    def test_problems_are_listed_per_row_and_those_rows_are_not_imported(self):
        text = "Company,Role,Link,Applied\nA,,,\nB,Dev,not a link,\nC,Dev,,13/13/2026\nD,Dev,https://d.example,31/12/2025\n"
        r = upload(self.client, text).json()
        self.assertEqual((r["added"], r["problem_count"]), (1, 3))
        messages = " ".join(p["message"] for p in r["problems"])
        self.assertIn("Row 2", messages)
        self.assertIn("not a web address", messages)
        self.assertIn("not a date", messages)
        self.assertEqual(Application.objects.get().company, "D")
        self.assertEqual(Application.objects.get().applied_date, date(2025, 12, 31))

    def test_duplicates_are_skipped_and_listed(self):
        job(self.a, company="Acme", role="Backend Engineer", url="https://acme.example/old")
        text = "Company,Role,Link\nacme inc,Senior Backend Engineer,\nNew Co,Dev,https://acme.example/old\nFresh,Dev,\nFresh,dev,\n"
        r = upload(self.client, text).json()
        self.assertEqual((r["added"], r["skipped_count"]), (1, 3))
        self.assertTrue(all(s["reason"] for s in r["skipped"]))
        self.assertEqual(sorted(Application.objects.values_list("company", flat=True)), ["Acme", "Fresh"])

    def test_an_unknown_status_becomes_saved_with_a_warning(self):
        r = upload(self.client, "Company,Role,Status\nA,Dev,Waiting for fate\nB,Dev,discarded\n").json()
        self.assertEqual(Application.objects.get(company="A").status.name, "Saved")
        self.assertEqual(Application.objects.get(company="B").status.name, "Not for me")
        self.assertTrue(any("Waiting for fate" in w for w in r["warnings"]))

    @override_settings(STILLOPEN_MAX_APPLICATIONS=3)
    def test_the_job_limit_stops_the_import_in_plain_words(self):
        job(self.a)
        r = upload(self.client, "Company,Role\nA,x\nB,y\nC,z\nD,w\n").json()
        self.assertEqual(r["added"], 2)
        self.assertIn("limit of 3", r["stopped"])
        self.assertEqual(Application.objects.filter(owner=self.a).count(), 3)

    def test_it_never_reads_the_links(self):
        with mock.patch("tracker.services.netguard.safe_get", side_effect=AssertionError("network")), mock.patch("tracker.services.jobtext.fetch_posting", side_effect=AssertionError("network")):
            self.assertEqual(upload(self.client, "Company,Role,Link\nA,Dev,https://a.example/1\n").json()["added"], 1)

    def test_size_and_row_limits_and_a_missing_file(self):
        big = upload(self.client, "", raw=b"Company,Role\n" + b"A,B\n" * 300000)
        self.assertEqual(big.status_code, 400)
        many = "Company,Role\n" + "".join(f"C{i},R{i}\n" for i in range(1001))
        self.assertEqual(upload(self.client, many).status_code, 400)
        self.assertEqual(self.client.post(f"{BASE}/jobs/import").status_code, 400)
        self.assertEqual(upload(self.client, "", raw=b"\x00\x01\x02binary").status_code, 400)
        self.assertEqual(upload(self.client, "").status_code, 400)
        self.assertEqual(Application.objects.count(), 0)

    def test_old_windows_files_are_read(self):
        r = upload(self.client, "", raw="Company,Role\nCafé,Dev\n".encode("cp1252")).json()
        self.assertEqual(r["added"], 1)
        self.assertEqual(Application.objects.get().company, "Café")

    def test_it_only_ever_adds_to_the_caller(self):
        upload(self.client, GOOD)
        self.assertEqual(Application.objects.filter(owner=self.b).count(), 0)
        self.assertEqual(Application.objects.filter(owner=self.a).count(), 2)

    @override_settings(STILLOPEN_IMPORTS_PER_HOUR=2)
    def test_it_is_rate_limited(self):
        for _ in range(2):
            self.assertEqual(upload(self.client, GOOD, preview=True).status_code, 200)
        self.assertEqual(upload(self.client, GOOD, preview=True).status_code, 429)


class Duplicates(Base):
    def add(self, body):
        return self.post("/jobs", body)

    def test_manual_add_warns_with_the_existing_job_then_goes_through_when_confirmed(self):
        existing = job(self.a, company="Acme, Inc.", role="Backend Engineer", status=self.applied)
        r = self.add({"company": "ACME", "role": "Senior Backend Engineer"})
        self.assertEqual(r.status_code, 409)
        body = r.json()
        self.assertEqual(body["duplicate"], {"id": existing.pk, "company": "Acme, Inc.", "role": "Backend Engineer", "status": "Applied"})
        self.assertEqual(body["error"], "You already track Backend Engineer at Acme, Inc. (Applied).")
        self.assertEqual(Application.objects.count(), 1)
        ok = self.add({"company": "ACME", "role": "Senior Backend Engineer", "allow_duplicate": True})
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(Application.objects.count(), 2)

    def test_the_same_link_is_a_duplicate_too_and_another_person_never_counts(self):
        job(self.a, company="One", role="X", url="https://x.example/1")
        self.assertEqual(self.add({"company": "Two", "role": "Y", "url": "https://x.example/1"}).status_code, 409)
        job(self.b, company="Zed", role="Dev")
        self.assertEqual(self.add({"company": "Zed", "role": "Dev"}).status_code, 200)

    def test_different_roles_are_not_duplicates(self):
        job(self.a, company="Acme", role="Backend Engineer")
        self.assertEqual(self.add({"company": "Acme", "role": "Frontend Engineer"}).status_code, 200)

    def test_quick_add_tells_the_form_early(self):
        job(self.a, company="Acme", role="Backend Engineer")
        found = {"url": "https://j.example/1", "role": "Sr Backend Engineer", "company": "acme", "description": "text"}
        with mock.patch("tracker.services.tracking.fetch_prefill", return_value=found):
            r = self.post("/quickadd", {"url": "https://j.example/1"}).json()
        self.assertEqual(r["duplicate"]["company"], "Acme")

    def test_adding_a_posting_checks_company_and_role_too(self):
        source = JobSource.objects.create(owner=self.a, name="Acme", connector="greenhouse", board_token="acme")
        posting = Posting.objects.create(source=source, url="https://boards.example/2", company="Acme", title="Senior Backend Engineer", title_key="acme|backend engineer")
        job(self.a, company="Acme", role="Backend Engineer", url="https://elsewhere.example/9")
        r = self.post(f"/postings/{posting.pk}/add")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(Application.objects.count(), 1)
        ok = self.post(f"/postings/{posting.pk}/add", {"allow_duplicate": True})
        self.assertEqual(ok.status_code, 200)
        self.assertTrue(ok.json()["created"])


class Calibration(Base):
    def make(self, n, percent_score, replied):
        for i in range(n):
            app = job(self.a, status=self.applied, applied_date=date(2026, 10, 1), score=percent_score)
            if i < replied:
                Interview.objects.create(owner=self.a, application=app, scheduled_at=timezone.now())

    def test_hidden_until_there_are_enough_scored_applications(self):
        self.make(7, 4.5, 3)
        c = stats.candidate_stats(self.a, date(2026, 10, 25))["calibration"]
        self.assertFalse(c["enough"])
        self.assertEqual((c["scored"], c["needed"], c["bands"]), (7, 8, []))
        self.assertIn("hint, not a rule", c["caveat"])

    def test_per_band_applied_and_replied(self):
        self.make(6, 4.5, 3)  # 90%: Strong
        self.make(4, 1.0, 0)  # 20%: A stretch
        job(self.a, status=self.applied, applied_date=date(2026, 10, 1))  # no score: left out
        c = stats.candidate_stats(self.a, date(2026, 10, 25))["calibration"]
        self.assertTrue(c["enough"])
        self.assertEqual(c["scored"], 10)
        rows = {r["label"]: r for r in c["bands"]}
        self.assertEqual((rows["Strong"]["applied"], rows["Strong"]["replies"], rows["Strong"]["reply_rate"]), (6, 3, 50))
        self.assertEqual((rows["A stretch"]["applied"], rows["A stretch"]["replies"]), (4, 0))
        self.assertEqual(rows["Fair"]["applied"], 0)
        self.assertIsNone(rows["Fair"]["reply_rate"])

    def test_it_never_counts_someone_elses_applications(self):
        for _ in range(9):
            job(self.b, status=self.applied, applied_date=date(2026, 10, 1), score=4.0)
        self.assertFalse(self.client.get(f"{BASE}/stats").json()["calibration"]["enough"])


class ReplyParse(Base):
    def read(self, app, text):
        return self.post(f"/jobs/{app.pk}/reply-parse", {"text": text})

    def test_a_rejection_is_quoted_and_nothing_changes(self):
        app = job(self.a, status=self.applied)
        r = self.read(app, "Hi,\nThank you for applying. Unfortunately we will not be moving forward with your application.\nBest, HR").json()
        s = r["suggestion"]
        self.assertEqual(s["status"]["name"], "Rejected")
        self.assertEqual(s["confidence"], "clear")
        self.assertEqual(s["quotes"], ["Unfortunately we will not be moving forward with your application."])
        app.refresh_from_db()
        self.assertEqual(app.status_id, self.applied.pk)
        self.assertFalse(app.events.exists())

    def test_the_kinds_and_negation(self):
        app = job(self.a)
        cases = {
            "We would like to invite you to an interview next week.": "Interview",
            "We are pleased to offer you the position of Engineer.": "Offer",
            "Unfortunately we are not able to offer you the role.": "Rejected",
            "We have received your application and will be in touch.": "Responded",
            "We have decided to pursue other candidates.": "Rejected",
        }
        for text, name in cases.items():
            self.assertEqual(self.read(app, text).json()["suggestion"]["status"]["name"], name, text)

    def test_words_must_match_whole_words(self):
        app = job(self.a)
        self.assertIsNone(self.read(app, "The rejectionist council met the interviewees at the offertory.").json()["suggestion"])
        self.assertIsNone(self.read(app, "Lunch on Friday? Bring the offerings.").json()["suggestion"])

    def test_nothing_recognised_says_so_and_asks_for_nothing(self):
        r = self.read(job(self.a), "See you at the gym").json()
        self.assertIsNone(r["suggestion"])
        self.assertIn("set the status yourself", r["message"])

    def test_it_is_not_stored_and_a_long_text_is_cut(self):
        app = job(self.a)
        r = self.read(app, "Thank you for your application. " + "x " * 20000).json()
        self.assertTrue(r["truncated"])
        self.assertFalse(Event.objects.filter(application=app).exists())

    def test_empty_text_is_refused_and_someone_elses_job_is_a_404(self):
        self.assertEqual(self.read(job(self.a), "   ").status_code, 400)
        theirs = job(self.b)
        self.assertEqual(self.read(theirs, "We regret to inform you").status_code, 404)

    def test_the_timeline_note_is_written_only_when_the_person_confirms(self):
        app = job(self.a, status=self.applied)
        rejected = Status.objects.get(name="Rejected")
        r = self.patch(f"/jobs/{app.pk}/status", {"status": rejected.pk, "note": "We will not be moving forward."})
        self.assertEqual(r.status_code, 200)
        texts = list(app.events.values_list("text", flat=True))
        self.assertIn("Reply pasted: We will not be moving forward.", texts)
        self.assertIn("Status set to Rejected", texts)
