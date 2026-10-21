from django.urls import path

from . import views

urlpatterns = [
    path("", views.landing, name="landing"),
    path("privacy/", views.privacy, name="privacy"),
    path("terms/", views.terms, name="terms"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("jobs/add/", views.add_job, name="add_job"),
    path("profile/", views.profile, name="profile"),
    path("profile/ai/", views.profile_ai, name="profile_ai"),
    path("profile/export/", views.export_data, name="export_data"),
    path("profile/delete/", views.delete_account, name="delete_account"),
    path("knowledge/", views.knowledge_list, name="knowledge"),
    path("knowledge/<int:pk>/<str:action>/", views.knowledge_action, name="knowledge_action"),
    path("api/application/<int:pk>/status/", views.set_status, name="set_status"),
    path("api/application/<int:pk>/evaluate/", views.evaluate, name="evaluate"),
    path("api/liveness/start/", views.liveness_start, name="liveness_start"),
    path("api/liveness/status/", views.liveness_status, name="liveness_status"),
    path("api/import/", views.import_tracker, name="import_tracker"),
    path("api/document/<int:pk>/paperless/", views.push_to_paperless, name="push_to_paperless"),
    path("document/<int:pk>/", views.document_file, name="document_file"),
]
