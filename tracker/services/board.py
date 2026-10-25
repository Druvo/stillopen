"""Moving a job between statuses. One rule, shared by the classic page, the JSON API and the board's drag-and-drop."""
from django.utils import timezone

from ..models import Event


def change_status(app, status) -> bool:
    """Set `app.status`, stamp the applied date for statuses that count as applied and write the timeline event.

    Returns False when nothing changed (the job was already there)."""
    if app.status_id == status.pk:
        return False
    app.status = status
    if status.counts_as_applied and not app.applied_date:
        app.applied_date = timezone.localdate()
    app.save()
    Event.objects.create(
        application=app,
        kind="applied" if status.counts_as_applied else "status",
        text=f"Status set to {status.name}",
    )
    return True
