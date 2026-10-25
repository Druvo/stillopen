"""Prep plans, phase 2: daily practice, scoring, the streak, and topics that need another look."""
from datetime import date, timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from tracker.models import (Application, PrepAnswer, PrepChallenge, PrepLesson, PrepPlan, PrepQuestion, PrepTopic, PrepWeek, SiteConfig, UserProfile)
from tracker.services import guide, quiz
from tracker.tests_prep import GOOD_SOURCE, PrepBase

User = get_user_model()
TODAY = date(2026, 10, 25)


def day(n):
    """n days before TODAY."""
    return TODAY - timedelta(days=n)


class QuizBase(PrepBase):
    def plan_with_questions(self, owner=None, status="active", topics=2, per_topic=3, weeks=2):
        """A plan with `weeks` weeks of one lesson each; every topic has `per_topic` questions spread over those lessons."""
        owner = owner or self.user
        app = self.app if owner == self.user else Application.objects.create(owner=owner, company="O", role="R", status=self.status, description="x")
        plan = PrepPlan.objects.create(owner=owner, application=app, title="Plan", status=status)
        lessons = []
        for w in range(1, weeks + 1):
            week = PrepWeek.objects.create(plan=plan, order=w, title=f"W{w}", hours=6)
            lessons.append(PrepLesson.objects.create(week=week, order=1, title=f"L{w}", gap="Kubernetes", sources=[GOOD_SOURCE]))
        self.topics, self.qs = [], []
        for t in range(topics):
            topic = PrepTopic.objects.create(plan=plan, slug=f"t{t}", title=f"Topic {t}")
            self.topics.append(topic)
            for n in range(per_topic):
                lesson = lessons[n % weeks]
                self.qs.append(PrepQuestion.objects.create(
                    plan=plan, topic=topic, lesson=lesson, prompt=f"T{t}Q{n}", choices=["a", "b", "c", "d"], correct=[0] if n % 3 else [0, 2],
                    kind="single" if n % 3 else "multi", explanation="because", sources=[GOOD_SOURCE]))
        return plan

    def answer(self, question, correct, when, owner=None):
        return PrepAnswer.objects.create(owner=owner or self.user, question=question, challenge=None, chosen=list(question.correct) if correct else [3],
                                         correct=correct, answered_on=when)


class Selection(QuizBase):
    def test_a_day_has_one_practice_however_often_it_is_opened_and_numbers_count_up(self):
        plan = self.plan_with_questions()
        first = quiz.build_challenge(plan, 3, TODAY)
        self.assertEqual(quiz.build_challenge(plan, 3, TODAY).pk, first.pk)
        self.assertEqual(first.items.count(), 3)
        second = quiz.build_challenge(plan, 3, day(-1))
        self.assertEqual((first.number, second.number), (1, 2))
        self.assertEqual(list(first.items.values_list("position", flat=True)), [1, 2, 3])

    def test_the_count_comes_from_the_setting_and_is_bounded(self):
        plan = self.plan_with_questions(per_topic=6, weeks=1)
        self.assertEqual(quiz.build_challenge(plan, 99, TODAY).items.count(), 10)
        self.assertEqual(quiz.build_challenge(plan, 0, day(-1)).items.count(), 1)

    def test_removed_questions_never_appear_and_an_empty_plan_says_so(self):
        plan = self.plan_with_questions(topics=1, per_topic=2, weeks=1)
        PrepQuestion.objects.filter(plan=plan).update(removed=True)
        with self.assertRaises(quiz.QuizError):
            quiz.build_challenge(plan, 3, TODAY)
        PrepQuestion.objects.filter(pk=self.qs[0].pk).update(removed=False)
        self.assertEqual(list(quiz.build_challenge(plan, 3, TODAY).items.values_list("question_id", flat=True)), [self.qs[0].pk])

    def test_new_questions_come_first_then_the_missed_then_the_long_ago_then_recent_right_answers(self):
        plan = self.plan_with_questions(topics=1, per_topic=4, weeks=1)
        q_new, q_missed, q_old, q_recent = self.qs
        self.answer(q_missed, False, day(2))
        self.answer(q_old, True, day(20))
        self.answer(q_recent, True, day(1))
        ids = list(quiz.build_challenge(plan, 4, TODAY).items.values_list("question_id", flat=True))
        self.assertEqual(ids, [q_new.pk, q_missed.pk, q_old.pk, q_recent.pk])

    def test_only_this_weeks_and_earlier_weeks_questions_are_asked_until_lessons_are_done(self):
        plan = self.plan_with_questions(topics=1, per_topic=4, weeks=2)  # questions alternate week 1, 2, 1, 2
        week_of = {q.pk: q.lesson.week.order for q in self.qs}
        first = quiz.build_challenge(plan, 10, TODAY)
        self.assertEqual({week_of[i] for i in first.items.values_list("question_id", flat=True)}, {1})
        PrepLesson.objects.filter(week__plan=plan, week__order=1).update(done_at=timezone.now())
        later = quiz.build_challenge(plan, 10, day(-1))
        self.assertEqual({week_of[i] for i in later.items.values_list("question_id", flat=True)}, {1, 2})

    def test_a_topic_that_needs_another_look_gets_one_review_question_first(self):
        plan = self.plan_with_questions(topics=2, per_topic=3, weeks=1)
        weak_topic = self.topics[0]
        for q in self.qs[:2]:
            self.answer(q, False, day(3))
        first_item = quiz.build_challenge(plan, 3, TODAY).items.first()
        self.assertTrue(first_item.is_review)
        self.assertEqual(first_item.question.topic, weak_topic)
        self.assertEqual(list(quiz.build_challenge(plan, 3, TODAY).items.filter(is_review=True).values_list("pk", flat=True)), [first_item.pk])


class Scoring(QuizBase):
    def setUp(self):
        super().setUp()
        self.plan = self.plan_with_questions(topics=1, per_topic=3, weeks=1)  # Q0 multi [0, 2]; Q1, Q2 single [0]
        self.challenge = quiz.build_challenge(self.plan, 3, TODAY)

    def choices(self, **by_index):
        return {self.qs[int(k[1:])].pk: v for k, v in by_index.items()}

    def test_multi_answer_questions_need_the_exact_set(self):
        result = quiz.submit(self.challenge, self.choices(q0=[0, 2], q1=[0], q2=[1]), TODAY)
        self.assertEqual((result["right"], result["total"]), (2, 3))
        right = {a.question_id: a.correct for a in self.challenge.answers.all()}
        self.assertEqual(right, {self.qs[0].pk: True, self.qs[1].pk: True, self.qs[2].pk: False})
        self.assertIsNotNone(PrepChallenge.objects.get(pk=self.challenge.pk).completed_at)

    def test_part_of_a_multi_answer_is_wrong_and_extra_is_wrong(self):
        quiz.submit(self.challenge, self.choices(q0=[0], q1=[0], q2=[0]), TODAY)
        self.assertFalse(PrepAnswer.objects.get(question=self.qs[0]).correct)
        challenge2 = quiz.build_challenge(self.plan, 3, day(-1))
        quiz.submit(challenge2, self.choices(q0=[0, 1, 2], q1=[0], q2=[0]), day(-1))
        self.assertFalse(PrepAnswer.objects.get(question=self.qs[0], challenge=challenge2).correct)

    def test_a_missing_answer_saves_nothing(self):
        with self.assertRaises(quiz.QuizError):
            quiz.submit(self.challenge, self.choices(q0=[0, 2], q1=[0]), TODAY)
        self.assertEqual(PrepAnswer.objects.count(), 0)
        self.assertIsNone(PrepChallenge.objects.get(pk=self.challenge.pk).completed_at)

    def test_one_answer_questions_need_exactly_one_pick_and_bad_indexes_do_not_count(self):
        with self.assertRaises(quiz.QuizError):
            quiz.submit(self.challenge, self.choices(q0=[0, 2], q1=[0, 1], q2=[0]), TODAY)
        with self.assertRaises(quiz.QuizError):
            quiz.submit(self.challenge, self.choices(q0=[0, 2], q1=[9], q2=[-1]), TODAY)
        self.assertEqual(PrepAnswer.objects.count(), 0)

    def test_it_cannot_be_answered_twice(self):
        quiz.submit(self.challenge, self.choices(q0=[0, 2], q1=[0], q2=[0]), TODAY)
        with self.assertRaisesMessage(quiz.QuizError, "already answered"):
            quiz.submit(self.challenge, self.choices(q0=[1], q1=[1], q2=[1]), TODAY)
        self.assertEqual(PrepAnswer.objects.count(), 3)

    def test_answers_belong_to_the_plan_owner_and_review_answers_are_marked(self):
        quiz.submit(self.challenge, self.choices(q0=[0, 2], q1=[0], q2=[0]), TODAY)
        self.assertTrue(all(a.owner == self.user for a in PrepAnswer.objects.all()))
        self.assertEqual({a.mode for a in PrepAnswer.objects.all()}, {"daily"})
        PrepAnswer.objects.all().delete()
        PrepChallenge.objects.all().delete()
        for q in self.qs[:2]:
            self.answer(q, False, day(2))
        review = quiz.build_challenge(self.plan, 3, TODAY)
        quiz.submit(review, {i.question_id: [0] for i in review.items.all()} | {self.qs[0].pk: [0, 2]}, TODAY)
        self.assertIn("review", set(PrepAnswer.objects.filter(challenge=review).values_list("mode", flat=True)))

    def test_results_pair_each_question_with_what_was_chosen(self):
        quiz.submit(self.challenge, self.choices(q0=[0, 2], q1=[3], q2=[0]), TODAY)
        rows = {r["question"].pk: r for r in quiz.results(self.challenge)}
        self.assertTrue(rows[self.qs[0].pk]["correct"])
        self.assertEqual((rows[self.qs[1].pk]["correct"], rows[self.qs[1].pk]["chosen"]), (False, [3]))


class NeedsAnotherLook(QuizBase):
    def setUp(self):
        super().setUp()
        self.plan = self.plan_with_questions(topics=1, per_topic=3, weeks=1)
        self.q0, self.q1, self.q2 = self.qs

    def weak(self):
        return quiz.weak_topics(self.plan, TODAY)

    def test_two_different_questions_missed_recently_mark_the_topic(self):
        self.answer(self.q0, False, day(3))
        self.assertEqual(self.weak(), [])
        self.answer(self.q1, False, day(2))
        self.assertEqual(self.weak(), [self.topics[0]])

    def test_missing_the_same_question_twice_is_not_a_pattern(self):
        self.answer(self.q0, False, day(3))
        self.answer(self.q0, False, day(2))
        self.assertEqual(self.weak(), [])

    def test_old_misses_do_not_count(self):
        self.answer(self.q0, False, day(45))
        self.answer(self.q1, False, day(2))
        self.assertEqual(self.weak(), [])
        self.answer(self.q2, False, day(40))
        self.assertEqual(self.weak(), [])

    def test_it_clears_after_right_answers_on_three_days_across_two_questions(self):
        self.answer(self.q0, False, day(10))
        self.answer(self.q1, False, day(9))
        self.answer(self.q0, True, day(8))
        self.answer(self.q1, True, day(7))
        self.assertEqual(self.weak(), [self.topics[0]])  # two days is not enough
        self.answer(self.q0, True, day(6))
        self.assertEqual(self.weak(), [])

    def test_three_days_on_one_question_does_not_clear_it(self):
        self.answer(self.q0, False, day(10))
        self.answer(self.q1, False, day(9))
        for n in (8, 7, 6):
            self.answer(self.q0, True, day(n))
        self.assertEqual(self.weak(), [self.topics[0]])

    def test_right_answers_from_before_the_latest_miss_do_not_count(self):
        for n in (14, 13, 12):
            self.answer(self.q0, True, day(n))
            self.answer(self.q1, True, day(n))
        self.answer(self.q0, False, day(5))
        self.answer(self.q1, False, day(4))
        self.assertEqual(self.weak(), [self.topics[0]])

    def test_another_persons_answers_never_change_my_topics(self):
        theirs = self.plan_with_questions(owner=self.other)
        for q in self.qs[-3:]:
            self.answer(q, False, day(1), owner=self.other)
        self.assertEqual(quiz.weak_topics(self.plan, TODAY), [])


class Streak(QuizBase):
    def setUp(self):
        super().setUp()
        self.plan = self.plan_with_questions()

    def finish(self, *days):
        for n in days:
            PrepChallenge.objects.create(plan=self.plan, number=PrepChallenge.objects.count() + 1, day=day(n), completed_at=timezone.now())

    def test_consecutive_days_count_and_today_pending_keeps_yesterdays_run(self):
        self.assertEqual(quiz.streak(self.plan, TODAY), 0)
        self.finish(1, 2, 3)
        self.assertEqual(quiz.streak(self.plan, TODAY), 3)
        self.finish(0)
        self.assertEqual(quiz.streak(self.plan, TODAY), 4)

    def test_a_missed_day_ends_the_run_and_unfinished_practice_does_not_count(self):
        self.finish(1, 3, 4)
        self.assertEqual(quiz.streak(self.plan, TODAY), 1)
        self.finish(5)
        PrepChallenge.objects.create(plan=self.plan, number=99, day=day(2))  # opened, never finished
        self.assertEqual(quiz.streak(self.plan, TODAY), 1)
        self.assertEqual(quiz.streak(self.plan, day(-5)), 0)


class DuePlans(QuizBase):
    def test_active_plans_with_questions_and_no_finished_practice_today_are_due(self):
        plan = self.plan_with_questions()
        self.assertEqual(quiz.due_plans(self.user, TODAY), [plan])
        challenge = quiz.build_challenge(plan, 3, TODAY)
        self.assertEqual(quiz.due_plans(self.user, TODAY), [plan])  # opened but not finished
        PrepChallenge.objects.filter(pk=challenge.pk).update(completed_at=timezone.now())
        self.assertEqual(quiz.due_plans(self.user, TODAY), [])

    def test_drafts_empty_plans_and_other_peoples_plans_are_not_due(self):
        self.plan_with_questions(status="draft")
        empty = self.plan_with_questions()
        PrepQuestion.objects.filter(plan=empty).delete()
        self.plan_with_questions(owner=self.other)
        self.assertEqual(quiz.due_plans(self.user, TODAY), [])

    def test_the_dashboard_nudge_comes_after_every_other_suggestion(self):
        plan = self.plan_with_questions()
        profile = UserProfile.for_user(self.user)

        class Done:  # a profile with nothing left to ask for
            is_complete = True
            missing_fields = []

        step = guide.next_step(Done(), [{"app": self.app, "percent": None, "cv": None}], has_areas=True, prep_due=[plan])
        self.assertNotIn("practice", step["headline"].lower())  # something about the job comes first
        step = guide.next_step(Done(), [{"app": Application(status=self.status, live_state="expired"), "percent": 10, "cv": None}], has_areas=True, prep_due=[plan])
        self.assertIn("Today's practice", step["headline"])
        self.assertEqual(step["url"], f"/app/prep/{plan.pk}/today")
        self.assertIsNone(guide.next_step(Done(), [{"app": Application(status=self.status, live_state="expired"), "percent": 10, "cv": None}], has_areas=True))


class QuizViews(QuizBase):
    def setUp(self):
        super().setUp()
        self.plan = self.plan_with_questions(topics=1, per_topic=3, weeks=1)
        self.client.force_login(self.user)

    def post_all(self, **override):
        challenge = quiz.build_challenge(self.plan, 3)
        data = {f"q{i.question_id}": ["0", "2"] if i.question.kind == "multi" else ["0"] for i in challenge.items.select_related("question")}
        data.update(override)
        return self.client.post(reverse("prep_answer", args=[self.plan.pk]), data, follow=True)

    def test_the_questions_page_and_the_whole_round_trip(self):
        page = self.client.get(reverse("prep_today", args=[self.plan.pk]))
        self.assertContains(page, "Send my answers")
        self.assertContains(page, "T0Q0")
        self.assertContains(page, 'type="checkbox"')  # the multi-answer question
        self.assertContains(page, 'type="radio"')
        self.assertNotContains(page, "because")  # explanations only after answering
        done = self.post_all()
        self.assertContains(done, "3 of 3 right")
        self.assertContains(done, "because")
        self.assertContains(done, "kubernetes.io")
        self.assertContains(done, "1 day in a row")
        self.assertNotContains(done, "Send my answers")

    def test_a_wrong_answer_is_explained_and_shown(self):
        first = quiz.build_challenge(self.plan, 3).items.first().question
        done = self.post_all(**{f"q{first.pk}": ["3"]})
        self.assertContains(done, "2 of 3 right")
        self.assertContains(done, "your pick")
        self.assertContains(done, "right answer")

    def test_a_missing_answer_asks_again_and_saves_nothing(self):
        challenge = quiz.build_challenge(self.plan, 3)
        r = self.client.post(reverse("prep_answer", args=[self.plan.pk]), {f"q{challenge.items.first().question_id}": ["0"]}, follow=True)
        self.assertContains(r, "Answer every question")
        self.assertEqual(PrepAnswer.objects.count(), 0)

    def test_sending_twice_does_not_double_count(self):
        self.post_all()
        again = self.post_all()
        self.assertContains(again, "already answered")
        self.assertEqual(PrepAnswer.objects.count(), 3)

    def test_junk_in_the_form_is_ignored(self):
        challenge = quiz.build_challenge(self.plan, 3)
        r = self.client.post(reverse("prep_answer", args=[self.plan.pk]), {f"q{challenge.items.first().question_id}": ["abc", "<script>"]}, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(PrepAnswer.objects.count(), 0)

    def test_a_draft_cannot_be_practised_and_other_peoples_plans_are_not_found(self):
        draft = self.plan_with_questions(status="draft")
        theirs = self.plan_with_questions(owner=self.other)
        for plan in (draft, theirs):
            self.assertEqual(self.client.get(reverse("prep_today", args=[plan.pk])).status_code, 404)
            self.assertEqual(self.client.post(reverse("prep_answer", args=[plan.pk])).status_code, 404)
        self.assertEqual(PrepChallenge.objects.filter(plan__in=[draft, theirs]).count(), 0)

    def test_login_is_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("prep_today", args=[self.plan.pk])).status_code, 302)
        self.assertEqual(self.client.post(reverse("prep_answer", args=[self.plan.pk])).status_code, 302)

    def test_the_plan_page_shows_the_practice_button_streak_and_topics_to_revisit(self):
        page = self.client.get(reverse("prep_plan", args=[self.plan.pk]))
        self.assertContains(page, "Today&#x27;s practice" if "Today&#x27;s" in page.content.decode() else "Today's practice")
        self.post_all()
        page = self.client.get(reverse("prep_plan", args=[self.plan.pk]))
        self.assertContains(page, "See today")
        self.assertContains(page, "1 day in a row")
        for q in self.qs[:2]:
            self.answer(q, False, timezone.localdate())
        self.assertContains(self.client.get(reverse("prep_plan", args=[self.plan.pk])), "Worth another look")

    def test_the_dashboard_offers_practice_when_nothing_else_is_pending_and_the_feature_can_be_off(self):
        SiteConfig.objects.filter(pk=1).update(prep_enabled=False)
        self.assertNotContains(self.client.get(reverse("dashboard")), "Today&#x27;s practice is ready")
        self.assertEqual(self.client.get(reverse("prep_today", args=[self.plan.pk])).status_code, 404)

    def test_the_daily_count_is_an_admin_setting(self):
        SiteConfig.objects.filter(pk=1).update(prep_daily_questions=2)
        self.client.get(reverse("prep_today", args=[self.plan.pk]))
        self.assertEqual(PrepChallenge.objects.get(plan=self.plan).items.count(), 2)

    def test_answers_are_in_the_export_and_go_with_the_account(self):
        self.post_all()
        import json

        data = json.loads(self.client.get(reverse("export_data")).content)
        self.assertEqual(len(data["prep_plans"][0]["answers"]), 3)
        self.user.delete()
        self.assertEqual(PrepAnswer.objects.count(), 0)
        self.assertEqual(PrepChallenge.objects.count(), 0)
