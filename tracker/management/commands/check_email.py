from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.mail import send_mail
from django.core.management.base import BaseCommand, CommandError

from tracker.services import integrations


class Command(BaseCommand):
    help = (
        "Show how email is set up and send one test message, so you find out now (not when a candidate signs up) whether "
        "SMTP works. Never prints the password."
    )

    def add_arguments(self, parser):
        parser.add_argument("--to", help="Where to send the test (default: the first superuser's email).")
        parser.add_argument("--no-send", action="store_true", help="Only show the settings.")

    def handle(self, *args, **opts):
        backend = settings.EMAIL_BACKEND.rsplit(".", 1)[-1]
        cfg = integrations.email_settings()
        if cfg is None:
            self.stdout.write(self.style.WARNING(
                "Email is NOT set up. Messages are only printed to this console, so nobody receives them.\n"
                "Fill in Site configuration > Email sending in the admin (or set EMAIL_HOST and friends in .env), then run this again.\n"
                f"Consequence today: new sign-ups are not email-verified (confirmation is {'on' if integrations.require_email_confirmation() else 'off'})."
            ))
            return
        self.stdout.write(
            f"Backend: {backend} (settings from the {cfg.source})\nServer:  {cfg.host}:{cfg.port} (TLS {'on' if cfg.use_tls else 'off'})\n"
            f"Login:   {cfg.username or '(none)'}\nFrom:    {cfg.from_email}"
        )
        if opts["no_send"]:
            return
        recipient = opts["to"]
        if not recipient:
            admin = get_user_model().objects.filter(is_superuser=True).exclude(email="").order_by("pk").first()
            recipient = admin.email if admin else ""
        if not recipient:
            raise CommandError("No address to send to. Pass --to you@example.com.")
        try:
            send_mail(
                "StillOpen: test email", "If you can read this, StillOpen can send email.\n\nSign-up confirmations, interview reminders, "
                "follow-ups and job alerts will reach people.", cfg.from_email, [recipient], fail_silently=False,
            )
        except Exception as exc:  # noqa: BLE001 - the reason is the whole point of this command
            raise CommandError(f"Sending failed: {exc.__class__.__name__}: {exc}") from exc
        self.stdout.write(self.style.SUCCESS(f"Sent a test email to {recipient}. Check that inbox (and spam)."))
