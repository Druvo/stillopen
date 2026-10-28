"""Draft ahead: after a scheduled search, tailored CV drafts for the best new matches. Opt-in, capped, never approved."""
import json
from unittest import mock

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings

from tracker.models import AIUsageEvent, CVVersion, ScanRun, SiteConfig, UserProfile
from tracker.services import ai, draftahead, scan
from tracker.tests_apply import job
from tracker.tests_cv import MASTER, person

REPLY = MASTER.replace("Photoshop, Excel, C#", "C#, Excel, Photoshop")  # same claims, nothing new to flag
INVENTED = MASTER + "\n- Led a team of 40 engineers across 6 countries."
BASE = "https://jobs.example.com/"


def turn_on(user, site=True, provider="openai"):
    SiteConfig.objects.update_or_create(pk=1, defaults={"draft_ahead_site_enabled": site})
    UserProfile.objects.filter(user=user).update(draft_ahead_enabled=True, ai_provider=provider)


def run_for(owner, *apps):
    return ScanRun.objects.create(owner=owner, running=False, added_ids=[a.pk for a in apps], added=len(apps))


def strong(owner, n, **kw):  # 4.5 of 5 = 90%, inside the top band
    return job(owner, company=f"Co{n}", url=f"{BASE}{n}", score=4.5, **kw)


class Prepare(TestCase):
    def setUp(self):
        self.u = person("jane")
        turn_on(self.u)

    @mock.patch("tracker.services.ai.complete", return_value=REPLY)
    def test_a_draft_is_made_for_a_top_band_new_job_and_never_approved(self, complete):
        app = strong(self.u, 1)
        run = run_for(self.u, app)
        self.assertEqual(draftahead.prepare(self.u, run), 1)
        draft = CVVersion.objects.get(owner=self.u, kind="tailored")
        self.assertTrue(draft.draft_ahead)
        self.assertEqual(draft.application, app)
        self.assertFalse(draft.approved)
        self.assertIsNone(draft.approved_at)
        run.refresh_from_db()
        self.assertIn("1 CV draft ready for your review", run.note)

    @mock.patch("tracker.services.ai.complete", return_value=INVENTED)
    def test_a_flagged_draft_stays_flagged_and_cannot_be_exported(self, complete):
        draftahead.prepare(self.u, run_for(self.u, strong(self.u, 1)))
        draft = CVVersion.objects.get(kind="tailored")
        self.assertTrue(draft.flagged)
        self.assertFalse(draft.approved)
        self.assertFalse(draft.exportable)

    @mock.patch("tracker.services.ai.complete", return_value=REPLY)
    def test_only_the_top_band_and_only_this_runs_new_jobs(self, complete):
        low = job(self.u, company="Low", url=f"{BASE}low", score=2.0)
        unscored = job(self.u, company="None", url=f"{BASE}none", score=None)
        good = strong(self.u, 1)
        old = strong(self.u, 2)  # tracked before this run
        draftahead.prepare(self.u, run_for(self.u, low, unscored, good))
        self.assertEqual(list(CVVersion.objects.filter(kind="tailored").values_list("application_id", flat=True)), [good.pk])
        self.assertFalse(old.cv_versions.exists())

    @override_settings(STILLOPEN_DRAFT_AHEAD_MAX=2)
    @mock.patch("tracker.services.ai.complete", return_value=REPLY)
    def test_the_cap_per_run_and_best_first(self, complete):
        apps = [job(self.u, company=f"C{i}", url=f"{BASE}{i}", score=score) for i, score in enumerate((4.2, 5.0, 4.6, 4.4))]
        draftahead.prepare(self.u, run_for(self.u, *apps))
        made = set(CVVersion.objects.filter(kind="tailored").values_list("application_id", flat=True))
        self.assertEqual(made, {apps[1].pk, apps[2].pk})

    @mock.patch("tracker.services.ai.complete", return_value=REPLY)
    def test_the_same_job_never_gets_a_second_draft(self, complete):
        app = strong(self.u, 1)
        run = run_for(self.u, app)
        self.assertEqual(draftahead.prepare(self.u, run), 1)
        self.assertEqual(draftahead.prepare(self.u, run), 0)
        self.assertEqual(CVVersion.objects.filter(kind="tailored").count(), 1)
        self.assertEqual(complete.call_count, 1)

    @mock.patch("tracker.services.ai.complete")
    def test_one_job_failing_does_not_stop_the_others(self, complete):
        complete.side_effect = [ai.AIError("The AI did not answer."), RuntimeError("boom"), REPLY]
        apps = [strong(self.u, i) for i in range(3)]
        self.assertEqual(draftahead.prepare(self.u, run_for(self.u, *apps)), 1)
        self.assertEqual(CVVersion.objects.filter(kind="tailored").count(), 1)
        run = ScanRun.objects.get()
        self.assertIn("1 CV draft ready for your review; 2 could not be made.", run.note)

    @mock.patch("tracker.services.ai.complete", return_value=REPLY)
    def test_without_an_ai_key_it_is_skipped_with_a_plain_note(self, complete):
        UserProfile.objects.filter(user=self.u).update(ai_provider="anthropic")  # needs a key, none stored
        run = run_for(self.u, strong(self.u, 1))
        with mock.patch.dict("os.environ", {"STILLOPEN_AI_API_KEY": ""}):
            self.assertEqual(draftahead.prepare(self.u, run), 0)
        complete.assert_not_called()
        run.refresh_from_db()
        self.assertIn("set up your AI", run.note)
        self.assertFalse(CVVersion.objects.filter(kind="tailored").exists())

    @mock.patch("tracker.services.ai.complete", return_value=REPLY)
    def test_with_the_ai_off_it_is_skipped(self, complete):
        UserProfile.objects.filter(user=self.u).update(ai_provider="none")
        self.assertEqual(draftahead.prepare(self.u, run_for(self.u, strong(self.u, 1))), 0)
        complete.assert_not_called()

    @mock.patch("tracker.services.ai.complete", return_value=REPLY)
    def test_without_a_master_cv_it_is_skipped(self, complete):
        UserProfile.objects.filter(user=self.u).update(profile_cv="")
        run = run_for(self.u, strong(self.u, 1))
        self.assertEqual(draftahead.prepare(self.u, run), 0)
        run.refresh_from_db()
        self.assertIn("add your CV", run.note)

    @mock.patch("tracker.services.ai.complete", return_value=REPLY)
    def test_off_at_either_level_does_nothing_and_says_nothing(self, complete):
        for site, mine in ((False, True), (True, False)):
            SiteConfig.objects.update(draft_ahead_site_enabled=site)
            UserProfile.objects.filter(user=self.u).update(draft_ahead_enabled=mine)
            run = run_for(self.u, strong(self.u, 1))
            self.assertEqual(draftahead.prepare(self.u, run), 0)
            run.refresh_from_db()
            self.assertEqual(run.note, "")
        complete.assert_not_called()

    def test_the_ai_usage_is_logged_like_a_manual_tailoring(self):
        app = strong(self.u, 1)
        def backend(system, user, config):
            ai._last_usage.set({"input_tokens": 100, "output_tokens": 50, "cost_usd": None})
            return REPLY

        with mock.patch("tracker.services.ai.BACKENDS", {"openai": backend}):
            draftahead.prepare(self.u, run_for(self.u, app))
        self.assertTrue(AIUsageEvent.objects.filter(owner=self.u, application=app, purpose="tailor").exists())

    @mock.patch("tracker.services.ai.complete", return_value=REPLY)
    def test_other_peoples_jobs_in_the_run_are_ignored(self, complete):
        other = person("omar")
        theirs = strong(other, 9)
        draftahead.prepare(self.u, run_for(self.u, theirs))
        self.assertFalse(CVVersion.objects.filter(owner=other, kind="tailored").exists())
        self.assertFalse(CVVersion.objects.filter(owner=self.u, kind="tailored").exists())


class Digest(TestCase):
    def setUp(self):
        from allauth.account.models import EmailAddress

        self.u = person("jane")
        EmailAddress.objects.create(user=self.u, email=self.u.email, verified=True, primary=True)

    def test_the_email_mentions_waiting_drafts_in_one_line(self):
        app = strong(self.u, 1)
        for i in range(2):
            CVVersion.objects.create(owner=self.u, application=strong(self.u, 10 + i), kind="tailored", content="x", draft_ahead=True)
        self.assertTrue(scan.send_scan_digest(self.u, run_for(self.u, app)))
        self.assertIn("2 drafts are waiting for your review.", mail.outbox[0].body)

    def test_no_line_when_nothing_is_waiting(self):
        self.assertTrue(scan.send_scan_digest(self.u, run_for(self.u, strong(self.u, 1))))
        self.assertNotIn("waiting for your review", mail.outbox[0].body)

    def test_an_approved_draft_is_no_longer_waiting(self):
        CVVersion.objects.create(owner=self.u, application=strong(self.u, 5), kind="tailored", content="x", draft_ahead=True, approved=True)
        self.assertEqual(draftahead.digest_line(self.u), "")


class ScheduledScanRunsIt(TestCase):
    @mock.patch("tracker.services.ai.complete", return_value=REPLY)
    def test_the_command_prepares_drafts_after_the_search(self, complete):
        u = person("jane")
        turn_on(u)
        UserProfile.objects.filter(user=u).update(scan_digest_enabled=True)
        SiteConfig.objects.update(scan_emails_enabled=True)
        app = strong(u, 1)
        with mock.patch("tracker.services.scan.searchable_sources") as sources, mock.patch("tracker.services.scan.start_run") as start:
            sources.return_value.exists.return_value = True
            start.return_value = run_for(u, app)
            call_command("scheduled_scan")
        self.assertTrue(CVVersion.objects.filter(owner=u, kind="tailored", draft_ahead=True).exists())


class DashboardAndIsolation(TestCase):
    def setUp(self):
        self.a, self.b = person("jane"), person("omar")
        self.client.force_login(self.a)

    def get(self):
        return self.client.get("/api/v1/dashboard").json()

    def draft(self, owner, app, **kw):
        fields = {"owner": owner, "application": app, "kind": "tailored", "content": "x", "draft_ahead": True,
                  "check_report": [{"kind": "number", "text": "9", "line": 1}, {"kind": "number", "text": "8", "line": 2}]}
        fields.update(kw)
        return CVVersion.objects.create(**fields)

    def test_the_dashboard_lists_my_waiting_drafts_with_their_flag_count(self):
        app = strong(self.a, 1)
        d = self.draft(self.a, app)
        self.assertEqual(self.get()["drafts"], [{
            "id": d.pk, "job_id": app.pk, "company": app.company, "role": app.role, "flagged_count": 2,
            "created_at": self.get()["drafts"][0]["created_at"],
        }])

    def test_another_persons_drafts_never_appear(self):
        self.draft(self.b, strong(self.b, 2))
        self.assertEqual(self.get()["drafts"], [])

    def test_manual_and_approved_versions_are_not_drafts(self):
        app = strong(self.a, 1)
        self.draft(self.a, app, draft_ahead=False)
        self.draft(self.a, app, approved=True)
        self.assertEqual(self.get()["drafts"], [])

    def test_discarding_deletes_only_the_draft_and_keeps_the_master_history(self):
        app = strong(self.a, 1)
        master = CVVersion.objects.create(owner=self.a, kind="master", content="m", approved=True)
        d = self.draft(self.a, app, parent=master)
        self.assertEqual(self.client.delete(f"/api/v1/cv/{d.pk}").status_code, 200)
        self.assertFalse(CVVersion.objects.filter(pk=d.pk).exists())
        self.assertTrue(CVVersion.objects.filter(pk=master.pk).exists())
        self.assertEqual(self.get()["drafts"], [])

    def test_i_cannot_discard_or_open_someone_elses_draft(self):
        d = self.draft(self.b, strong(self.b, 2))
        self.assertEqual(self.client.delete(f"/api/v1/cv/{d.pk}").status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/cv/{d.pk}").status_code, 404)
        self.assertTrue(CVVersion.objects.filter(pk=d.pk).exists())

    def test_the_draft_is_not_approvable_by_anyone_but_the_owner(self):
        d = self.draft(self.b, strong(self.b, 2))
        self.assertEqual(self.client.post(f"/api/v1/cv/{d.pk}/approve").status_code, 404)
        d.refresh_from_db()
        self.assertFalse(d.approved)

    def test_the_profile_carries_the_new_settings(self):
        data = self.client.get("/api/v1/profile").json()
        self.assertFalse(data["profile"]["draft_ahead_enabled"])
        self.assertFalse(data["site"]["draft_ahead_site_enabled"])
        body = {**data["profile"], "draft_ahead_enabled": True}
        r = self.client.put("/api/v1/profile", data=json.dumps(body), content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(UserProfile.objects.get(user=self.a).draft_ahead_enabled)
        self.assertFalse(UserProfile.objects.get(user=self.b).draft_ahead_enabled)
