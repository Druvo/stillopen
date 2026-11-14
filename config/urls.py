from django.contrib import admin
from django.urls import include, path

from tracker import views_clerk
from tracker.api import api

admin.site.site_header = "StillOpen admin"
admin.site.site_title = "StillOpen admin"
admin.site.index_title = "Configuration and data"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/login/", views_clerk.login_page, name="account_login"),
    path("accounts/signup/", views_clerk.signup_page, name="account_signup"),
    path("accounts/logout/", views_clerk.logout_view, name="account_logout"),
    path("auth/clerk/session/", views_clerk.clerk_session, name="clerk_session"),
    path("accounts/", include("allauth.urls")),
    path("api/v1/", api.urls),
    path("", include("tracker.urls")),
]
