from django.urls import path

from . import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("api/application/<int:pk>/status/", views.set_status, name="set_status"),
    path("api/application/<int:pk>/evaluate/", views.evaluate, name="evaluate"),
    path("api/liveness/start/", views.liveness_start, name="liveness_start"),
    path("api/liveness/status/", views.liveness_status, name="liveness_status"),
    path("api/import/", views.import_tracker, name="import_tracker"),
    path("api/document/<int:pk>/paperless/", views.push_to_paperless, name="push_to_paperless"),
    path("document/<int:pk>/", views.document_file, name="document_file"),
]
