"""The whole account as one JSON file (the "Export my data" button), and the shape `dataimport` reads back.

Secrets (API keys, tokens), file paths and other people's data are never in it. `FORMAT` and `VERSION` let the importer refuse a file that
is not one of ours."""
from django.utils import timezone

from tracker.models import Application, KnowledgeSource, PrepAnswer, UserProfile

FORMAT = "stillopen-export"
VERSION = 1


def build(user) -> dict:
    profile = UserProfile.for_user(user)
    data = {
        "format": FORMAT, "format_version": VERSION,
        "exported_at": timezone.now().isoformat(),
        "account": {"username": user.get_username(), "email": user.email},
        "profile": {
            "target_roles": profile.target_roles, "employment_types": profile.employment_types,
            "seniority_levels": profile.seniority_levels, "industries": profile.industries, "languages": profile.languages,
            "notice_period": profile.notice_period, "salary_floor": profile.salary_floor,
            "search_areas": [a.describe() for a in user.search_areas.all()],
            "deal_breakers": profile.deal_breakers, "about": profile.about, "cv": profile.profile_cv,
            "home_country": profile.home_country, "timezone": profile.timezone,
        },
        "knowledge": [
            {"title": s.title, "kind": s.kind, "enabled": s.enabled, "text": s.text}
            for s in KnowledgeSource.objects.filter(owner=user).exclude(key__in=["profile-cv", "careerops:cv.md"])
        ],
        "prep_plans": [
            {"title": p.title, "summary": p.summary, "status": p.status, "weeks": p.weeks_count, "hours_per_week": p.hours_per_week,
             "for_job": f"{p.application.company} - {p.application.role}" if p.application else None, "gaps": p.gap_skills,
             "lessons": [{"week": w.order, "title": le.title, "gap": le.gap, "sources": le.sources, "done": bool(le.done_at)}
                         for w in p.weeks.all() for le in w.lessons.all()],
             "tasks": [{"week": w.order, "kind": m.kind, "text": m.text, "done": bool(m.done_at)} for w in p.weeks.all() for m in w.milestones.all()],
             "topics": [t.title for t in p.topics.all()],
             "practice_days": [{"number": c.number, "day": c.day.isoformat(), "finished": bool(c.completed_at)} for c in p.challenges.all()],
             "questions": [{"prompt": q.prompt, "choices": q.choices, "correct": q.correct, "explanation": q.explanation, "sources": q.sources}
                           for q in p.questions.filter(removed=False)],
             "answers": [{"question": a.question.prompt, "chosen": a.chosen, "correct": a.correct, "day": a.answered_on.isoformat(), "mode": a.mode}
                         for a in PrepAnswer.objects.filter(owner=user, question__plan=p).select_related("question")]}
            for p in user.prep_plans.select_related("application").prefetch_related("weeks__lessons")
        ],
        "cv_versions": [
            {"label": v.label, "kind": v.kind, "source": v.source, "created": v.created_at.isoformat(),
             "for_job": f"{v.application.company} - {v.application.role}" if v.application else None, "content": v.content}
            for v in user.cv_versions.select_related("application")
        ],
        "interviews": [
            {"for_job": f"{i.application.company} - {i.application.role}", "when": i.scheduled_at.isoformat(), "kind": i.kind,
             "where": i.where, "notes": i.notes, "outcome": i.outcome}
            for i in user.interviews.select_related("application")
        ],
        "contacts": [
            {"name": c.name, "company": c.company, "title": c.title, "email": c.email, "link": c.link, "notes": c.notes,
             "last_contacted": c.last_contacted.isoformat() if c.last_contacted else None,
             "referrals": [{"for_job": f"{r.application.company} - {r.application.role}", "status": r.status, "note": r.note} for r in c.referrals.all()]}
            for c in user.contacts.prefetch_related("referrals__application")
        ],
        "offers": [
            {"for_job": f"{o.application.company} - {o.application.role}", "status": o.status, "currency": o.currency,
             "base": str(o.base), "period": o.period, "bonus": str(o.bonus), "equity": str(o.equity),
             "other_benefits": str(o.other_benefits), "signing": str(o.signing),
             "deadline": o.deadline.isoformat() if o.deadline else None, "notes": o.notes}
            for o in user.offers.select_related("application")
        ],
        "interview_prep": [
            {"for_job": f"{ip.application.company} - {ip.application.role}", "created": ip.created_at.isoformat(), "content": ip.content}
            for ip in user.interview_preps.select_related("application")
        ],
        "question_bank": [
            {"question": q.question, "answer": q.answer, "tags": q.tags} for q in user.bank_questions.all()
        ],
        "company_notes": [
            {"company": n.name, "notes": n.notes, "website": n.website, "careers": n.careers, "linkedin": n.linkedin, "watched": n.watched}
            for n in user.company_notes.all()
        ],
        "own_job_sources": [
            {"name": s.name, "connector": s.connector, "board_token": s.board_token, "enabled": s.enabled}
            for s in user.job_sources.all()
        ],
        "cover_letters": [
            {"for_job": f"{l.application.company} - {l.application.role}", "source": l.source,
             "created": l.created_at.isoformat(), "content": l.content}
            for l in user.cover_letters.select_related("application")
        ],
        "applications": [
            {
                "company": a.company, "role": a.role, "url": a.url, "status": a.status.name,
                "score": a.score, "verdict": a.decision, "summary": a.summary, "notes": a.notes,
                "applied_channel": a.applied_channel, "applied_note": a.applied_note, "applied_cv_label": a.applied_cv.label if a.applied_cv else None,
                "follow_up_date": a.follow_up_date.isoformat() if a.follow_up_date else None, "description_at_apply": a.jd_at_apply,
                "location": a.location_text, "country": a.country, "arrangement": a.arrangement,
                "sponsorship": a.sponsorship, "relocation": a.relocation, "employment_type": a.employment_type, "seniority": a.seniority,
                "found": a.found_date.isoformat(), "applied": a.applied_date.isoformat() if a.applied_date else None,
                "deadline": a.deadline.isoformat() if a.deadline else None, "description": a.description,
                "strengths": [i.text for i in a.insights.all() if i.kind == "strength"],
                "gaps": [i.text for i in a.insights.all() if i.kind == "gap"],
                "timeline": [f"{e.happened_at:%Y-%m-%d} {e.get_kind_display()}: {e.text}" for e in a.events.all()],
            }
            for a in Application.objects.filter(owner=user).select_related("status").prefetch_related("insights", "events")
        ],
    }
    return data
