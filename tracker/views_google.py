"""Where Google sends the person back after they allowed (or refused) the connection. A page, not JSON: it is a browser redirect."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.decorators.http import require_GET

from .services import googleconnect
from .services.googleconnect import GoogleError

BACK = "/app/profile/connections"


@login_required
@require_GET
def google_callback(request):
    if request.GET.get("error"):
        request.session.pop(googleconnect.SESSION_KEY, None)
        request.session["google_flash"] = "Google was not connected: you did not allow it."
        return redirect(BACK)
    try:
        googleconnect.finish(request, request.GET.get("state", ""), request.GET.get("code", ""))
        request.session["google_flash"] = "Your Google account is connected."
    except GoogleError as exc:
        request.session["google_flash"] = str(exc)
    return redirect(BACK)
