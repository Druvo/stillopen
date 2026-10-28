"""The opt-in Google connection: one per person, tokens encrypted at rest, plus the few facts kept from replies.

Imported at the end of models.py so Django registers these with the rest of the app."""
from django.conf import settings
from django.db import models
from django.utils import timezone

from tracker import crypto


class GoogleConnection(models.Model):
    """A person's own Google account, connected by them (services/googleconnect.py). Never shared, never readable through any API."""

    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="google_connection")
    refresh_token_encrypted = models.TextField(blank=True, editable=False)
    access_token_encrypted = models.TextField(blank=True, editable=False)
    access_expires_at = models.DateTimeField(null=True, blank=True, editable=False)
    scopes = models.JSONField(default=list, blank=True, editable=False)
    email = models.CharField(max_length=254, blank=True, help_text="The Google address that was connected (shown to the person, so they know which account it is).")
    connected_at = models.DateTimeField(default=timezone.now)
    calendar_sync = models.BooleanField(default=False, help_text="Keep the person's Google Calendar in step with their interviews.")
    calendar_synced_at = models.DateTimeField(null=True, blank=True, editable=False)
    last_error = models.CharField(max_length=300, blank=True, editable=False)

    def __str__(self):
        return f"Google connection of {self.owner_id}"

    @property
    def refresh_token(self) -> str:
        return crypto.decrypt(self.refresh_token_encrypted)

    @property
    def access_token(self) -> str:
        return crypto.decrypt(self.access_token_encrypted)

    def set_tokens(self, access: str, expires_at, refresh: str | None = None) -> None:
        self.access_token_encrypted = crypto.encrypt(access)
        self.access_expires_at = expires_at
        if refresh:
            self.refresh_token_encrypted = crypto.encrypt(refresh)


class MailMessage(models.Model):
    """One message seen in a job's Gmail conversation. Only who, when, a short snippet and the id: never the whole body."""

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mail_messages")
    application = models.ForeignKey("tracker.Application", on_delete=models.CASCADE, related_name="mail_messages")
    gmail_id = models.CharField(max_length=64)
    sender = models.CharField(max_length=300, blank=True)
    sent_at = models.DateTimeField()
    snippet = models.CharField(max_length=300, blank=True)
    from_me = models.BooleanField(default=False)

    class Meta:
        ordering = ["sent_at", "id"]
        constraints = [models.UniqueConstraint(fields=["application", "gmail_id"], name="one_mail_row_per_message")]

    def __str__(self):
        return f"Message {self.gmail_id} for job {self.application_id}"
