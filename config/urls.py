from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "Job search admin"
admin.site.site_title = "Job search admin"
admin.site.index_title = "Configuration and data"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("tracker.urls")),
]
