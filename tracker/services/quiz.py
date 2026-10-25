"""Daily practice for a prep plan: today's questions, scoring, the streak, and which topics need another look.

Plain rules, no AI. Everything is worked out from the answers the person has given (`PrepAnswer`), so there is one source of truth and
nothing to get out of step. Design: docs/design/prep-plans.md, section 7.
"""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Max
from django.utils import timezone

from tracker.models import PrepAnswer, PrepChallenge, PrepChallengeItem, PrepPlan, PrepQuestion, PrepTopic
from tracker.services import tz

WEAK_WINDOW_DAYS = 30        # two different questions on a topic missed within this many days: the topic needs another look
RECOVER_DAYS = 3             # ...and it clears after correct answers on this many separate days
RECOVER_QUESTIONS = 2        # ...across at least this many different questions, all after the latest miss
RECENT_CORRECT_DAYS = 7      # a question answered right this recently is not asked again unless nothing else is left


class QuizError(Exception):
    """Shown to the person, so it says what to do."""


def _answers(plan: PrepPlan) -> list:
    return list(PrepAnswer.objects.filter(question__plan=plan).select_related("question").order_by("answered_at", "id"))


def weak_topics(plan: PrepPlan, today=None, answers=None) -> list:
    """Topics with a pattern of misses that has not been recovered from yet."""
    today = today or tz.today_for(plan.owner_id)
    answers = _answers(plan) if answers is None else answers
    by_topic = {}
    for answer in answers:
        by_topic.setdefault(answer.question.topic_id, []).append(answer)
    weak = []
    for topic in plan.topics.all():
        given = by_topic.get(topic.pk, [])
        misses = [a for a in given if not a.correct]
        recent = [a for a in misses if (today - a.answered_on).days <= WEAK_WINDOW_DAYS]
        if len({a.question_id for a in recent}) < 2:
            continue
        last_miss = misses[-1]
        after = [a for a in given if a.correct and (a.answered_at, a.id) > (last_miss.answered_at, last_miss.id)]
        if len({a.answered_on for a in after}) >= RECOVER_DAYS and len({a.question_id for a in after}) >= RECOVER_QUESTIONS:
            continue
        weak.append(topic)
    return weak


def streak(plan: PrepPlan, today=None) -> int:
    """Consecutive days with a finished practice. Still counts today's streak as alive until the day ends."""
    today = today or tz.today_for(plan.owner_id)
    days = set(plan.challenges.filter(completed_at__isnull=False).values_list("day", flat=True))
    day = today if today in days else today - timedelta(days=1)
    count = 0
    while day in days:
        count += 1
        day -= timedelta(days=1)
    return count


def _eligible(plan: PrepPlan) -> list:
    """Questions from the current week and earlier weeks (the current week is the first one with a lesson still to do)."""
    from tracker.models import PrepLesson

    questions = list(plan.questions.filter(removed=False).select_related("lesson__week", "topic").order_by("lesson__week__order", "lesson__order", "id"))
    first_undone = PrepLesson.objects.filter(week__plan=plan, done_at__isnull=True).order_by("week__order").values_list("week__order", flat=True).first()
    if first_undone is None:
        return questions
    return [q for q in questions if q.lesson is None or q.lesson.week.order <= first_undone] or questions


def build_challenge(plan: PrepPlan, count: int, today=None) -> PrepChallenge:
    """Today's practice for this plan: made once per day, then the same however often it is opened."""
    today = today or tz.today_for(plan.owner_id)
    existing = plan.challenges.filter(day=today).first()
    if existing:
        return existing
    count = max(1, min(10, count))
    answers = _answers(plan)
    history = {}
    for answer in answers:
        history.setdefault(answer.question_id, []).append(answer)
    weak_ids = {t.pk for t in weak_topics(plan, today, answers)}

    def last(q):
        given = history.get(q.pk)
        return given[-1] if given else None

    def rank(q):
        """Never seen, then last time wrong, then right but a while ago, then right recently. Oldest first inside each."""
        latest = last(q)
        if latest is None:
            return (0, 0)
        age = latest.answered_on.toordinal()
        if not latest.correct:
            return (1, age)
        return (3 if (today - latest.answered_on).days <= RECENT_CORRECT_DAYS else 2, age)

    pool = _eligible(plan)
    if not pool:
        raise QuizError("This plan has no questions to practise.")
    ordered = sorted(pool, key=lambda q: (rank(q), pool.index(q)))
    chosen, review_ids = [], set()
    review = [q for q in ordered if q.topic_id in weak_ids and rank(q)[0] != 3]
    if review:
        chosen.append(review[0])
        review_ids.add(review[0].pk)
    for q in ordered:
        if len(chosen) >= count:
            break
        if q not in chosen:
            chosen.append(q)
    number = (plan.challenges.aggregate(m=Max("number"))["m"] or 0) + 1
    try:
        with transaction.atomic():
            challenge = PrepChallenge.objects.create(plan=plan, number=number, day=today)
            for position, q in enumerate(chosen, start=1):
                PrepChallengeItem.objects.create(challenge=challenge, question=q, position=position, is_review=q.pk in review_ids)
    except IntegrityError:  # two tabs opened it at the same moment
        return plan.challenges.get(day=today)
    return challenge


def submit(challenge: PrepChallenge, choices: dict, today=None) -> dict:
    """Score the answers {question id: [chosen indexes]} for every unanswered question. All or nothing: a missing answer saves none."""
    today = today or tz.today_for(challenge.plan.owner_id)
    items = list(challenge.items.select_related("question"))
    done = set(challenge.answers.values_list("question_id", flat=True))
    todo = [item for item in items if item.question_id not in done]
    if not todo:
        raise QuizError("You have already answered today's questions.")
    prepared = []
    for item in todo:
        q = item.question
        picked = sorted({i for i in choices.get(q.pk, []) if isinstance(i, int) and 0 <= i < len(q.choices)})
        if not picked:
            raise QuizError("Answer every question before you send them.")
        if q.kind == "single" and len(picked) != 1:
            raise QuizError("Pick just one answer for the questions that ask for one.")
        prepared.append((item, picked, picked == sorted(q.correct)))
    with transaction.atomic():
        for item, picked, correct in prepared:
            PrepAnswer.objects.create(owner=challenge.plan.owner, question=item.question, challenge=challenge, chosen=picked, correct=correct,
                                      answered_on=today, mode="review" if item.is_review else "daily")
        challenge.completed_at = timezone.now()
        challenge.save(update_fields=["completed_at"])
    right = sum(1 for _, _, correct in prepared if correct)
    return {"right": right, "total": len(prepared)}


def results(challenge: PrepChallenge) -> list:
    """The finished practice question by question, for the page that explains each answer."""
    answers = {a.question_id: a for a in challenge.answers.all()}
    out = []
    for item in challenge.items.select_related("question__topic"):
        answer = answers.get(item.question_id)
        out.append({"question": item.question, "chosen": answer.chosen if answer else [], "correct": answer.correct if answer else None,
                    "review": item.is_review})
    return out


def due_plans(user, today=None) -> list:
    """Plans in progress that have questions and no finished practice today (what the dashboard nudges about)."""
    today = today or tz.today_for(user)
    finished_today = PrepChallenge.objects.filter(plan__owner=user, day=today, completed_at__isnull=False).values("plan_id")
    plans = PrepPlan.objects.filter(owner=user, status__in=["active", "done"]).exclude(pk__in=finished_today)
    return [p for p in plans if p.questions.filter(removed=False).exists()]
