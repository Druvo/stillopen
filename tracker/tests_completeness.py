"""Guards for the whole product: no personal data is left out of the export or left behind by an account deletion, and no API route lacks a fixture.

Models are discovered generically (`apps.get_models()`), so a model added later is caught without anyone remembering to list it."""
import json
import re

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import models
from django.test import TestCase

from tracker.tests_api import BASE, person, routes, world

User = get_user_model()
USER_MODEL = settings.AUTH_USER_MODEL.lower()
# Models that belong to a person but are deliberately not in the data export, and why.
EXPORT_EXCLUDED = {
    "tracker.apitoken": "access tokens are credentials (only a hash is kept); exporting them would be a risk, not a favour",
    "tracker.aiusageevent": "a log of provider calls (tokens and cost), no personal content",
    "tracker.scanrun": "operational log of searches",
    "tracker.scanlogentry": "operational log of searches",
    "tracker.livenessrun": "operational log of open/closed checks",
    "tracker.knowledgechunk": "a derived search index of the documents that are exported",
    "tracker.prepchallengeitem": "which questions a practice day held; derived from the answers and practice days, which are exported",
    "tracker.posting": "a fact about a company's public job board, shared by everyone who watches that board (CLAUDE.md), not one person's data",
    "tracker.postingsighting": "the same shared fact: when a posting was seen on a public board",
}


def owner_path(model, _seen=()):
    """FK names leading from `model` to the user model (directly, or through a parent that owns it), else None."""
    for field in model._meta.get_fields():
        if isinstance(field, models.ForeignKey) and field.related_model._meta.label_lower == USER_MODEL:
            return [field.name]
    for field in model._meta.get_fields():
        if field.concrete and isinstance(field, models.ForeignKey) and field.remote_field.on_delete is models.CASCADE:
            parent = field.related_model
            if parent is model or parent in _seen or parent._meta.app_label != "tracker":
                continue
            rest = owner_path(parent, _seen + (model,))
            if rest:
                return [field.name] + rest
    return None


def personal_models():
    return [m for m in apps.get_app_config("tracker").get_models() if owner_path(m)]


def accessors_to(model):
    """Every name a parent uses to reach `model` (reverse relations): how the export walks into child tables."""
    names = set()
    for other in apps.get_models():
        for field in other._meta.get_fields():
            if field.auto_created and (field.one_to_many or field.one_to_one) and field.related_model is model:
                names.add(field.get_accessor_name())
    return names


class ExportCoversEveryPersonalModel(TestCase):
    def test_every_model_with_an_owner_is_in_the_export_or_explicitly_excluded(self):
        from tracker import views

        with open(views.__file__, encoding="utf-8") as handle:
            source = handle.read()
        missing = []
        for model in personal_models():
            label = model._meta.label_lower
            if label in EXPORT_EXCLUDED:
                continue
            names = {model.__name__} | accessors_to(model)
            if not any(re.search(rf"\b{re.escape(n)}\b", source) for n in names):
                missing.append(label)
        self.assertEqual(missing, [], f"hold a person's data but are not in views.export_data (add them, or to EXPORT_EXCLUDED with a reason): {missing}")

    def test_the_exclusions_are_still_personal_models(self):
        known = {m._meta.label_lower for m in personal_models()}
        for label in EXPORT_EXCLUDED:
            self.assertIn(label, known, f"{label} is excluded but is not a personal model any more: remove it from the list")


class DeletingAnAccountLeavesNothing(TestCase):
    def setUp(self):
        cache.clear()
        self.gone, self.stays = person("goner"), person("stayer")
        world(self.gone)  # a job and a started prep plan with lessons, tasks and questions, plus whatever each tracker/world_*.py adds
        world(self.stays)

    def count(self, user_id):
        out = {}
        for model in personal_models():
            path = "__".join(owner_path(model))
            out[model._meta.label_lower] = model.objects.filter(**{f"{path}__pk": user_id}).count()
        return out

    def test_nothing_owner_linked_remains_and_the_other_person_is_untouched(self):
        before_other = self.count(self.stays.pk)
        self.assertGreater(sum(self.count(self.gone.pk).values()), 5)
        self.client.force_login(self.gone)
        r = self.client.post(f"{BASE}/account/delete", data=json.dumps({"confirm": self.gone.username}), content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(User.objects.filter(pk=self.gone.pk).exists())
        left = {k: v for k, v in self.count(self.gone.pk).items() if v}
        self.assertEqual(left, {}, f"rows left behind: {left}")
        self.assertEqual(self.count(self.stays.pk), before_other)

    def test_no_row_in_any_model_still_points_at_the_deleted_user(self):
        user_id = self.gone.pk
        self.client.force_login(self.gone)
        self.client.post(f"{BASE}/account/delete", data=json.dumps({"confirm": self.gone.username}), content_type="application/json")
        for model in apps.get_models():
            for field in model._meta.get_fields():
                if isinstance(field, models.ForeignKey) and field.concrete and field.related_model._meta.label_lower == USER_MODEL:
                    self.assertFalse(model.objects.filter(**{f"{field.name}_id": user_id}).exists(), f"{model._meta.label} still points at the deleted user")


class EveryRouteHasAFixture(TestCase):
    def test_no_path_parameter_lacks_a_world_fixture(self):
        ids = world(person("fixture"))
        missing = sorted({(method, path, name) for method, path in routes() for name in re.findall(r"\{(\w+)\}", path) if name not in ids})
        self.assertEqual(missing, [], f"routes whose path parameters no tracker/world_*.py fixture provides: {missing}")
