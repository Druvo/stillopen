"""Prep plans: a short study plan, generated for one person and one job, that closes the skill gaps the fit check found.

Every row hangs off a plan, and every plan hangs off its owner: another person's plan is never reachable (the views and tests
enforce it). Imported at the end of models.py so Django registers these with the rest of the app.
"""
from django.conf import settings
from django.db import models


class PrepPlan(models.Model):
    STATUSES = [
        ("generating", "Being written"), ("failed", "Could not be written"), ("draft", "Draft: waiting for your OK"),
        ("active", "In progress"), ("done", "Finished"),
    ]

    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="prep_plans")
    application = models.ForeignKey("tracker.Application", null=True, blank=True, on_delete=models.SET_NULL, related_name="prep_plans",
                                    help_text="The job it was made for. The plan survives the job being deleted.")
    title = models.CharField(max_length=120, blank=True)
    summary = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=12, choices=STATUSES, default="generating")
    gap_skills = models.JSONField(default=list, blank=True, help_text="The gaps this plan was built to close, as found when it was made.")
    weeks_count = models.PositiveSmallIntegerField(default=4)
    hours_per_week = models.PositiveSmallIntegerField(default=6)
    generator = models.CharField(max_length=80, blank=True, help_text="Which provider and model wrote it, and the prompt version.")
    progress = models.CharField(max_length=160, blank=True, help_text="What the writer is doing right now, while status is 'generating'.")
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.title or f"Prep plan {self.pk}"

    @property
    def lessons(self):
        return PrepLesson.objects.filter(week__plan=self)

    def progress_counts(self) -> tuple[int, int]:
        lessons = self.lessons
        return lessons.filter(done_at__isnull=False).count(), lessons.count()


class PrepWeek(models.Model):
    plan = models.ForeignKey(PrepPlan, on_delete=models.CASCADE, related_name="weeks")
    order = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=160)
    goal = models.CharField(max_length=300, blank=True)
    hours = models.PositiveSmallIntegerField(default=6)

    class Meta:
        ordering = ["order", "id"]


class PrepLesson(models.Model):
    week = models.ForeignKey(PrepWeek, on_delete=models.CASCADE, related_name="lessons")
    order = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=200)
    topics = models.JSONField(default=list, blank=True)
    gap = models.CharField(max_length=120, blank=True, help_text="The gap this lesson serves.")
    sources = models.JSONField(default=list, blank=True, help_text="[{title, url, checked}]: official documentation to read.")
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]


class PrepMilestone(models.Model):
    KINDS = [("read", "Read"), ("build", "Build"), ("apply", "Apply")]

    week = models.ForeignKey(PrepWeek, on_delete=models.CASCADE, related_name="milestones")
    order = models.PositiveSmallIntegerField(default=0)
    kind = models.CharField(max_length=6, choices=KINDS)
    text = models.CharField(max_length=300)
    done_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["order", "id"]


class PrepTopic(models.Model):
    """A skill area the questions belong to, e.g. 'kubernetes-basics'. Evidence of what is weak is worked out per topic."""

    plan = models.ForeignKey(PrepPlan, on_delete=models.CASCADE, related_name="topics")
    slug = models.SlugField(max_length=80)
    title = models.CharField(max_length=120)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["plan", "slug"], name="uniq_prep_topic_slug")]
        ordering = ["title"]


class PrepQuestion(models.Model):
    KINDS = [("single", "One answer"), ("multi", "Several answers")]

    plan = models.ForeignKey(PrepPlan, on_delete=models.CASCADE, related_name="questions")
    topic = models.ForeignKey(PrepTopic, on_delete=models.CASCADE, related_name="questions")
    lesson = models.ForeignKey(PrepLesson, null=True, blank=True, on_delete=models.SET_NULL, related_name="questions")
    kind = models.CharField(max_length=6, choices=KINDS, default="single")
    prompt = models.CharField(max_length=400)
    choices = models.JSONField(default=list, help_text="The answer options as text, in the order shown.")
    correct = models.JSONField(default=list, help_text="Indexes into choices.")
    explanation = models.TextField(blank=True)
    sources = models.JSONField(default=list, help_text="At least one: [{title, url, checked}]. A question without a source is never saved.")
    checks = models.JSONField(default=dict, blank=True, help_text="Results of the automatic checks, e.g. {'sources_reachable': false}.")
    removed = models.BooleanField(default=False, help_text="Taken out by the person while reviewing the draft.")

    class Meta:
        ordering = ["id"]
