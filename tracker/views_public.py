"""The public side: landing page, job board, one opening's page, robots.txt and the sitemap. No sign-in needed.

Rules this follows (from the sources' own terms and from Google's job-posting guidelines):
  * only sources marked "show publicly" appear, never a person's own boards;
  * an opening nobody has seen for a few days is gone (410), not left up;
  * a short excerpt and a credit link to the original, never the full posting;
  * no JobPosting structured data: that markup needs the full description on the employer's own page, and several sources forbid
    passing their jobs to Google Jobs;
  * an opening's own page is not offered to search engines unless the admin switches that on (thin copied content).
"""
from xml.sax.saxutils import escape as xml_escape

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, HttpResponsePermanentRedirect
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET
from django.views.decorators.vary import vary_on_cookie

from .models import Posting, SiteConfig
from . import landing_content
from .services import geo, public


def public_cache(view):
    """Pages are the same for every visitor except the sign-in button, so they are cached briefly per cookie."""
    seconds = settings.STILLOPEN_PUBLIC_CACHE_SECONDS
    return vary_on_cookie(cache_page(seconds)(view)) if seconds else view


def _board_off(config) -> bool:
    return not config.public_board_enabled


@require_GET
@public_cache
def landing(request):
    config = SiteConfig.load()
    if not config.landing_enabled:
        return redirect("dashboard")
    context = {
        "config": config, "board_on": config.public_board_enabled, "features": landing_content.FEATURES,
        "comparison": landing_content.COMPARISON, "faq": landing_content.FAQ, "credits": [],
    }
    if config.public_board_enabled:
        public.refresh_if_stale()
        stats = public.stats()
        context.update({"stats": stats, "credits": stats["credits"], "latest": public.latest(8)})
        context["remote_share"] = round(100 * stats["remote"] / stats["total"]) if stats["total"] else 0
        context["kinds"] = [("Employer career pages", stats["boards"]), ("Remote job boards", stats["feeds"])] if stats["total"] else []
        context["country_rows"] = landing_content.country_rows(stats)
        context["day_rows"] = landing_content.day_rows(stats)
    else:
        context["stats"] = None
    return render(request, "tracker/landing.html", context)


def _filters(request):
    q = " ".join(request.GET.get("q", "").split())[:80]
    country = request.GET.get("country", "").strip().upper()
    if country and not (len(country) == 2 and country.isalpha()):
        country = ""
    return q, country, request.GET.get("remote") == "1"


@require_GET
@public_cache
def openings(request):
    config = SiteConfig.load()
    if _board_off(config):
        raise Http404("The public job board is switched off.")
    public.refresh_if_stale()
    q, country, remote = _filters(request)
    base = public.public_postings()
    qs = base
    for word in q.split():
        qs = qs.filter(Q(title__icontains=word) | Q(company__icontains=word) | Q(location__icontains=word))
    if country:
        qs = qs.filter(country=country)
    if remote:
        qs = qs.filter(remote=True)
    qs = qs.order_by("-first_seen_at", "-pk")
    page = Paginator(qs, settings.STILLOPEN_PUBLIC_PAGE_SIZE).get_page(request.GET.get("page"))
    countries = [
        {"code": row["country"], "name": geo.country_name(row["country"]), "n": row["n"]}
        for row in base.exclude(country="").values("country").annotate(n=Count("id")).order_by("-n")[:40]
    ]
    rows = [{"p": p, "credit": public.credit_for(p), "slug": public.slug_for(p), "where": public.location_label(p)} for p in page]
    keep = request.GET.copy()
    keep.pop("page", None)
    filtered = bool(q or country or remote)
    stats = public.stats()
    return render(request, "tracker/openings.html", {
        "config": config, "page": page, "rows": rows, "q": q, "country": country, "remote": remote, "countries": countries,
        "country_name": geo.country_name(country) if country else "", "total": paginator_total(page), "filtered": filtered,
        "qs": keep.urlencode(), "credits": stats["credits"], "stats": stats,
        # filtered and deep pages are for people, not search results
        "noindex": filtered or page.number > 1,
    })


def paginator_total(page) -> int:
    return page.paginator.count


def _active(pk):
    try:
        return public.public_postings().get(pk=pk)
    except Posting.DoesNotExist:
        return None


@require_GET
@public_cache
def opening_detail(request, pk, slug=""):
    config = SiteConfig.load()
    if _board_off(config):
        raise Http404("The public job board is switched off.")
    posting = _active(pk)
    if posting is None:
        # Seen before but not listed any more (or from a source that is not public): tell crawlers it is gone, not "maybe later".
        if Posting.objects.filter(pk=pk, source__owner__isnull=True, source__show_publicly=True).exists():
            stats = public.stats()
            return render(request, "tracker/opening_gone.html", {"config": config, "credits": stats["credits"]}, status=410)
        raise Http404("No such opening.")
    correct = public.slug_for(posting)
    if slug != correct:
        return HttpResponsePermanentRedirect(reverse("opening_detail", args=[posting.pk, correct]))
    credit = public.credit_for(posting)
    more = list(public.public_postings().filter(company=posting.company).exclude(pk=posting.pk).order_by("-first_seen_at")[:5])
    nearby = []
    if posting.country:
        nearby = list(public.public_postings().filter(country=posting.country).exclude(pk=posting.pk).exclude(company=posting.company).order_by("-first_seen_at")[:5])
    stats = public.stats()
    return render(request, "tracker/opening_detail.html", {
        "config": config, "p": posting, "slug": correct, "credit": credit, "where": public.location_label(posting), "country_name": geo.country_name(posting.country) if posting.country else "",
        "more": [{"p": m, "slug": public.slug_for(m), "where": public.location_label(m)} for m in more],
        "nearby": [{"p": m, "slug": public.slug_for(m), "where": public.location_label(m)} for m in nearby],
        "credits": stats["credits"], "indexable": config.public_details_indexable,
    })


@require_GET
def robots_txt(request):
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /dashboard/", "Disallow: /accounts/", "Disallow: /admin/", "Disallow: /api/", "Disallow: /profile/", "Disallow: /jobs/",
        "Disallow: /cv/", "Disallow: /cover/", "Disallow: /knowledge/", "Disallow: /interviews/", "Disallow: /contacts/", "Disallow: /offers/",
        "Disallow: /insights/", "Disallow: /sources/", "Disallow: /postings/", "Disallow: /welcome/", "Disallow: /referrals/", "Disallow: /documents/",
        "",
        f"Sitemap: {request.build_absolute_uri(reverse('sitemap'))}",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain; charset=utf-8")


SITEMAP_LIMIT = 45000  # the protocol allows 50,000 per file


@require_GET
@public_cache
def sitemap(request):
    config = SiteConfig.load()
    urls = [(request.build_absolute_uri(reverse(name)), None) for name in ("landing", "privacy", "terms")]
    if config.public_board_enabled:
        urls.append((request.build_absolute_uri(reverse("openings")), None))
        if config.public_details_indexable:
            for p in public.public_postings().order_by("-last_seen_at")[:SITEMAP_LIMIT]:
                urls.append((request.build_absolute_uri(reverse("opening_detail", args=[p.pk, public.slug_for(p)])), p.last_seen_at.date().isoformat()))
    body = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for loc, lastmod in urls:
        body.append(f"<url><loc>{xml_escape(loc)}</loc>" + (f"<lastmod>{lastmod}</lastmod>" if lastmod else "") + "</url>")
    body.append("</urlset>")
    return HttpResponse("\n".join(body), content_type="application/xml; charset=utf-8")
