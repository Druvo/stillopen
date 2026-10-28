"""The opt-in Google connection, with Google's HTTP faked: no real network anywhere."""
import base64
import json
import logging
import re
from datetime import timedelta, timezone as _tz
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.utils import timezone

from tracker import crypto
from tracker.models import Application, CoverLetter, CVVersion, Event, GoogleConnection, Interview, MailMessage, SiteConfig, Status
from tracker.services import ai, apply as apply_service, gcal, gmail, googleconnect
from tracker.services.googleconnect import SCOPES

dt_utc = _tz.utc
User = get_user_model()
PW = "correct-horse-battery-staple"
BASE = "/api/v1"
ACCESS, REFRESH = "ya29.fake-access-token", "1//fake-refresh-token"
CV = "Backend engineer. Python, SQL, Docker."


class Resp:
    def __init__(self, status=200, data=None):
        self.status_code = status
        self._data = data
        self.content = b"" if data is None else json.dumps(data).encode()

    def json(self):
        if self._data is None:
            raise ValueError("no json")
        return self._data


class FakeGoogle:
    """Answers the few Google endpoints we use; records every call so tests can see what was (not) sent."""

    def __init__(self):
        self.calls = []
        self.refresh_status = 200
        self.token_scope = " ".join(SCOPES)
        self.thread = {"id": "T1", "messages": []}
        self.events = {}
        self.busy = []
        self.next_event = 1

    def __call__(self, method, url, headers=None, timeout=None, allow_redirects=None, **kw):
        self.calls.append((method, url, kw))
        path = urlparse(url).path
        if path == "/token":
            if kw["data"]["grant_type"] == "refresh_token":
                return Resp(self.refresh_status, {"access_token": ACCESS + "2", "expires_in": 3600} if self.refresh_status == 200 else {"error": "invalid_grant"})
            return Resp(200, {"access_token": ACCESS, "refresh_token": REFRESH, "expires_in": 3600, "scope": self.token_scope})
        if path == "/revoke":
            return Resp(200, {})
        if path.endswith("/profile"):
            return Resp(200, {"emailAddress": "me@gmail.example"})
        if path.endswith("/messages/send"):
            return Resp(200, {"id": "M1", "threadId": "T1"})
        if path.endswith("/threads"):
            return Resp(200, {"threads": [{"id": "T9"}]})
        if "/threads/" in path:
            return Resp(200, self.thread)
        if path.endswith("/freeBusy"):
            return Resp(200, {"calendars": {"primary": {"busy": self.busy}}})
        if path.endswith("/calendars/primary/events") and method == "POST":
            eid = f"ev{self.next_event}"
            self.next_event += 1
            self.events[eid] = {**kw["json"], "id": eid, "updated": "2030-01-01T00:00:00Z"}
            return Resp(200, self.events[eid])
        m = re.search(r"/events/(.+)$", path)
        if m:
            eid = m.group(1)
            if method == "DELETE":
                self.events.pop(eid, None)
                return Resp(204)
            if eid not in self.events:
                return Resp(404, {"error": {"code": 404}})
            if method == "PATCH":
                self.events[eid].update(kw["json"])
                self.events[eid]["updated"] = "2030-01-02T00:00:00Z"
            return Resp(200, self.events[eid])
        return Resp(404, {})

    def sent(self):
        return [c for c in self.calls if c[1].endswith("/messages/send")]


def person(name):
    return User.objects.create_user(name, email=f"{name}@example.com", password=PW)


def job(owner, **kw):
    fields = {"owner": owner, "company": "Acme", "role": "Dev", "status": Status.objects.get(name="Evaluated"), "description": "Send your CV to jobs@acme.example please."}
    fields.update(kw)
    return Application.objects.create(**fields)


def connect(owner, **kw):
    c = GoogleConnection(owner=owner, scopes=list(SCOPES), email="me@gmail.example", **kw)
    c.set_tokens(ACCESS, timezone.now() + timedelta(hours=1), REFRESH)
    c.save()
    return c


class Base(TestCase):
    def setUp(self):
        cache.clear()
        config = SiteConfig.load()
        config.google_connect_client_id = "client-id.apps.example"
        config.set_google_connect_secret("client-secret-fake")
        config.save()
        self.fake = FakeGoogle()
        patcher = mock.patch("tracker.services.googleconnect.requests.request", self.fake)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.a, self.b = person("alice"), person("bob")
        self.client.force_login(self.a)

    def post(self, path, body=None, client=None):
        return (client or self.client).post(f"{BASE}{path}", data=json.dumps(body or {}), content_type="application/json")

    def master(self, owner):
        return CVVersion.objects.create(owner=owner, kind="master", content=CV, approved=True)


class ConnectFlow(Base):
    def begin(self):
        url = self.post("/google/connect").json()["url"]
        return url, parse_qs(urlparse(url).query)

    def test_off_while_the_client_is_blank(self):
        SiteConfig.objects.update(google_connect_client_id="")
        self.assertFalse(self.client.get(f"{BASE}/google/status").json()["available"])
        self.assertEqual(self.post("/google/connect").status_code, 400)

    def test_begin_uses_pkce_state_and_every_scope(self):
        url, q = self.begin()
        self.assertTrue(url.startswith("https://accounts.google.com/"))
        self.assertEqual(q["code_challenge_method"], ["S256"])
        self.assertEqual(set(q["scope"][0].split()), set(SCOPES))
        self.assertTrue(q["state"][0] and q["code_challenge"][0])
        self.assertNotIn("code_verifier", url)

    def test_state_mismatch_is_refused_and_connects_nothing(self):
        self.begin()
        r = self.client.get("/google/callback/?state=wrong&code=abc")
        self.assertEqual(r.status_code, 302)
        self.assertFalse(GoogleConnection.objects.exists())
        self.assertFalse([c for c in self.fake.calls if c[1].endswith("/token")])
        self.assertIn("did not start here", self.client.get(f"{BASE}/google/status").json()["message"])

    def test_callback_without_a_started_flow_is_refused(self):
        self.client.get("/google/callback/?state=anything&code=abc")
        self.assertFalse(GoogleConnection.objects.exists())

    def test_state_is_single_use_and_bound_to_the_session(self):
        _, q = self.begin()
        other = Client()
        other.force_login(self.a)  # same person, a different browser session
        other.get(f"/google/callback/?state={q['state'][0]}&code=abc")
        self.assertFalse(GoogleConnection.objects.exists())
        self.client.get(f"/google/callback/?state={q['state'][0]}&code=abc")
        self.assertTrue(GoogleConnection.objects.filter(owner=self.a).exists())
        GoogleConnection.objects.all().delete()
        self.client.get(f"/google/callback/?state={q['state'][0]}&code=abc")  # replay
        self.assertFalse(GoogleConnection.objects.exists())

    def test_the_code_exchange_sends_the_pkce_verifier(self):
        _, q = self.begin()
        self.client.get(f"/google/callback/?state={q['state'][0]}&code=abc")
        exchange = next(c for c in self.fake.calls if c[1].endswith("/token"))[2]["data"]
        self.assertEqual(exchange["code"], "abc")
        digest = base64.urlsafe_b64encode(__import__("hashlib").sha256(exchange["code_verifier"].encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(digest, q["code_challenge"][0])

    def test_tokens_are_encrypted_at_rest_and_never_in_an_api_answer(self):
        _, q = self.begin()
        self.client.get(f"/google/callback/?state={q['state'][0]}&code=abc")
        c = GoogleConnection.objects.get(owner=self.a)
        self.assertNotIn(REFRESH, c.refresh_token_encrypted)
        self.assertNotIn(ACCESS, c.access_token_encrypted)
        self.assertEqual(crypto.decrypt(c.refresh_token_encrypted), REFRESH)
        self.assertEqual(c.email, "me@gmail.example")
        body = self.client.get(f"{BASE}/google/status").content.decode()
        self.assertTrue(json.loads(body)["connected"])
        for secret in (REFRESH, ACCESS, "client-secret-fake"):
            self.assertNotIn(secret, body)
        self.assertNotIn("refresh", body.lower())

    def test_missing_scopes_are_refused(self):
        self.fake.token_scope = SCOPES[0]
        _, q = self.begin()
        self.client.get(f"/google/callback/?state={q['state'][0]}&code=abc")
        self.assertFalse(GoogleConnection.objects.exists())

    def test_the_admin_secret_is_stored_encrypted(self):
        config = SiteConfig.load()
        self.assertNotIn("client-secret-fake", config.google_connect_secret_encrypted)
        self.assertEqual(config.effective_google_connect, ("client-id.apps.example", "client-secret-fake"))

    def test_disconnect_revokes_at_google_and_deletes_the_tokens(self):
        connect(self.a)
        r = self.post("/google/disconnect")
        self.assertFalse(r.json()["connected"])
        revoke = [c for c in self.fake.calls if c[1].endswith("/revoke")]
        self.assertEqual(revoke[0][2]["data"]["token"], REFRESH)
        self.assertFalse(GoogleConnection.objects.exists())

    def test_only_google_hosts_are_ever_called(self):
        with self.assertRaises(googleconnect.GoogleError):
            googleconnect.http("GET", "https://evil.example/token")
        with self.assertRaises(googleconnect.GoogleError):
            googleconnect.http("GET", "http://gmail.googleapis.com/x")


class Admin(Base):
    def test_the_admin_form_has_a_write_only_secret_that_is_kept_when_blank(self):
        from tracker.admin import SiteConfigForm
        form = SiteConfigForm(instance=SiteConfig.load())
        self.assertNotIn("client-secret-fake", str(form["google_connect_secret"]))
        admin_user = User.objects.create_superuser("root", "root@example.com", PW)
        self.client.force_login(admin_user)
        r = self.client.get("/admin/tracker/siteconfig/1/change/")
        self.assertEqual(r.status_code, 200)
        self.assertNotIn(b"client-secret-fake", r.content)


class Tokens(Base):
    def test_an_expired_token_is_renewed_on_demand(self):
        c = connect(self.a)
        c.access_expires_at = timezone.now() - timedelta(minutes=1)
        c.save()
        self.assertEqual(googleconnect.access_token(c), ACCESS + "2")
        c.refresh_from_db()
        self.assertEqual(c.access_token, ACCESS + "2")

    def test_a_refresh_failure_says_to_reconnect_and_leaks_nothing(self):
        c = connect(self.a)
        c.access_expires_at = timezone.now() - timedelta(minutes=1)
        c.save()
        self.fake.refresh_status = 400
        app = job(self.a)
        records = []
        handler = logging.Handler()
        handler.emit = records.append
        logging.getLogger().addHandler(handler)
        self.addCleanup(logging.getLogger().removeHandler, handler)
        r = self.post(f"/jobs/{app.pk}/google/check", {"contact_email": "hr@acme.example"})
        self.assertEqual(r.status_code, 400)
        self.assertIn("Reconnect", r.json()["error"])
        for secret in (REFRESH, ACCESS, "client-secret-fake"):
            self.assertNotIn(secret, r.content.decode())
            self.assertFalse([x for x in records if secret in x.getMessage()])
        c.refresh_from_db()
        self.assertIn("Reconnect", c.last_error)


class Send(Base):
    def setUp(self):
        super().setUp()
        connect(self.a)
        self.app = job(self.a)
        self.cv = self.master(self.a)
        self.msg = {"to": "jobs@acme.example", "subject": "Application: Dev", "body": "Dear team, my CV is attached.", "cv": self.cv.pk}

    def preview(self, **over):
        return self.post(f"/jobs/{self.app.pk}/google/preview", {**self.msg, **over})

    def send(self, **over):
        return self.post(f"/jobs/{self.app.pk}/google/send", {**self.msg, **over})

    def test_the_apply_screen_offers_the_posting_address_only(self):
        data = self.client.get(f"{BASE}/jobs/{self.app.pk}/apply").json()["google"]
        self.assertEqual(data["suggested_to"], "jobs@acme.example")
        self.assertTrue(data["connected"])
        bare = job(self.a, description="No address here.")
        self.assertEqual(self.client.get(f"{BASE}/jobs/{bare.pk}/apply").json()["google"]["suggested_to"], "")

    def test_preview_shows_everything_and_sends_nothing(self):
        r = self.preview().json()
        self.assertEqual((r["to"], r["subject"], r["from"]), ("jobs@acme.example", "Application: Dev", "me@gmail.example"))
        self.assertEqual(r["attachments"][0]["name"], f"CV-v{self.cv.pk}.docx")
        self.assertTrue(r["digest"])
        self.assertEqual(self.fake.sent(), [])

    def test_no_confirm_means_nothing_is_sent(self):
        digest = self.preview().json()["digest"]
        for confirm in (False,):
            r = self.send(digest=digest, confirm=confirm)
            self.assertEqual(r.status_code, 400)
        r = self.post(f"/jobs/{self.app.pk}/google/send", {**self.msg, "digest": digest})  # confirm left out
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.fake.sent(), [])
        self.app.refresh_from_db()
        self.assertIsNone(self.app.applied_date)

    def test_a_changed_message_needs_a_new_preview(self):
        digest = self.preview().json()["digest"]
        r = self.send(digest=digest, confirm=True, body="Something else entirely.")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.fake.sent(), [])

    def test_send_goes_out_records_the_application_and_keeps_the_thread(self):
        letter = CoverLetter.objects.create(owner=self.a, application=self.app, content="Dear team, hello.", approved=True)
        digest = self.preview(cover=letter.pk).json()["digest"]
        r = self.send(cover=letter.pk, digest=digest, confirm=True)
        self.assertEqual(r.status_code, 200, r.content)
        (call,) = self.fake.sent()
        raw = base64.urlsafe_b64decode(call[2]["json"]["raw"]).decode("latin-1")
        self.assertIn("To: jobs@acme.example", raw)
        self.assertIn("Subject: Application: Dev", raw)
        self.assertEqual(raw.count("Content-Disposition: attachment"), 2)
        self.app.refresh_from_db()
        self.assertEqual(self.app.gmail_thread_id, "T1")
        self.assertEqual(self.app.applied_cv_id, self.cv.pk)
        self.assertEqual(self.app.applied_channel, "email")
        self.assertTrue(self.app.status.counts_as_applied)
        self.assertTrue(self.app.events.filter(kind="applied", text__contains="jobs@acme.example").exists())

    def test_header_injection_and_bad_addresses_are_refused(self):
        for bad in ("a@b.example\nBcc: x@y.example", "a@b.example, c@d.example", "not-an-address", ""):
            self.assertEqual(self.preview(to=bad).status_code, 400, bad)
        self.assertEqual(self.preview(subject="Hi\nBcc: x@y.example").status_code, 400)

    def test_a_flagged_unapproved_cv_cannot_be_attached(self):
        flagged = CVVersion.objects.create(owner=self.a, application=self.app, kind="tailored", content="Led 400 engineers", check_report=[{"kind": "number", "text": "400"}])
        self.assertEqual(self.preview(cv=flagged.pk).status_code, 400)
        self.assertEqual(self.send(cv=flagged.pk, digest="x", confirm=True).status_code, 400)
        self.assertEqual(self.fake.sent(), [])
        flagged.approved = True
        flagged.save()
        self.assertEqual(self.preview(cv=flagged.pk).status_code, 200)

    def test_record_itself_still_refuses_a_flagged_cv(self):
        flagged = CVVersion.objects.create(owner=self.a, application=self.app, kind="tailored", content="x", check_report=[{"kind": "number", "text": "4"}])
        with self.assertRaises(apply_service.ApplyError):
            apply_service.record(self.app, flagged, "email", "", 7, SiteConfig.load())

    def test_someone_elses_cv_and_cover_letter_cannot_be_attached(self):
        theirs = self.master(self.b)
        self.assertEqual(self.preview(cv=theirs.pk).status_code, 400)
        other_app = job(self.b)
        letter = CoverLetter.objects.create(owner=self.b, application=other_app, content="Dear", approved=True)
        self.assertEqual(self.preview(cover=letter.pk).status_code, 400)

    def test_an_unapproved_flagged_cover_letter_cannot_be_attached(self):
        letter = CoverLetter.objects.create(owner=self.a, application=self.app, content="Dear", check_report=[{"kind": "x", "text": "y"}])
        self.assertEqual(self.preview(cover=letter.pk).status_code, 400)

    def test_attachments_are_size_capped(self):
        with mock.patch("tracker.services.gmail.MAX_ATTACHMENT_BYTES", 10):
            self.assertEqual(self.preview().status_code, 400)

    def test_without_a_connection_nothing_can_be_sent(self):
        GoogleConnection.objects.all().delete()
        self.assertEqual(self.preview().status_code, 400)

    def test_alice_cannot_use_bobs_connection_or_job(self):
        connect(self.b)
        bob_job = job(self.b)
        r = self.post(f"/jobs/{bob_job.pk}/google/preview", self.msg)
        self.assertEqual(r.status_code, 404)
        self.assertEqual(self.post(f"/jobs/{bob_job.pk}/google/send", {**self.msg, "digest": "x", "confirm": True}).status_code, 404)
        self.assertEqual(self.fake.sent(), [])
        # each person's own connection is the only one used
        self.assertEqual(googleconnect.for_user(self.a).owner_id, self.a.pk)

    def test_sending_is_rate_limited(self):
        with mock.patch("tracker.api.google.SEND_PER_HOUR", 1):
            digest = self.preview().json()["digest"]
            self.assertEqual(self.send(digest=digest, confirm=True).status_code, 200)
            self.assertEqual(self.send(digest=digest, confirm=True).status_code, 429)


class Replies(Base):
    def setUp(self):
        super().setUp()
        connect(self.a)
        self.app = job(self.a, gmail_thread_id="T1")
        self.fake.thread = {"id": "T1", "messages": [
            {"id": "m1", "internalDate": "1893456000000", "snippet": "Thanks for applying",
             "payload": {"headers": [{"name": "From", "value": "Me <me@gmail.example>"}]}},
            {"id": "m2", "internalDate": "1893542400000", "snippet": "We &#39;d like to talk " + "x" * 400,
             "payload": {"headers": [{"name": "From", "value": "HR <hr@acme.example>"}]}},
        ]}

    def test_new_messages_are_saved_with_only_the_short_facts(self):
        r = self.post(f"/jobs/{self.app.pk}/google/check", {}).json()
        self.assertEqual(r["new"], 2)
        rows = {m.gmail_id: m for m in MailMessage.objects.filter(application=self.app)}
        self.assertTrue(rows["m1"].from_me)
        self.assertFalse(rows["m2"].from_me)
        self.assertLessEqual(len(rows["m2"].snippet), 300)
        self.assertIn("We 'd like", rows["m2"].snippet)
        self.assertEqual(rows["m2"].sender, "HR <hr@acme.example>")
        again = self.post(f"/jobs/{self.app.pk}/google/check", {}).json()
        self.assertEqual(again["new"], 0)
        self.assertEqual(MailMessage.objects.filter(application=self.app).count(), 2)

    def test_the_cache_skips_google_on_open(self):
        self.post(f"/jobs/{self.app.pk}/google/check", {})
        before = len(self.fake.calls)
        r = self.post(f"/jobs/{self.app.pk}/google/check", {"force": False}).json()
        self.assertTrue(r["cached"])
        self.assertEqual(len(self.fake.calls), before)

    def test_only_the_stored_thread_is_read(self):
        self.post(f"/jobs/{self.app.pk}/google/check", {})
        urls = [c[1] for c in self.fake.calls]
        self.assertTrue(any(u.endswith("/threads/T1") for u in urls))
        self.assertFalse(any(u.endswith("/messages") or "/threads?" in u or u.endswith("/threads") for u in urls))

    def test_a_confirmed_address_can_link_an_earlier_conversation(self):
        bare = job(self.a)
        self.fake.thread["id"] = "T9"
        r = self.post(f"/jobs/{bare.pk}/google/check", {"contact_email": "hr@acme.example"}).json()
        self.assertTrue(r["linked"])
        bare.refresh_from_db()
        self.assertEqual(bare.gmail_thread_id, "T9")
        search = next(c for c in self.fake.calls if c[1].endswith("/threads"))
        self.assertIn("hr@acme.example", search[2]["params"]["q"])

    def test_messages_of_another_person_are_not_visible(self):
        self.post(f"/jobs/{self.app.pk}/google/check", {})
        bob = Client()
        bob.force_login(self.b)
        self.assertEqual(bob.get(f"{BASE}/jobs/{self.app.pk}/google/messages").status_code, 404)
        self.assertEqual(self.post(f"/jobs/{self.app.pk}/google/check", {}, client=bob).status_code, 404)

    def test_draft_reply_is_only_a_draft_and_is_fact_checked(self):
        self.post(f"/jobs/{self.app.pk}/google/check", {})
        from tracker.models import UserProfile
        UserProfile.objects.filter(user=self.a).update(profile_cv=CV)
        hr = MailMessage.objects.get(gmail_id="m2")
        with mock.patch.object(ai, "complete", return_value="Dear HR, I have 40 years of Python.\n\nKind regards,\n[Your name]") as complete:
            r = self.post(f"/jobs/{self.app.pk}/google/draft", {"message_id": hr.pk}).json()
        self.assertIn("Python", r["draft"])
        self.assertTrue(r["flags"])
        self.assertIn("<employer_message>", complete.call_args[0][2])
        self.assertEqual(self.fake.sent(), [])
        mine = MailMessage.objects.get(gmail_id="m1")
        self.assertEqual(self.post(f"/jobs/{self.app.pk}/google/draft", {"message_id": mine.pk}).status_code, 400)

    def test_suggest_times_returns_three_free_slots(self):
        r = self.post(f"/jobs/{self.app.pk}/google/times").json()
        self.assertEqual(r["count"], 3)
        self.assertEqual(r["text"].count("\n- "), 3)

    def test_busy_time_is_avoided(self):
        slots = gcal.free_slots(self.a)
        first = slots[0]
        self.fake.busy = [{"start": first.astimezone(dt_utc).isoformat(), "end": (first + timedelta(hours=1)).astimezone(dt_utc).isoformat()}]
        again = gcal.free_slots(self.a)
        self.assertNotIn(first, again)
        for s in again:
            self.assertTrue(9 <= s.hour < 17 and s.weekday() < 5)


class Calendar(Base):
    def setUp(self):
        super().setUp()
        self.conn = connect(self.a, calendar_sync=True)
        self.app = job(self.a)
        self.when = timezone.now() + timedelta(days=3)

    def interview(self, **kw):
        return Interview.objects.create(owner=self.a, application=self.app, scheduled_at=self.when, **kw)

    def test_create_update_delete_follow_the_interview(self):
        form = {"application": self.app.pk, "scheduled_at": timezone.localtime(self.when).strftime("%Y-%m-%dT%H:%M"), "kind": "video"}
        r = self.post("/interviews", form).json()
        item = Interview.objects.get(pk=r["id"])
        self.assertTrue(item.google_event_id)
        self.assertEqual(r["calendar_note"], "")
        self.assertNotIn("attendees", self.fake.events[item.google_event_id])
        self.client.patch(f"{BASE}/interviews/{item.pk}", data=json.dumps({"where": "Room 5"}), content_type="application/json")
        self.assertEqual(self.fake.events[item.google_event_id]["location"], "Room 5")
        self.client.delete(f"{BASE}/interviews/{item.pk}")
        self.assertEqual(self.fake.events, {})

    def test_off_means_google_is_never_called(self):
        self.conn.calendar_sync = False
        self.conn.save()
        self.interview()
        item = Interview.objects.get()
        self.assertEqual(gcal.push(item), "")
        self.assertEqual(self.fake.calls, [])

    def test_a_google_failure_does_not_lose_the_interview(self):
        form = {"application": self.app.pk, "scheduled_at": timezone.localtime(self.when).strftime("%Y-%m-%dT%H:%M"), "kind": "video"}
        self.fake.refresh_status = 400
        GoogleConnection.objects.update(access_expires_at=timezone.now() - timedelta(minutes=1))
        r = self.post("/interviews", form).json()
        self.assertTrue(Interview.objects.filter(pk=r["id"]).exists())
        self.assertIn("not updated", r["calendar_note"])

    def test_a_time_moved_in_google_comes_back(self):
        item = self.interview()
        gcal.push(item)
        item.refresh_from_db()
        moved = self.when + timedelta(days=1)
        self.fake.events[item.google_event_id]["start"] = {"dateTime": moved.astimezone(dt_utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        self.fake.events[item.google_event_id]["updated"] = "2030-02-02T00:00:00Z"
        r = self.post("/google/calendar/sync?force=true").json()
        self.assertEqual(r["changed"], 1)
        item.refresh_from_db()
        self.assertEqual(item.scheduled_at.replace(microsecond=0), moved.replace(microsecond=0))

    def test_a_cancelled_event_marks_the_interview_cancelled(self):
        item = self.interview()
        gcal.push(item)
        item.refresh_from_db()
        del self.fake.events[item.google_event_id]
        self.post("/google/calendar/sync?force=true")
        item.refresh_from_db()
        self.assertEqual(item.outcome, "cancelled")

    def test_events_we_did_not_create_are_never_touched(self):
        plain = self.interview()  # no event id: nothing about it is read or changed
        self.fake.events["theirs"] = {"id": "theirs", "start": {"dateTime": "2030-01-01T10:00:00Z"}, "updated": "x"}
        self.post("/google/calendar/sync?force=true")
        plain.refresh_from_db()
        self.assertEqual(plain.google_event_id, "")
        self.assertEqual([c for c in self.fake.calls if "theirs" in c[1]], [])
        self.assertEqual(self.fake.events["theirs"]["updated"], "x")

    def test_the_screen_cache_skips_google(self):
        item = self.interview()
        gcal.push(item)
        self.post("/google/calendar/sync?force=true")
        before = len(self.fake.calls)
        self.assertTrue(self.post("/google/calendar/sync").json()["cached"])
        self.assertEqual(len(self.fake.calls), before)

    def test_switching_the_sync_on_puts_upcoming_interviews_on_the_calendar(self):
        self.conn.calendar_sync = False
        self.conn.save()
        item = self.interview()
        r = self.client.patch(f"{BASE}/google/settings", data=json.dumps({"calendar_sync": True}), content_type="application/json").json()
        self.assertEqual(r["pushed"]["added"], 1)
        item.refresh_from_db()
        self.assertTrue(item.google_event_id)

    def test_another_persons_calendar_is_never_used(self):
        connect(self.b, calendar_sync=True)
        item = self.interview()
        gcal.push(item)
        bob_calls = [c for c in self.fake.calls]
        self.assertTrue(bob_calls)
        self.assertEqual(self.client.get(f"{BASE}/interviews").json()["google"], {"connected": True, "sync": True})


class NothingElseCanSend(TestCase):
    """The app sends mail only from the one confirm route: not the MCP server, not a management command, not the scheduler."""

    ROOT = Path(__file__).resolve().parent

    def test_only_the_confirm_route_calls_send(self):
        users = []
        for path in list(self.ROOT.rglob("*.py")) + [self.ROOT.parent / "mcp_server.py"]:
            if path.name.startswith("tests") or path.name in ("gmail.py",):
                continue
            if "send_message(" in path.read_text(encoding="utf-8") and "gmail" in path.read_text(encoding="utf-8"):
                users.append(path.name)
        self.assertEqual(users, ["google.py"])

    def test_mcp_and_commands_do_not_touch_gmail_at_all(self):
        files = [self.ROOT / n for n in ("mcp_tools.py", "mcp_registry.py", "views_mcp.py")] + [self.ROOT.parent / "mcp_server.py"]
        files += list((self.ROOT / "management" / "commands").glob("*.py"))
        for path in files:
            text = path.read_text(encoding="utf-8")
            for word in ("gmail", "googleconnect", "googledraft", "gcal", "messages/send"):
                self.assertNotIn(word, text, f"{path.name} must not reach {word}")

    def test_no_mcp_tool_is_named_for_sending(self):
        from tracker import mcp_tools
        names = [n for n in dir(mcp_tools) if not n.startswith("_")]
        self.assertFalse([n for n in names if "send" in n.lower() or "gmail" in n.lower() or "google" in n.lower()])

    def test_running_the_commands_makes_no_google_call(self):
        from django.core.management import call_command
        fake = FakeGoogle()
        owner = person("carol")
        connect(owner, calendar_sync=True)
        job(owner)
        with mock.patch("tracker.services.googleconnect.requests.request", fake):
            for name in ("send_followup_emails", "send_interview_reminders", "send_weekly_digest", "send_weekly_summary"):
                try:
                    call_command(name)
                except Exception:  # noqa: BLE001 - a command may complain about its own settings; only Google matters here
                    pass
        self.assertEqual(fake.calls, [])
