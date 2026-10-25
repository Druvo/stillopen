from django.contrib import admin
from django.urls import include, path

from tracker.api import api

admin.site.site_header = "StillOpen admin"
admin.site.site_title = "StillOpen admin"
admin.site.index_title = "Configuration and data"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("api/v1/", api.urls),
    path("", include("tracker.urls")),
]
