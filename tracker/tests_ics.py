"""Calendar files for interviews: valid RFC 5545 output (checked by a small strict parser), escaping, folding, isolation, sign-in required."""
import datetime as dt

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from tracker.models import Interview
from tracker.services import ics
from tracker.tests_api import job, person

WHEN = dt.datetime(2026, 11, 3, 14, 30, tzinfo=dt.timezone.utc)


def unfold(text: str) -> list[str]:
    """Strict: CRLF only, no physical line over 75 octets, continuation lines start with one space or tab."""
    assert text.endswith("\r\n"), "must end with CRLF"
    body = text[:-2]
    assert "\n" not in body.replace("\r\n", "") and "\r" not in body.replace("\r\n", ""), "bare CR or LF"
    lines: list[str] = []
    for physical in body.split("\r\n"):
        assert len(physical.encode("utf-8")) <= 75, f"line over 75 octets: {physical!r}"
        if physical[:1] in (" ", "\t"):
            assert lines, "continuation with nothing before it"
            lines[-1] += physical[1:]
        else:
            lines.append(physical)
    return lines


def parse(text: str):
    """The VCALENDAR as (name, [(property, value)], [children]); raises on any structural error."""
    stack = [("ROOT", [], [])]
    for line in unfold(text):
        assert ":" in line, line
        name, _, value = line.partition(":")
        key = name.split(";")[0]
        if key == "BEGIN":
            node = (value, [], [])
            stack[-1][2].append(node)
            stack.append(node)
        elif key == "END":
            assert stack[-1][0] == value, f"END:{value} closes {stack[-1][0]}"
            stack.pop()
        else:
            assert key.replace("-", "").isalnum() and key == key.upper(), key
            stack[-1][1].append((key, value))
    assert len(stack) == 1, "unclosed component"
    return stack[0][2][0]


def props(node):
    return dict(node[1])


class Writing(SimpleTestCase):
    def test_escaping(self):
        self.assertEqual(ics.escape_text("a, b; c\\d\nline two\r\nthree"), "a\\, b\\; c\\\\d\\nline two\\nthree")
        self.assertEqual(ics.escape_text("bell\x07 ok"), "bell ok")

    def test_folding_at_75_octets_never_inside_a_character(self):
        long = "DESCRIPTION:" + "é" * 120 + "x" * 30
        parts = ics.fold_line(long).split("\r\n")
        for physical in parts:
            self.assertLessEqual(len(physical.encode("utf-8")), 75)
        self.assertTrue(all(p.startswith(" ") for p in parts[1:]))
        self.assertEqual(parts[0] + "".join(p[1:] for p in parts[1:]), long)
        self.assertEqual(ics.fold_line("SHORT:line"), "SHORT:line")
        exactly = "X:" + "a" * 73
        self.assertEqual(ics.fold_line(exactly), exactly)

    def test_utc_stamp(self):
        self.assertEqual(ics.utc_stamp(WHEN), "20261103T143000Z")
        self.assertEqual(ics.utc_stamp(WHEN.astimezone(dt.timezone(dt.timedelta(hours=6)))), "20261103T143000Z")


class Content(TestCase):
    def setUp(self):
        self.a = person("alice")
        self.app = job(self.a, company="Acme, Inc.", role="Dev; Backend")
        self.item = Interview.objects.create(
            owner=self.a, application=self.app, scheduled_at=WHEN, kind="technical", where="Room 4, 2nd floor; https://meet.example/x",
            notes="Meet Sam.\nBring a laptop, charger; and \\ stuff. " + "Long note. " * 20,
        )

    def test_a_valid_calendar_with_one_event_and_two_reminders(self):
        now = dt.datetime(2026, 10, 25, 12, 0, tzinfo=dt.timezone.utc)
        root = parse(ics.calendar([self.item], now=now))
        self.assertEqual(root[0], "VCALENDAR")
        head = props(root)
        self.assertEqual((head["VERSION"], head["METHOD"]), ("2.0", "PUBLISH"))
        self.assertTrue(head["PRODID"].startswith("-//"))
        (event,) = root[2]
        e = props(event)
        self.assertEqual(e["UID"], f"interview-{self.item.pk}@stillopen")
        self.assertEqual((e["DTSTAMP"], e["DTSTART"], e["DTEND"]), ("20261025T120000Z", "20261103T143000Z", "20261103T160000Z"))  # technical: 90 minutes
        self.assertEqual(e["SUMMARY"], "Interview: Dev\\; Backend at Acme\\, Inc.")
        self.assertEqual(e["LOCATION"], "Room 4\\, 2nd floor\\; https://meet.example/x")
        self.assertIn("Kind: Technical round", e["DESCRIPTION"])
        self.assertIn("Bring a laptop\\, charger\\; and \\\\ stuff.", e["DESCRIPTION"])
        self.assertIn("\\n", e["DESCRIPTION"])
        alarms = [c for c in event[2] if c[0] == "VALARM"]
        self.assertEqual([props(a)["TRIGGER"] for a in alarms], ["-P1D", "-PT1H"])
        self.assertTrue(all(props(a)["ACTION"] == "DISPLAY" and "DESCRIPTION" in props(a) for a in alarms))

    def test_default_lengths_by_kind(self):
        for kind, minutes in ics.DEFAULT_MINUTES.items():
            self.item.kind = kind
            e = props(parse(ics.calendar([self.item]))[2][0])
            start = dt.datetime.strptime(e["DTSTART"], "%Y%m%dT%H%M%SZ")
            end = dt.datetime.strptime(e["DTEND"], "%Y%m%dT%H%M%SZ")
            self.assertEqual((end - start).seconds // 60, minutes, kind)

    def test_an_empty_calendar_is_still_valid(self):
        self.assertEqual(parse(ics.calendar([]))[2], [])


class Downloads(TestCase):
    def setUp(self):
        self.a, self.b = person("alice"), person("bob")
        self.ja, self.jb = job(self.a, company="AliceCo"), job(self.b, company="BobCo")
        soon = timezone.now() + dt.timedelta(days=2)
        self.i1 = Interview.objects.create(owner=self.a, application=self.ja, scheduled_at=soon, kind="video")
        self.i2 = Interview.objects.create(owner=self.a, application=self.ja, scheduled_at=soon + dt.timedelta(days=1), kind="phone")
        Interview.objects.create(owner=self.a, application=self.ja, scheduled_at=timezone.now() - dt.timedelta(days=2))
        Interview.objects.create(owner=self.a, application=self.ja, scheduled_at=soon, outcome="cancelled")
        self.theirs = Interview.objects.create(owner=self.b, application=self.jb, scheduled_at=soon)

    def test_signed_out_goes_to_sign_in(self):
        for url in (f"/interviews/{self.i1.pk}/calendar.ics", "/interviews/calendar.ics"):
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302)
            self.assertIn("/accounts/login/", r["Location"])

    def test_one_interview_downloads_as_an_attachment_and_is_not_cached(self):
        self.client.force_login(self.a)
        r = self.client.get(f"/interviews/{self.i1.pk}/calendar.ics")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r["Content-Type"].startswith("text/calendar"))
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertIn(".ics", r["Content-Disposition"])
        self.assertIn("no-store", r["Cache-Control"])
        self.assertEqual(len(parse(r.content.decode())[2]), 1)

    def test_someone_elses_interview_is_a_404(self):
        self.client.force_login(self.a)
        self.assertEqual(self.client.get(f"/interviews/{self.theirs.pk}/calendar.ics").status_code, 404)
        self.client.force_login(self.b)
        self.assertEqual(self.client.get(f"/interviews/{self.i1.pk}/calendar.ics").status_code, 404)

    def test_all_means_only_my_pending_upcoming_ones_soonest_first(self):
        self.client.force_login(self.a)
        r = self.client.get("/interviews/calendar.ics")
        body = r.content.decode()
        uids = [props(e)["UID"] for e in parse(body)[2]]
        self.assertEqual(uids, [f"interview-{self.i1.pk}@stillopen", f"interview-{self.i2.pk}@stillopen"])
        self.assertNotIn("BobCo", body)
        self.assertIn("attachment", r["Content-Disposition"])
        self.assertIn("no-store", r["Cache-Control"])

    def test_post_is_not_allowed(self):
        self.client.force_login(self.a)
        self.assertEqual(self.client.post("/interviews/calendar.ics").status_code, 405)
