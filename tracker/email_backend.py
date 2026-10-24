"""The email backend: sends through whatever the owner configured at the time of sending (see services/integrations.py)."""
from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail.backends.console import EmailBackend as ConsoleBackend
from django.core.mail.backends.smtp import EmailBackend as SmtpBackend

from .services import integrations


class ConfiguredBackend(BaseEmailBackend):
    def _real(self):
        cfg = integrations.email_settings()
        if cfg is None:
            return ConsoleBackend(fail_silently=self.fail_silently)
        return SmtpBackend(host=cfg.host, port=cfg.port, username=cfg.username, password=cfg.password, use_tls=cfg.use_tls,
                           fail_silently=self.fail_silently, timeout=20)

    def send_messages(self, email_messages):
        return self._real().send_messages(email_messages)
