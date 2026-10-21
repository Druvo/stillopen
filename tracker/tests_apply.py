from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from tracker import mcp_tools
from tracker.models import Application, CVVersion, Event, SiteConfig, Status, UserProfile
from tracker.services import apply as apply_service
from tracker.services.apply import ApplyError
from tracker.tests_cv import JD, MASTER

User = get_user_model()
PW = "correct-horse-battery-staple"


def person(name="jane", **profile):
    u = User.objects.create_user(name, email=f"{name}@example.com", password=PW)
    UserProfile.objects.filter(user=u).update(profile_cv=MASTER, **profile)
    return u


def job(owner, **kw):
    fields = {"owner": owner, "company": "Globex", "role": "Backend Engineer", "status": Status.objects.get(name="Evaluated"),
              "description": JD, "url": "https://jobs.example.com/globex"}
    fields.update(kw)
    return Application.objects.create(**fields)


def tailored(owner, app, flagged=False, approved=False, **kw):
    fields = {"owner": owner, "application": app, "kind": "tailored", "label": "Globex CV", "content": "# Jane\n- Built things",
              "check_report": [{"kind": "number", "text": "99", "line": 2}] if flagged else [], "approved": approved}
    fields.update(kw)
    return CVVersion.objects.create(**fields)


def post_record(client, app, **data):
    return client.post(reverse("mark_applied", args=[app.pk]), data)


class Checklist(TestCase):
    def setUp(self):
        self.u = person()
        self.config = SiteConfig.for_user(self.u)

    def levels(self, app, versions=()):
        return {c["text"]: c["level"] for c in apply_service.checklist(app, self.config, list(versions))}

    def texts(self, app, versions=(), level=None):
        return [c["text"] for c in apply_service.checklist(app, self.config, list(versions)) if level in (None, c["level"])]

    def test_closed_posting_and_poor_fit_and_deadline_warn(self):
        app = job(self.u, live_state="expired", score=1.5, deadline=timezone.localdate() + timedelta(days=2))
        warnings = " | ".join(self.texts(app, level="warn"))
        self.assertIn("looks closed", warnings)
        self.assertIn("poor fit", warnings)
        self.assertIn("deadline is in 2 days", warnings)

    def test_good_state_is_all_clear(self):
        app = job(self.u, live_state="active", score=4.5, deadline=timezone.localdate() + timedelta(days=30))
        self.assertEqual(self.texts(app, level="warn"), [])
        self.assertIn("open", " ".join(self.texts(app, level="ok")))

    def test_past_deadline_warns(self):
        app = job(self.u, deadline=timezone.localdate() - timedelta(days=3))
        self.assertIn("passed 3 days ago", " ".join(self.texts(app, level="warn")))

    def test_cv_state_messages(self):
        app = job(self.u)
        self.assertIn("No CV tailored", " ".join(self.texts(app)))
        tailored(self.u, app, flagged=True)
        self.assertIn("still has flagged claims", " ".join(self.texts(app, level="warn")))
        good = tailored(self.u, app)
        self.assertIn("passed the fact check", " ".join(self.texts(app, [good], level="ok")))


class AssistantPage(TestCase):
    def setUp(self):
        self.u = person()
        self.app = job(self.u, company="Globex")
        self.client.force_login(self.u)

    def test_page_explains_it_does_not_submit_and_links_the_posting_safely(self):
        page = self.client.get(reverse("apply_page", args=[self.app.pk])).content.decode()
        self.assertTrue("does not submit applications" in page)
        self.assertTrue('href="https://jobs.example.com/globex" target="_blank" rel="noopener noreferrer"' in page)
        self.assertTrue("I submitted it" in page)

    def test_only_sendable_versions_are_offered(self):
        clean = tailored(self.u, self.app, label="Clean one")
        locked = tailored(self.u, self.app, flagged=True, label="Locked one")
        approved = tailored(self.u, self.app, flagged=True, approved=True, label="Approved one")
        other_job = job(self.u, company="Elsewhere")
        wrong_job = tailored(self.u, other_job, label="Wrong job")
        master = CVVersion.objects.create(owner=self.u, kind="master", content=MASTER, label="My master", approved=True)
        page = self.client.get(reverse("apply_page", args=[self.app.pk])).content.decode()
        self.assertTrue("Clean one" in page and "Approved one" in page and "My master" in page)
        self.assertFalse("Locked one" in page)
        self.assertFalse("Wrong job" in page)

    def test_email_draft_uses_only_what_is_known_and_is_escaped(self):
        evil = job(self.u, company="<script>alert(1)</script>", role="Dev")
        draft = apply_service.email_draft(evil)
        self.assertEqual(draft["subject"], "Application: Dev")
        self.assertIn("[Your name]", draft["body"])
        page = self.client.get(reverse("apply_page", args=[evil.pk])).content.decode()
        self.assertFalse("<script>alert(1)</script>" in page)

    def test_default_follow_up_days_come_from_the_admin_setting(self):
        SiteConfig.objects.filter(pk=1).update(apply_followup_days=3)
        page = self.client.get(reverse("apply_page", args=[self.app.pk])).content.decode()
        self.assertTrue('name="days" min="1" max="90" value="3"' in page)

    def test_closed_posting_asks_for_confirmation(self):
        Application.objects.filter(pk=self.app.pk).update(live_state="expired")
        page = self.client.get(reverse("apply_page", args=[self.app.pk])).content.decode()
        self.assertTrue("confirm_closed" in page)

    def test_other_peoples_jobs_and_anonymous_visitors(self):
        theirs = job(person("bob"))
        self.assertEqual(self.client.get(reverse("apply_page", args=[theirs.pk])).status_code, 404)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("apply_page", args=[self.app.pk])).status_code, 302)


class Recording(TestCase):
    def setUp(self):
        self.u = person()
        self.app = job(self.u)
        self.cv = tailored(self.u, self.app)
        self.client.force_login(self.u)

    def test_recording_sets_everything_and_logs_it(self):
        r = post_record(self.client, self.app, cv=self.cv.pk, channel="linkedin", note="Spoke to Sam", days=5)
        self.assertRedirects(r, reverse("dashboard"), fetch_redirect_response=False)
        self.app.refresh_from_db()
        today = timezone.localdate()
        self.assertEqual(self.app.status.name, "Applied")
        self.assertEqual((self.app.applied_date, self.app.applied_cv, self.app.applied_channel, self.app.applied_note),
                         (today, self.cv, "linkedin", "Spoke to Sam"))
        self.assertEqual(self.app.follow_up_date, today + timedelta(days=5))
        event = self.app.events.get(kind="applied")
        self.assertIn(f"CV v{self.cv.pk}", event.text)
        self.assertIn("LinkedIn", event.text)

    def test_posting_snapshot_survives_the_posting_changing(self):
        post_record(self.client, self.app, cv=self.cv.pk, days=7)
        Application.objects.filter(pk=self.app.pk).update(description="the posting was edited or removed")
        self.app.refresh_from_db()
        self.assertEqual(self.app.jd_at_apply, JD)

    def test_recording_again_updates_instead_of_duplicating(self):
        post_record(self.client, self.app, cv=self.cv.pk, channel="site", days=7)
        post_record(self.client, self.app, cv="none", channel="email", days=2)
        self.app.refresh_from_db()
        self.assertEqual((self.app.applied_channel, self.app.applied_cv), ("email", None))
        texts = list(self.app.events.filter(kind="applied").order_by("pk").values_list("text", flat=True))
        self.assertEqual(len(texts), 2)
        self.assertTrue(texts[0].startswith("Applied") and texts[1].startswith("Application details updated"))

    def test_never_moves_someone_backwards(self):
        Application.objects.filter(pk=self.app.pk).update(status=Status.objects.get(name="Interview"))
        post_record(self.client, self.app, cv=self.cv.pk, days=7)
        self.app.refresh_from_db()
        self.assertEqual(self.app.status.name, "Interview")
        self.assertEqual(self.app.applied_cv, self.cv)

    def test_backdating_is_allowed_future_is_not(self):
        yesterday = (timezone.localdate() - timedelta(days=2)).isoformat()
        post_record(self.client, self.app, cv="none", applied_on=yesterday, days=7)
        self.app.refresh_from_db()
        self.assertEqual(self.app.applied_date.isoformat(), yesterday)
        self.assertEqual(self.app.follow_up_date, self.app.applied_date + timedelta(days=7))
        before = self.app.applied_date
        post_record(self.client, self.app, cv="none", applied_on=(timezone.localdate() + timedelta(days=3)).isoformat(), days=7)
        self.app.refresh_from_db()
        self.assertEqual(self.app.applied_date, before)

    def test_bad_input_changes_nothing(self):
        for data in [{"days": 0}, {"days": 91}, {"days": "abc"}, {"days": 7, "channel": "carrier-pigeon"}, {"days": 7, "applied_on": "not-a-date"}]:
            post_record(self.client, self.app, cv=self.cv.pk, **data)
        self.app.refresh_from_db()
        self.assertEqual(self.app.status.name, "Evaluated")
        self.assertIsNone(self.app.applied_cv)
        self.assertFalse(self.app.events.filter(kind="applied").exists())

    def test_unsendable_versions_are_refused(self):
        locked = tailored(self.u, self.app, flagged=True)
        wrong_job = tailored(self.u, job(self.u, company="Elsewhere"))
        for version in (locked, wrong_job):
            post_record(self.client, self.app, cv=version.pk, days=7)
        self.app.refresh_from_db()
        self.assertIsNone(self.app.applied_cv)
        tailored_locked = CVVersion.objects.get(pk=locked.pk)
        from tracker.services import cvversions
        cvversions.approve(tailored_locked)
        post_record(self.client, self.app, cv=locked.pk, days=7)
        self.app.refresh_from_db()
        self.assertEqual(self.app.applied_cv, locked)

    def test_someone_elses_version_is_a_404(self):
        theirs = CVVersion.objects.create(owner=person("bob"), kind="master", content="Bob's CV", approved=True)
        self.assertEqual(post_record(self.client, self.app, cv=theirs.pk, days=7).status_code, 404)
        self.app.refresh_from_db()
        self.assertIsNone(self.app.applied_cv)

    def test_closed_posting_needs_explicit_confirmation(self):
        Application.objects.filter(pk=self.app.pk).update(live_state="expired")
        post_record(self.client, self.app, cv="none", days=7)
        self.app.refresh_from_db()
        self.assertEqual(self.app.status.name, "Evaluated")
        post_record(self.client, self.app, cv="none", days=7, confirm_closed="on")
        self.app.refresh_from_db()
        self.assertEqual(self.app.status.name, "Applied")

    def test_needs_a_status_that_counts_as_applied(self):
        Status.objects.update(counts_as_applied=False)
        post_record(self.client, self.app, cv="none", days=7)
        self.app.refresh_from_db()
        self.assertIsNone(self.app.applied_date)

    def test_post_only_and_owner_only(self):
        self.assertEqual(self.client.get(reverse("mark_applied", args=[self.app.pk])).status_code, 405)
        theirs = job(person("bob"))
        self.assertEqual(post_record(self.client, theirs, cv="none", days=7).status_code, 404)

    def test_dashboard_shows_what_was_sent(self):
        post_record(self.client, self.app, cv=self.cv.pk, channel="email", days=4)
        page = self.client.get(reverse("dashboard")).content.decode()
        self.assertTrue(f"sent <a" in page and f"CV v{self.cv.pk}" in page)
        self.assertTrue("via Email" in page)
        self.assertTrue("follow up" in page)


class FollowUps(TestCase):
    def setUp(self):
        self.u = person()
        self.client.force_login(self.u)
        self.today = timezone.localdate()

    def test_due_list_includes_only_what_is_due_and_active_and_mine(self):
        due = job(self.u, company="Due", follow_up_date=self.today)
        overdue = job(self.u, company="Overdue", follow_up_date=self.today - timedelta(days=4))
        job(self.u, company="Later", follow_up_date=self.today + timedelta(days=2))
        job(self.u, company="Rejected", follow_up_date=self.today, status=Status.objects.get(name="Rejected"))
        job(person("bob"), company="BobsDue", follow_up_date=self.today)
        names = [a.company for a in apply_service.due_followups(self.u)]
        self.assertEqual(names, ["Overdue", "Due"])
        page = self.client.get(reverse("dashboard")).content.decode()
        self.assertTrue("Follow-ups due" in page and "Overdue" in page)
        self.assertFalse("BobsDue" in page)

    def test_no_banner_when_nothing_is_due(self):
        job(self.u, follow_up_date=self.today + timedelta(days=5))
        self.assertFalse("Follow-ups due" in self.client.get(reverse("dashboard")).content.decode())

    def test_done_and_snooze(self):
        a = job(self.u, follow_up_date=self.today)
        self.client.post(reverse("followup_action", args=[a.pk, "snooze"]), {"days": 3})
        a.refresh_from_db()
        self.assertEqual(a.follow_up_date, self.today + timedelta(days=3))
        self.client.post(reverse("followup_action", args=[a.pk, "done"]))
        a.refresh_from_db()
        self.assertIsNone(a.follow_up_date)
        self.assertEqual(a.events.filter(kind="followup").count(), 2)

    def test_snooze_is_clamped_and_unknown_actions_404(self):
        a = job(self.u, follow_up_date=self.today)
        self.client.post(reverse("followup_action", args=[a.pk, "snooze"]), {"days": 100000})
        a.refresh_from_db()
        self.assertEqual(a.follow_up_date, self.today + timedelta(days=90))
        self.assertEqual(self.client.post(reverse("followup_action", args=[a.pk, "delete"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("followup_action", args=[a.pk, "done"])).status_code, 405)

    def test_cannot_touch_someone_elses_reminders(self):
        theirs = job(person("bob"), follow_up_date=self.today)
        self.assertEqual(self.client.post(reverse("followup_action", args=[theirs.pk, "done"])).status_code, 404)
        theirs.refresh_from_db()
        self.assertEqual(theirs.follow_up_date, self.today)


class Protection(TestCase):
    def setUp(self):
        self.u = person()
        self.app = job(self.u)
        self.cv = tailored(self.u, self.app)
        self.client.force_login(self.u)

    def test_a_cv_that_was_sent_cannot_be_deleted(self):
        post_record(self.client, self.app, cv=self.cv.pk, days=7)
        self.client.post(reverse("cv_delete", args=[self.cv.pk]))
        self.assertTrue(CVVersion.objects.filter(pk=self.cv.pk).exists())
        unsent = tailored(self.u, self.app, label="never sent")
        self.client.post(reverse("cv_delete", args=[unsent.pk]))
        self.assertFalse(CVVersion.objects.filter(pk=unsent.pk).exists())

    def test_deleting_an_application_or_an_account_still_works(self):
        post_record(self.client, self.app, cv=self.cv.pk, days=7)
        other = person("leaver")
        other_app = job(other)
        other_cv = tailored(other, other_app)
        other_app.applied_cv = other_cv
        other_app.save()
        self.app.delete()  # the application and the CV sent with it go together
        self.assertFalse(CVVersion.objects.filter(pk=self.cv.pk).exists())
        self.client.force_login(other)
        self.client.post(reverse("delete_account"), {"confirm": "leaver"})
        self.assertFalse(User.objects.filter(username="leaver").exists())
        self.assertFalse(CVVersion.objects.filter(pk=other_cv.pk).exists())

    def test_export_includes_what_was_sent(self):
        post_record(self.client, self.app, cv=self.cv.pk, channel="referral", note="via Sam", days=7)
        data = self.client.get(reverse("export_data")).json()["applications"][0]
        self.assertEqual((data["applied_channel"], data["applied_note"], data["applied_cv_label"]), ("referral", "via Sam", "Globex CV"))
        self.assertEqual(data["description_at_apply"], JD)
        self.assertTrue(data["follow_up_date"])


class Mcp(TestCase):
    def setUp(self):
        self.u = person("mcpapply")
        self.app = job(self.u)
        self.cv = tailored(self.u, self.app)
        mcp_tools.set_user(self.u)
        self.addCleanup(mcp_tools.set_user, None)

    def test_record_application_and_follow_ups(self):
        out = mcp_tools.record_application(self.app.pk, self.cv.pk, channel="site", note="from Claude", follow_up_days=2)
        self.assertEqual((out["status"], out["cv_version_sent"]), ("Applied", self.cv.pk))
        self.assertEqual(out["follow_up_date"], (timezone.localdate() + timedelta(days=2)).isoformat())
        Application.objects.filter(pk=self.app.pk).update(follow_up_date=timezone.localdate())
        self.assertEqual([f["id"] for f in mcp_tools.list_follow_ups()], [self.app.pk])

    def test_default_follow_up_comes_from_settings(self):
        SiteConfig.objects.filter(pk=1).update(apply_followup_days=9)
        out = mcp_tools.record_application(self.app.pk)
        self.assertEqual(out["follow_up_date"], (timezone.localdate() + timedelta(days=9)).isoformat())

    def test_refuses_flagged_foreign_and_unknown_things(self):
        flagged = tailored(self.u, self.app, flagged=True)
        theirs_user = person("someone")
        theirs_cv = CVVersion.objects.create(owner=theirs_user, kind="master", content="x", approved=True)
        theirs_app = job(theirs_user)
        for call in [
            lambda: mcp_tools.record_application(self.app.pk, flagged.pk),
            lambda: mcp_tools.record_application(self.app.pk, theirs_cv.pk),
            lambda: mcp_tools.record_application(theirs_app.pk),
            lambda: mcp_tools.record_application(self.app.pk, channel="carrier-pigeon"),
            lambda: mcp_tools.record_application(self.app.pk, follow_up_days=500),
        ]:
            with self.assertRaises(ValueError):
                call()
        self.app.refresh_from_db()
        self.assertEqual(self.app.status.name, "Evaluated")
        theirs_app.refresh_from_db()
        self.assertEqual(theirs_app.status.name, "Evaluated")
