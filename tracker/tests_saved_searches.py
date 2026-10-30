"""Saved searches: extra, named role lists searched alongside the profile's own target_roles."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from tracker.models import SavedSearch, UserProfile
from tracker.services import scan

User = get_user_model()
PW = "correct-horse-battery-staple"


def user(name, target_roles=""):
    u = User.objects.create_user(name, email=f"{name}@example.com", password=PW)
    UserProfile.objects.filter(user=u).update(target_roles=target_roles)
    return u


class RolesUnion(TestCase):
    def test_enabled_searches_add_to_the_profiles_own_roles(self):
        owner = user("alice", target_roles="Backend Engineer")
        SavedSearch.objects.create(owner=owner, name="Remote", target_roles="Solutions Architect\nSRE")
        self.assertEqual(scan._roles(owner), ["backend engineer", "solutions architect", "sre"])

    def test_disabled_search_is_skipped_entirely(self):
        owner = user("alice", target_roles="Backend Engineer")
        SavedSearch.objects.create(owner=owner, name="Off", target_roles="Solutions Architect", enabled=False)
        self.assertEqual(scan._roles(owner), ["backend engineer"])

    def test_duplicate_roles_are_not_repeated(self):
        owner = user("alice", target_roles="Backend Engineer")
        SavedSearch.objects.create(owner=owner, name="Dup", target_roles="backend engineer\nSRE")
        self.assertEqual(scan._roles(owner), ["backend engineer", "sre"])

    def test_someone_elses_saved_search_never_counts(self):
        owner = user("alice", target_roles="Backend Engineer")
        other = user("bob", target_roles="")
        SavedSearch.objects.create(owner=other, name="Not mine", target_roles="Solutions Architect")
        self.assertEqual(scan._roles(owner), ["backend engineer"])


@override_settings(STILLOPEN_MAX_SAVED_SEARCHES=2)
class Api(TestCase):
    def setUp(self):
        self.a = user("alice")
        self.b = user("bob")
        self.client.login(username="alice", password=PW)

    def add(self, name="Remote", target_roles="Backend Engineer", **kw):
        payload = {"name": name, "target_roles": target_roles, **kw}
        return self.client.post("/api/v1/saved-searches", data=json.dumps(payload), content_type="application/json")

    def test_add_list_toggle_delete(self):
        r = self.add()
        self.assertEqual(r.status_code, 200, r.content)
        item = r.json()
        self.assertEqual(item["name"], "Remote")
        self.assertTrue(item["enabled"])

        listed = self.client.get("/api/v1/saved-searches").json()["saved_searches"]
        self.assertEqual([s["name"] for s in listed], ["Remote"])

        r = self.client.patch(f"/api/v1/saved-searches/{item['id']}", data=json.dumps({"enabled": False}), content_type="application/json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(r.json()["enabled"])

        r = self.client.delete(f"/api/v1/saved-searches/{item['id']}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/saved-searches").json()["saved_searches"], [])

    def test_name_must_be_unique_per_owner(self):
        self.assertEqual(self.add(name="Remote").status_code, 200)
        r = self.add(name="remote")
        self.assertEqual(r.status_code, 400)

    def test_blank_roles_rejected(self):
        r = self.add(target_roles="   ")
        self.assertEqual(r.status_code, 400)

    def test_limit_is_enforced(self):
        self.assertEqual(self.add(name="One").status_code, 200)
        self.assertEqual(self.add(name="Two").status_code, 200)
        r = self.add(name="Three")
        self.assertEqual(r.status_code, 400)

    def test_another_users_saved_search_is_a_404(self):
        self.client.logout()
        self.client.login(username="bob", password=PW)
        mine = self.add(name="Bob's").json()
        self.client.logout()
        self.client.login(username="alice", password=PW)
        self.assertEqual(self.client.get("/api/v1/saved-searches").json()["saved_searches"], [])
        self.assertEqual(self.client.patch(f"/api/v1/saved-searches/{mine['id']}", data=json.dumps({"enabled": False}), content_type="application/json").status_code, 404)
        self.assertEqual(self.client.delete(f"/api/v1/saved-searches/{mine['id']}").status_code, 404)

    def test_signed_out_is_unauthorized(self):
        self.client.logout()
        self.assertEqual(self.client.get("/api/v1/saved-searches").status_code, 401)
