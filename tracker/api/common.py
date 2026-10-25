"""Shared helpers for the API modules. Import from here, not from `routes.py` (which imports every module and would be circular)."""
from django.shortcuts import get_object_or_404
from ninja.errors import HttpError

from ..models import Application


def owned_job(request, pk) -> Application:
    """The person's own job or a 404, the same as the classic pages."""
    return get_object_or_404(Application, pk=pk, owner=request.user)


def owned(model, request, pk, field: str = "owner", **extra):
    """`model` row `pk` that belongs to the signed-in person (via `field`, default `owner`; use `application__owner` etc. for children), or a 404."""
    return get_object_or_404(model, pk=pk, **{field: request.user}, **extra)


def too_many() -> HttpError:
    return HttpError(429, "Too many requests. Try again later.")


def throttle(request, action: str, limit: int, window: int = 3600) -> None:
    """Raise 429 when this person has already done `action` `limit` times within `window` seconds (per server process, like the classic pages)."""
    from ..services.throttle import throttled

    if throttled(request.user, action, limit, window):
        raise too_many()


class ApiFormError(Exception):
    """A form refused the input. Becomes `400 {"error": "<first message>", "fields": {"name": ["message", ...]}}`."""

    def __init__(self, errors: dict[str, list[str]], message: str | None = None):
        self.fields = errors
        first = next((m for msgs in errors.values() for m in msgs), "Please check what you entered.")
        super().__init__(message or first)


def validate_form(form) -> None:
    """Run a Django form that was built from the request's JSON; raise `ApiFormError` with its field messages if it is not valid.

    Using the classic pages' own forms keeps every rule (limits, clean methods, owner-limited choices) in one place."""
    if not form.is_valid():
        errors = {name: [str(m) for m in msgs] for name, msgs in form.errors.items()}
        raise ApiFormError(errors)

