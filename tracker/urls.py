from django.urls import include, path, re_path

from . import views_export
from . import views, views_app, views_calendar, views_cover, views_cv, views_google, views_mcp, views_public, views_tools

urlpatterns = [
    path("", views_public.landing, name="landing"),
    path("openings/", views_public.openings, name="openings"),
    path("openings/feed.rss", views_public.openings_feed, name="openings_feed"),
    path("openings/<int:pk>/", views_public.opening_detail, name="opening_detail_bare"),
    path("openings/<int:pk>/<slug:slug>/", views_public.opening_detail, name="opening_detail"),
    path("robots.txt", views_public.robots_txt, name="robots"),
    path("sitemap.xml", views_public.sitemap, name="sitemap"),
    path("privacy/", views.privacy, name="privacy"),
    path("terms/", views.terms, name="terms"),
    path("app/", views_app.app_shell, name="app_shell"),
    re_path(r"^app/(?P<path>_next/.+)$", views_app.app_asset, name="app_asset_next"),
    path("app/<path:path>", views_app.app_shell, name="app_shell_deep"),
    path("tools/email-test/", views.email_test, name="email_test"),
    path("tools/", views_tools.tools_index, name="tools_index"),
    path("tools/job-fit/", views_tools.job_fit, name="tool_job_fit"),
    path("tools/is-it-still-open/", views_tools.liveness_check, name="tool_liveness"),
    path("tools/compare-offers/", views_tools.offer_compare, name="tool_offer_compare"),
    re_path(r"^calendar/(?P<token>[A-Za-z0-9_-]{8,100})\.ics$", views_calendar.calendar_feed, name="calendar_feed"),
    path("google/callback/", views_google.google_callback, name="google_callback"),
    path("developers/", views_tools.api_reference, name="api_reference"),
    path("tools/sample-interview-questions/", views_tools.sample_questions, name="tool_sample_questions"),
    path("mcp/", views_mcp.mcp_endpoint, name="mcp_endpoint"),
    # files the app links to by these addresses (not JSON, so they are not in /api/v1/)
    path("profile/export/", views.export_data, name="export_data"),
    path("jobs/export.csv", views_export.jobs_csv, name="jobs_export_csv"),
    path("document/<int:pk>/", views.document_file, name="document_file"),
    path("interviews/calendar.ics", views_calendar.interviews_calendar, name="interviews_calendar"),
    path("interviews/<int:pk>/calendar.ics", views_calendar.interview_calendar, name="interview_calendar"),
    path("cv/<int:pk>/print/", views_cv.cv_print, name="cv_print"),
    path("cv/<int:pk>/preview/", views_cv.cv_preview, name="cv_preview"),
    path("cv/builder/preview/", views_cv.builder_preview, name="cv_builder_preview"),
    path("jobs/<int:pk>/documents.zip", views_cv.job_documents_zip, name="job_documents_zip"),
    path("cv/<int:pk>/download/<str:fmt>/", views_cv.cv_download, name="cv_download"),
    path("cover/<int:pk>/download/<str:fmt>/", views_cover.cover_download, name="cover_download"),
    # the old classic-page addresses, redirected into the app
    path("", include("tracker.legacy")),
]
