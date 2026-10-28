"""Make two people with a few jobs each, for the browser tests in frontend/e2e. Refuses to run unless STILLOPEN_E2E=1 is set,
so a real install can never get a user with a known password from this command."""
import os
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from django.utils import timezone

from tracker.models import Application, CVVersion, Interview, JobSource, Notification, Posting, ScanLogEntry, ScanRun, SiteConfig, Status, UserProfile

CV = """# Alice Example

## Summary
Backend engineer building payment systems.

## Experience
**Acme Payments** - Backend Engineer, 2019 to now
- Built payment APIs in Python and SQL serving 10,000 merchants.
- Set up Docker based CI for the payments service.
"""
PASSWORD = "e2e-pass-12345"  # test-only value; the users exist only in the throwaway database these tests start


class Command(BaseCommand):
    help = "Create the e2e people (alice, bob, carol, dave, erin, frank and grace). Needs STILLOPEN_E2E=1. --demo also adds Jane Doe and a public board, for the README screenshots."

    def add_arguments(self, parser):
        parser.add_argument("--demo", action="store_true", help="Also make the demo person (jane, 9 jobs across the stages) and a few public openings. Used by `pnpm readme:images` only.")

    def handle(self, *args, **options):
        if os.environ.get("STILLOPEN_E2E") != "1":
            raise CommandError("Set STILLOPEN_E2E=1 to run this. It creates users with a known password and is only for the browser tests.")
        User = get_user_model()
        SiteConfig.objects.filter(pk=SiteConfig.load().pk).update(signup_mode="open")  # the hardening spec looks at the sign-up page itself
        statuses = {s.name: s for s in Status.objects.all()}
        today = timezone.localdate()
        for name, jobs in (
            (
                "alice",
                [
                    # a job with a description (so "Check my fit" shows), one with a link and a close deadline, one already applied to with a follow-up due
                    ("Acme", "Backend Engineer", "Saved", 4.2, {"description": "We need a backend engineer who knows Python and Django.", "advertised_pay": "USD 90k"}),
                    ("Globex", "Platform Engineer", "Evaluated", 3.1, {"url": "https://jobs.example.com/platform", "deadline": today + timedelta(days=3), "arrangement": "remote", "live_state": "active", "live_detail": "The page still loads."}),
                    ("Initech", "API Developer", "Applied", 4.8, {"applied_date": today - timedelta(days=4), "applied_channel": "email", "follow_up_date": today}),
                ],
            ),
            ("bob", [("SecretCo", "Hidden Role", "Saved", 3.0)]),
            ("carol", []),  # has not seen the welcome questions yet
            ("dave", [("Umbrella", "SRE", "Saved", 3.5)]),  # the account the delete test removes
            ("erin", []),  # the welcome-questions test saves her answers
            ("frank", []),  # the CV builder test builds his CV (so bob stays a person with no CV)
            ("grace", [("Hooli", "Backend Engineer", "Saved", 4.5)]),  # has a CV draft the scheduled search prepared (draftahead spec)
            ("heidi", []),  # has notices in the bell (notifications spec)
        ):
            user, _ = User.objects.get_or_create(username=name, defaults={"email": f"{name}@example.com"})
            user.set_password(PASSWORD)
            user.save()
            UserProfile.objects.filter(user=user).update(
                onboarding_done=name not in ("carol", "erin"), target_roles="Backend Engineer", home_country="MY",
                profile_cv=CV if name == "alice" else "",  # alice can tailor a CV in the parity specs
            )
            Application.objects.filter(owner=user).delete()
            ScanRun.objects.filter(owner=user).delete()
            for company, role, status, score, *extra in jobs:
                Application.objects.create(owner=user, company=company, role=role, status=statuses[status], score=score, summary=f"A role at {company}", **(extra[0] if extra else {}))
            if name == "alice":
                applied = Application.objects.get(owner=user, company="Initech")
                Interview.objects.create(owner=user, application=applied, scheduled_at=timezone.now() + timedelta(days=1), kind="video")
                run = ScanRun.objects.create(owner=user, running=False, total=2, done=2, found=40, added=3, note="Only the best matches were added.")
                ScanLogEntry.objects.create(run=run, source_name="Acme Careers", connector="greenhouse", found=30, matched=6, added=3, duplicates=1, outside=2)
                ScanLogEntry.objects.create(run=run, source_name="Broken Board", connector="lever", error="The board did not answer.")
                # a startup post from Hacker News that publishes an apply address: listed under All postings (the spec adds it to the tracker)
                hn, _ = JobSource.objects.get_or_create(connector="hnhiring", board_token="all", owner=None, defaults={"name": "Startups: Hacker News", "enabled": False})
                Posting.objects.get_or_create(
                    source=hn, url="https://news.ycombinator.com/item?id=1000001",
                    defaults={"title": "Founding Backend Engineer", "company": "Launchpad Labs", "title_key": "launchpad labs founding backend engineer",
                              "location": "Remote (EU)", "apply_address": "jobs@launchpad.example"},
                )
        heidi = User.objects.get(username="heidi")
        Notification.objects.filter(owner=heidi).delete()
        UserProfile.objects.filter(user=heidi).update(notify_muted=[])
        Notification.objects.create(owner=heidi, kind="search", title="Your search found 3 new jobs", text="Open your dashboard to see them, best match first.", link="/")
        Notification.objects.create(owner=heidi, kind="closed", title="Acme: the posting looks closed", text="Backend Engineer. Check the page before you spend time on it.", link="/jobs/1/edit")
        Notification.objects.create(owner=heidi, kind="followup", title="Follow up with Initech", text="API Developer. The date you set has come.", read_at=timezone.now() - timedelta(days=2), created_at=timezone.now() - timedelta(days=2))
        grace = User.objects.get(username="grace")
        CVVersion.objects.filter(owner=grace).delete()
        master = CVVersion.objects.create(owner=grace, kind="master", content=CV, label="Initial CV", approved=True)
        CVVersion.objects.create(
            owner=grace, application=Application.objects.get(owner=grace), parent=master, kind="tailored", source="ai", label="Hooli - Backend Engineer",
            content=CV + "- Led a team of 40 engineers.\n", draft_ahead=True,
            check_report=[{"kind": "number", "text": "40", "line": 12}],
        )
        if options["demo"]:
            self.seed_demo(User, statuses, today)
        self.stdout.write("Seeded alice, bob, carol, dave, erin, frank, grace and heidi" + (", and the demo person jane." if options["demo"] else "."))

    def seed_demo(self, User, statuses, today):
        """Jane Doe: an invented person with nine jobs across the stages, one tailored CV with a flagged claim and a few public openings,
        so the README pictures show a realistic search and no real person. Separate from the people above (no existing spec sees her)."""
        jane, _ = User.objects.get_or_create(username="jane", defaults={"email": "jane@example.com", "first_name": "Jane", "last_name": "Doe"})
        jane.first_name, jane.last_name = "Jane", "Doe"
        jane.set_password(PASSWORD)
        jane.save()
        UserProfile.objects.filter(user=jane).update(onboarding_done=True, target_roles="Backend Engineer, Platform Engineer", home_country="MY", profile_cv=CV)
        Application.objects.filter(owner=jane).delete()
        ScanRun.objects.filter(owner=jane).delete()
        d = timedelta
        rows = [
            ("Northwind", "Senior Backend Engineer", "Evaluated", 4.6, {"arrangement": "remote", "live_state": "active", "live_detail": "The page still loads.", "country": "MY", "advertised_pay": "MYR 18k a month", "found_date": today - d(days=1), "description": "Build payment APIs in Python and Django. Docker, SQL and CI.", "url": "https://jobs.example.com/northwind/backend"}),
            ("Contoso Pay", "Python Developer", "Evaluated", 4.3, {"arrangement": "hybrid", "live_state": "active", "live_detail": "The page still loads.", "country": "MY", "found_date": today - d(days=2), "description": "Python, Django and PostgreSQL for a payments team.", "url": "https://jobs.example.com/contoso/python"}),
            ("Fabrikam", "Platform Engineer", "Evaluated", 3.4, {"arrangement": "remote", "live_state": "expired", "live_detail": "The posting says it is no longer taking applications.", "found_date": today - d(days=6), "url": "https://jobs.example.com/fabrikam/platform"}),
            ("Tailspin", "API Engineer", "Saved", 3.9, {"arrangement": "remote", "live_state": "uncertain", "live_detail": "The page loads but does not say if the role is open.", "found_date": today - d(days=3), "url": "https://jobs.example.com/tailspin/api"}),
            ("Adventure Works", "Backend Engineer", "Applied", 4.4, {"applied_date": today - d(days=9), "applied_channel": "email", "follow_up_date": today + d(days=2), "found_date": today - d(days=12), "live_state": "active", "url": "https://jobs.example.com/adventure/backend"}),
            ("Wingtip", "Software Engineer, Payments", "Applied", 4.1, {"applied_date": today - d(days=5), "applied_channel": "other", "found_date": today - d(days=8), "live_state": "active", "url": "https://jobs.example.com/wingtip/payments"}),
            ("Litware", "Senior Python Engineer", "Interview", 4.7, {"applied_date": today - d(days=15), "applied_channel": "referral", "found_date": today - d(days=20), "live_state": "active", "url": "https://jobs.example.com/litware/python"}),
            ("Proseware", "Staff Backend Engineer", "Offer", 4.9, {"applied_date": today - d(days=30), "applied_channel": "other", "found_date": today - d(days=36), "live_state": "active", "url": "https://jobs.example.com/proseware/staff"}),
            ("Lucerne", "Data Platform Engineer", "Rejected", 3.2, {"applied_date": today - d(days=21), "applied_channel": "email", "found_date": today - d(days=26), "live_state": "expired", "url": "https://jobs.example.com/lucerne/data"}),
        ]
        for company, role, status, score, extra in rows:
            Application.objects.create(owner=jane, company=company, role=role, status=statuses[status], score=score, summary=f"A role at {company}", **extra)
        Interview.objects.create(owner=jane, application=Application.objects.get(owner=jane, company="Litware"), scheduled_at=timezone.now() + timedelta(days=2), kind="video")
        run = ScanRun.objects.create(owner=jane, running=False, total=3, done=3, found=212, added=4, note="Only the best matches were added.")
        ScanLogEntry.objects.create(run=run, source_name="Northwind Careers", connector="greenhouse", found=64, matched=5, added=2, duplicates=1, outside=8)
        ScanLogEntry.objects.create(run=run, source_name="Remote jobs feed", connector="remoteok", found=148, matched=9, added=2, duplicates=3, outside=40)
        CVVersion.objects.filter(owner=jane).delete()
        master = CVVersion.objects.create(owner=jane, kind="master", content=CV, label="Initial CV", approved=True)
        CVVersion.objects.create(
            owner=jane, application=Application.objects.get(owner=jane, company="Northwind"), parent=master, kind="tailored", source="ai",
            label="Northwind - Senior Backend Engineer", content=CV + "- Led a team of 40 engineers.\n", check_report=[{"kind": "number", "text": "40", "line": 12}],
        )
        # a public board for the openings screenshot: invented employers on a made-up source, nothing fetched from anywhere
        board, _ = JobSource.objects.get_or_create(connector="greenhouse", board_token="demo-board", owner=None, defaults={"name": "Demo Careers", "enabled": True, "show_publicly": True})
        JobSource.objects.filter(pk=board.pk).update(enabled=True, show_publicly=True)
        for i, (company, title, place, remote) in enumerate([
            ("Northwind", "Senior Backend Engineer", "Kuala Lumpur, Malaysia", False), ("Contoso Pay", "Python Developer", "Remote (Asia)", True),
            ("Litware", "Platform Engineer", "Dubai, UAE", False), ("Tailspin", "API Engineer", "Remote", True), ("Wingtip", "Site Reliability Engineer", "Dhaka, Bangladesh", False),
            ("Adventure Works", "Data Engineer", "Remote (Worldwide)", True), ("Fabrikam", "Security Engineer", "Singapore", False),
        ]):
            Posting.objects.get_or_create(
                source=board, url=f"https://jobs.example.com/demo/{i}",
                defaults={"title": title, "company": company, "title_key": f"{company} {title}".lower(), "location": place, "remote": remote,
                          "excerpt": f"{company} is hiring a {title.lower()} to join a small, friendly team."},
            )
