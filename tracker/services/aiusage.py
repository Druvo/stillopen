"""The person's own AI usage for the current month, from the AIUsageEvent log (owner-only).

Counts, tokens, a cost per model where the model has a known price (never a guess for one that does not: the cost stays blank and
the call is counted as "not priced"), a breakdown by purpose, failures and call time where it was recorded. Nothing from a prompt or a
reply is stored in the log, so none of it can appear here."""
from collections import defaultdict
from decimal import Decimal

from ..models import AIUsageEvent
from . import tz

RECENT = 25

PURPOSE_LABELS = {
    "evaluate": "Fit check", "tailor": "Tailored CV or cover letter", "prep": "Prep plan", "interview_prep": "Interview questions",
    "answer_feedback": "Answer feedback", "app_answer": "Application answer", "summarise": "Posting summary",
    "suggest_roles": "Role suggestions", "message_draft": "Message draft", "parse_posting": "Posting reader",
    "counter_note": "Counter-offer note", "referral_draft": "Referral message", "cv_improve": "CV improvement",
    "refine": "Ask for changes", "reply": "Reply draft",
}


def purpose_label(key: str) -> str:
    return PURPOSE_LABELS.get(key) or key.replace("_", " ").capitalize()


def percentile(values: list[int], p: float) -> int | None:
    """Nearest-rank percentile of a list; None for an empty list."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, -(-int(p * len(ordered) * 100) // 100))  # ceil(p * n) without float noise
    return ordered[min(rank, len(ordered)) - 1]


def _cost(value) -> float | None:
    return float(value) if value is not None else None


def report(user, limit: int = RECENT) -> dict:
    now = tz.now_for(user)
    month = AIUsageEvent.objects.filter(owner=user, created_at__year=now.year, created_at__month=now.month)
    rows = list(month.order_by("-created_at", "-pk").values("id", "created_at", "purpose", "provider", "model", "input_tokens", "output_tokens", "cost_usd", "cost_is_estimate", "duration_ms", "ok"))

    latest = list(AIUsageEvent.objects.filter(owner=user).order_by("-created_at", "-pk").values("id", "created_at", "purpose", "provider", "model", "input_tokens", "output_tokens", "cost_usd", "duration_ms", "ok")[:limit])
    ok_rows = [r for r in rows if r["ok"]]
    by_model: dict[tuple[str, str], dict] = {}
    by_purpose: dict[str, dict] = defaultdict(lambda: {"calls": 0, "failed": 0, "input_tokens": 0, "output_tokens": 0})
    for r in rows:
        p = by_purpose[r["purpose"]]
        p["calls"] += 1
        if not r["ok"]:
            p["failed"] += 1
            continue
        p["input_tokens"] += r["input_tokens"] or 0
        p["output_tokens"] += r["output_tokens"] or 0
        key = (r["provider"], r["model"])
        m = by_model.setdefault(key, {"provider": r["provider"], "model": r["model"], "currency": "USD", "calls": 0, "input_tokens": 0, "output_tokens": 0, "cost": Decimal(0), "priced": 0, "unpriced": 0, "estimated": False})
        m["calls"] += 1
        m["input_tokens"] += r["input_tokens"] or 0
        m["output_tokens"] += r["output_tokens"] or 0
        if r["cost_usd"] is not None:
            m["cost"] += r["cost_usd"]
            m["priced"] += 1
            m["estimated"] = m["estimated"] or r["cost_is_estimate"]
        else:
            m["unpriced"] += 1  # tokens may be known, but there is no price to multiply them by: never guessed

    models = [
        {
            "provider": m["provider"], "model": m["model"], "currency": m["currency"], "calls": m["calls"],
            "input_tokens": m["input_tokens"], "output_tokens": m["output_tokens"],
            "cost": float(m["cost"]) if m["priced"] else None, "unpriced_calls": m["unpriced"], "estimated": m["estimated"],
        }
        for m in sorted(by_model.values(), key=lambda m: -m["calls"])
    ]
    totals_by_currency = defaultdict(lambda: Decimal(0))
    for m in by_model.values():
        if m["priced"]:
            totals_by_currency[m["currency"]] += m["cost"]
    durations = [r["duration_ms"] for r in ok_rows if r["duration_ms"] is not None]
    return {
        "month": f"{now:%Y-%m}",
        "calls": len(rows),
        "failed": len(rows) - len(ok_rows),
        "input_tokens": sum(r["input_tokens"] or 0 for r in ok_rows),
        "output_tokens": sum(r["output_tokens"] or 0 for r in ok_rows),
        "costs": [{"currency": c, "amount": float(v)} for c, v in totals_by_currency.items()],
        "any_estimated": any(m["estimated"] for m in by_model.values()),
        "unpriced_calls": sum(m["unpriced"] for m in by_model.values()),
        "latency": {"samples": len(durations), "p50_ms": percentile(durations, 0.5), "p95_ms": percentile(durations, 0.95)},
        "models": models,
        "purposes": [
            {"purpose": k, "label": purpose_label(k), **v}
            for k, v in sorted(by_purpose.items(), key=lambda kv: -kv[1]["calls"])
        ],
        "recent": [
            {
                "id": r["id"], "at": r["created_at"].isoformat(), "purpose": purpose_label(r["purpose"]), "provider": r["provider"], "model": r["model"],
                "input_tokens": r["input_tokens"], "output_tokens": r["output_tokens"], "cost": _cost(r["cost_usd"]), "currency": "USD",
                "duration_ms": r["duration_ms"], "ok": r["ok"],
            }
            for r in latest
        ],
    }
