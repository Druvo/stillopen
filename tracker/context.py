from .models import SiteConfig


def site_config(request):
    config = SiteConfig.load()
    return {"site_config": config, "google_login_on": config.google_login_enabled}
