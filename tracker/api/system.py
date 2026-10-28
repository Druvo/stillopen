"""Which version is running, and the optional "newer release" notice for site admins (see services/updatecheck.py)."""
from ninja import Router
from ninja.errors import HttpError

from ..models import SiteConfig
from ..services import updatecheck

router = Router()


@router.get("/version", summary="The running version")
def version(request):
    return {"version": updatecheck.running_version()}


@router.get("/update-check", summary="Is a newer release out? (site admins only; asks GitHub only when the admin switched that on)")
def update_check(request):
    if not request.user.is_staff:
        raise HttpError(403, "Only site admins can do that.")
    return updatecheck.status(SiteConfig.load())
