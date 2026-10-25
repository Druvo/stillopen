"""Make two people with a few jobs each, for the browser tests in frontend/e2e. Refuses to run unless STILLOPEN_E2E=1 is set,
so a real install can never get a user with a known password from this command."""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from tracker.models import Application, SiteConfig, Status, UserProfile

PASSWORD = "e2e-pass-12345"  # test-only value; the users exist only in the throwaway database these tests start


class Command(BaseCommand):
    help = "Create the e2e people (alice and bob) and turn the new app on. Needs STILLOPEN_E2E=1."

    def handle(self, *args, **options):
        if os.environ.get("STILLOPEN_E2E") != "1":
            raise CommandError("Set STILLOPEN_E2E=1 to run this. It creates users with a known password and is only for the browser tests.")
        User = get_user_model()
        SiteConfig.objects.update(new_app_enabled=True)
        statuses = {s.name: s for s in Status.objects.all()}
        for name, jobs in (
            ("alice", [("Acme", "Backend Engineer", "Saved", 4.2), ("Globex", "Platform Engineer", "Evaluated", 3.1), ("Initech", "API Developer", "Applied", 4.8)]),
            ("bob", [("SecretCo", "Hidden Role", "Saved", 3.0)]),
        ):
            user, _ = User.objects.get_or_create(username=name, defaults={"email": f"{name}@example.com"})
            user.set_password(PASSWORD)
            user.save()
            UserProfile.objects.filter(user=user).update(use_new_app=True, onboarding_done=True, target_roles="Backend Engineer", home_country="MY")
            Application.objects.filter(owner=user).delete()
            for company, role, status, score in jobs:
                Application.objects.create(owner=user, company=company, role=role, status=statuses[status], score=score, summary=f"A role at {company}")
        self.stdout.write("Seeded alice and bob.")
