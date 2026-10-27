"""The public side: landing page, job board, one opening's page, robots.txt and the sitemap. No sign-in needed.

Rules this follows (from the sources' own terms and from Google's job-posting guidelines):
  * only sources marked "show publicly" appear, never a person's own boards;
  * an opening nobody has seen for a few days is gone (410), not left up;
  * a short excerpt and a credit link to the original, never the full posting;
  * no JobPosting structured data: that markup needs the full description on the employer's own page, and several sources forbid
    passing their jobs to Google Jobs;
  * an opening's own page is not offered to search engines unless the admin switches that on (thin copied content).
"""
from datetime import timedelta
from xml.sax.saxutils import escape as xml_escape

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404, HttpResponse, HttpResponsePermanentRedirect
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.feedgenerator import Rss201rev2Feed
from django.urls import reverse
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET
from django.views.decorators.vary import vary_on_cookie

from .models import Posting, SiteConfig
from . import landing_content
from .services import countries as countries_all, geo, public


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
        return redirect("/app/")
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


TYPES = [("full_time", "Full-time"), ("part_time", "Part-time"), ("contract", "Contract"), ("freelance", "Freelance"), ("internship", "Internship")]
LEVELS = [("junior", "Junior"), ("mid", "Mid-level"), ("senior", "Senior"), ("lead", "Lead or staff"), ("principal", "Principal or architect"), ("manager", "Manager")]
WITHIN = [("1", "Last 24 hours"), ("3", "Last 3 days"), ("7", "Last week"), ("30", "Last month")]


def _filters(request):
    """Every filter, cleaned: unknown values are dropped rather than trusted."""
    get = request.GET
    country = get.get("country", "").strip().upper()
    if country not in countries_all.ALL:
        country = ""
    pick = lambda key, options: get.get(key, "") if get.get(key, "") in dict(options) else ""
    return {
        "q": " ".join(get.get("q", "").split())[:80],
        "country": country,
        "remote": get.get("remote") == "1",
        "visa": get.get("visa") == "1",
        "relocation": get.get("relocation") == "1",
        "type": pick("type", TYPES),
        "level": pick("level", LEVELS),
        "within": pick("within", WITHIN),
    }


@require_GET
@public_cache
def openings(request):
    config = SiteConfig.load()
    if _board_off(config):
        raise Http404("The public job board is switched off.")
    public.refresh_if_stale()
    f = _filters(request)
    q, country, remote = f["q"], f["country"], f["remote"]
    base = public.public_postings()
    qs = base
    for word in q.split():
        qs = qs.filter(Q(title__icontains=word) | Q(company__icontains=word) | Q(location__icontains=word))
    if country:
        qs = qs.filter(country=country)
    if remote:
        qs = qs.filter(remote=True)
    if f["visa"]:
        qs = qs.filter(sponsorship="yes")
    if f["relocation"]:
        qs = qs.filter(relocation="yes")
    if f["type"]:
        qs = qs.filter(employment_type=f["type"])
    if f["level"]:
        qs = qs.filter(seniority=f["level"])
    if f["within"]:
        qs = qs.filter(first_seen_at__gte=timezone.now() - timedelta(days=int(f["within"])))
    qs = qs.order_by("-first_seen_at", "-pk")
    page = Paginator(qs, settings.STILLOPEN_PUBLIC_PAGE_SIZE).get_page(request.GET.get("page"))
    counts = {row["country"]: row["n"] for row in base.exclude(country="").values("country").annotate(n=Count("id"))}
    with_jobs = sorted(({"code": c, "name": countries_all.name(c), "n": n} for c, n in counts.items() if c in countries_all.ALL), key=lambda r: r["name"])
    without = [{"code": c, "name": n} for c, n in countries_all.sorted_items() if c not in counts]
    rows = [{"p": p, "credit": public.credit_for(p), "slug": public.slug_for(p), "where": public.location_label(p)} for p in page]
    keep = request.GET.copy()
    keep.pop("page", None)
    filtered = any(f.values())
    stats = public.stats()
    return render(request, "tracker/openings.html", {
        "config": config, "page": page, "rows": rows, "q": q, "country": country, "remote": remote, "f": f,
        "countries_with_jobs": with_jobs, "countries_without": without, "types": TYPES, "levels": LEVELS, "within_options": WITHIN,
        "country_name": geo.country_name(country) if country else "", "total": paginator_total(page), "filtered": filtered,
        "country_empty": bool(country) and not counts.get(country),
        "qs": keep.urlencode(), "credits": stats["credits"], "stats": stats,
        # filtered and deep pages are for people, not search results
        "noindex": filtered or page.number > 1,
    })


FEED_LIMIT = 100


@require_GET
@public_cache
def openings_feed(request):
    """An RSS feed of the public job board, for anyone who would rather subscribe than visit. Same filters as
    the board itself (q, country, remote, visa, relocation, type, level, within), same rule as everywhere else
    on the public side: each item is a short excerpt plus a credit link to the opening's own page, never the
    full posting text."""
    config = SiteConfig.load()
    if _board_off(config):
        raise Http404("The public job board is switched off.")
    f = _filters(request)
    qs = public.public_postings()
    for word in f["q"].split():
        qs = qs.filter(Q(title__icontains=word) | Q(company__icontains=word) | Q(location__icontains=word))
    if f["country"]:
        qs = qs.filter(country=f["country"])
    if f["remote"]:
        qs = qs.filter(remote=True)
    if f["visa"]:
        qs = qs.filter(sponsorship="yes")
    if f["relocation"]:
        qs = qs.filter(relocation="yes")
    if f["type"]:
        qs = qs.filter(employment_type=f["type"])
    if f["level"]:
        qs = qs.filter(seniority=f["level"])
    if f["within"]:
        qs = qs.filter(first_seen_at__gte=timezone.now() - timedelta(days=int(f["within"])))
    qs = qs.order_by("-first_seen_at", "-pk")[:FEED_LIMIT]

    feed = Rss201rev2Feed(
        title=f"{config.site_title} — job openings",
        link=request.build_absolute_uri(reverse("openings")),
        description="New job openings from public job boards and employer career pages, read by StillOpen.",
        language="en",
    )
    for p in qs:
        credit = public.credit_for(p)
        where = public.location_label(p)
        description = p.excerpt.strip() or "No description read from this posting."
        description += f"\n\nWhere: {where}. Source: {credit['label']}."
        feed.add_item(
            title=f"{p.title} at {p.company}" if p.company else p.title,
            link=request.build_absolute_uri(reverse("opening_detail", args=[p.pk, public.slug_for(p)])),
            description=description,
            pubdate=p.first_seen_at,
            unique_id=request.build_absolute_uri(reverse("opening_detail_bare", args=[p.pk])),
        )
    return HttpResponse(feed.writeString("utf-8"), content_type="application/rss+xml; charset=utf-8")


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
        "Disallow: /app/", "Disallow: /dashboard/", "Disallow: /accounts/", "Disallow: /admin/", "Disallow: /api/", "Disallow: /profile/", "Disallow: /jobs/",
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
    urls = [(request.build_absolute_uri(reverse(name)), None) for name in ("landing", "privacy", "terms", "tools_index", "tool_job_fit", "tool_liveness", "tool_offer_compare")]
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
