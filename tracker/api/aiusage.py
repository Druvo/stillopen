"""The person's own AI usage this month (see services/aiusage.py): counts, tokens, cost where a price is known, failures and call time.
Never any prompt or reply text, and never anyone else's calls."""
from ninja import Router

from ..services import aiusage

router = Router()


@router.get("/ai-usage", summary="This month's AI usage for the signed-in person")
def my_usage(request):
    return aiusage.report(request.user)
