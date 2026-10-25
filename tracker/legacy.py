"""Old addresses from the classic pages, kept alive: each one sends the browser to the same screen in the app (/app/).

Bookmarks, old emails and links from other sites keep working. Only GET (and HEAD) is answered, with a temporary redirect that
keeps the query string; anything else gets 405. The app itself asks people to sign in when they are not, so an anonymous visitor
ends up at the sign-in page and then on the right screen."""
from django.http import HttpResponseNotAllowed
from django.shortcuts import redirect
from django.urls import path
from django.views.decorators.csrf import csrf_exempt

# old address (Django path syntax) -> new address (the same converters fill the placeholders)
REDIRECTS = {
    "dashboard/": "/app/",
    "welcome/": "/app/welcome",
    "jobs/add/": "/app/jobs/add",
    "postings/": "/app/postings",
    "jobs/<int:pk>/edit/": "/app/jobs/{pk}/edit",
    "jobs/<int:pk>/apply/": "/app/jobs/{pk}/apply",
    "profile/": "/app/profile",
    "profile/ai/": "/app/profile/ai",
    "profile/assistant/": "/app/profile/assistant",
    "sources/": "/app/sources",
    "knowledge/": "/app/knowledge",
    "cv/": "/app/cv",
    "cv/<int:pk>/": "/app/cv/{pk}",
    "cv/<int:pk>/diff/": "/app/cv/{pk}/diff",
    "cover/<int:pk>/": "/app/cover/{pk}",
    "interviews/": "/app/interviews",
    "contacts/": "/app/contacts",
    "offers/": "/app/offers",
    "insights/": "/app/insights",
    "prep/": "/app/prep",
    "prep/<int:pk>/": "/app/prep/{pk}",
    "prep/<int:pk>/today/": "/app/prep/{pk}/today",
}


def _make(target: str):
    @csrf_exempt  # nothing is changed here, so a stale form post gets a plain 405 instead of a CSRF error
    def view(request, **kwargs):
        if request.method not in ("GET", "HEAD"):
            return HttpResponseNotAllowed(["GET", "HEAD"])
        url = target.format(**kwargs)
        query = request.META.get("QUERY_STRING", "")
        return redirect(f"{url}?{query}" if query else url)

    return view


urlpatterns = [path(old, _make(new)) for old, new in REDIRECTS.items()]
