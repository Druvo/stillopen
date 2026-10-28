"""Make two people with a few jobs each, for the browser tests in frontend/e2e. Refuses to run unless STILLOPEN_E2E=1 is set,
so a real install can never get a user with a known password from this command."""
import os
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from django.utils import timezone

from tracker.models import Application, Interview, JobSource, Posting, ScanLogEntry, ScanRun, Status, UserProfile

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
    help = "Create the e2e people (alice, bob, carol, dave and erin) Needs STILLOPEN_E2E=1."

    def handle(self, *args, **options):
        if os.environ.get("STILLOPEN_E2E") != "1":
            raise CommandError("Set STILLOPEN_E2E=1 to run this. It creates users with a known password and is only for the browser tests.")
        User = get_user_model()
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
                post, _ = Posting.objects.get_or_create(
                    source=hn, url="https://news.ycombinator.com/item?id=1000001",
                    defaults={"title": "Founding Backend Engineer", "company": "Launchpad Labs", "title_key": "launchpad labs founding backend engineer",
                              "location": "Remote (EU)", "apply_address": "jobs@launchpad.example"},
                )
        self.stdout.write("Seeded alice, bob, carol, dave and erin.")
