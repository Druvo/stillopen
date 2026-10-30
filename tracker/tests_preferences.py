"""Saved layout preferences (services/preferences.py), and the one admin-configurable default that uses them
differently from the rest: theme. A person's own saved choice always wins; absent one, the site's own
Appearance default applies -- not a hardcoded "light" -- so Site configuration > Appearance actually reaches
a signed-in account, not just the pre-hydration flash a signed-out visitor sees."""
from django.test import TestCase

from tracker.models import SiteConfig, UserProfile
from tracker.services import preferences
from tracker.tests_api import BASE, person


class ThemeDefault(TestCase):
    def test_normalize_falls_back_to_light_with_no_site_default_given(self):
        self.assertEqual(preferences.normalize({})["theme"], "light")
        self.assertEqual(preferences.normalize(None)["theme"], "light")

    def test_normalize_uses_the_given_site_default_for_someone_with_no_stored_choice(self):
        self.assertEqual(preferences.normalize({}, default_theme="dark")["theme"], "dark")
        self.assertEqual(preferences.normalize(None, default_theme="dark")["theme"], "dark")

    def test_an_invalid_site_default_is_ignored(self):
        self.assertEqual(preferences.normalize({}, default_theme="blue")["theme"], "light")

    def test_a_persons_own_stored_choice_always_wins_over_the_site_default(self):
        self.assertEqual(preferences.normalize({"theme": "light"}, default_theme="dark")["theme"], "light")
        self.assertEqual(preferences.normalize({"theme": "dark"}, default_theme="light")["theme"], "dark")

    def test_read_reflects_the_sites_own_configured_default(self):
        u = person("alice")
        profile = UserProfile.for_user(u)
        SiteConfig.objects.filter(pk=1).update(default_theme="dark")
        self.assertEqual(preferences.read(profile)["theme"], "dark")
        SiteConfig.objects.filter(pk=1).update(default_theme="light")
        self.assertEqual(preferences.read(profile)["theme"], "light")

    def test_me_and_preferences_endpoints_both_reflect_it_for_a_fresh_account(self):
        SiteConfig.objects.filter(pk=1).update(default_theme="dark")
        self.client.force_login(person("bob"))
        self.assertEqual(self.client.get(f"{BASE}/me").json()["preferences"]["theme"], "dark")
        self.assertEqual(self.client.get(f"{BASE}/preferences").json()["theme"], "dark")

    def test_saving_an_unrelated_preference_does_not_quietly_lock_in_light_over_the_site_default(self):
        """A write that never mentions theme must not downgrade an unset theme to the hardcoded default --
        it has to keep reading through the site's own configured one, the same as a plain GET would."""
        SiteConfig.objects.filter(pk=1).update(default_theme="dark")
        self.client.force_login(person("carol"))
        r = self.client.put(f"{BASE}/preferences", data='{"density": "compact"}', content_type="application/json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["theme"], "dark")
        self.assertEqual(r.json()["density"], "compact")

    def test_an_explicit_choice_opposite_the_site_default_is_kept_after_an_unrelated_save(self):
        SiteConfig.objects.filter(pk=1).update(default_theme="dark")
        self.client.force_login(person("dave"))
        self.client.put(f"{BASE}/preferences", data='{"theme": "light"}', content_type="application/json")
        r = self.client.put(f"{BASE}/preferences", data='{"density": "compact"}', content_type="application/json")
        self.assertEqual(r.json()["theme"], "light")  # the site default is "dark"; dave's own pick must not be overwritten
