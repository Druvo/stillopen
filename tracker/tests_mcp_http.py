"""The web MCP endpoint and the page where people make tokens: one token, one person; read-only means read-only."""
import json
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from tracker.models import ApiToken, Application, SiteConfig, Status

User = get_user_model()


def rpc(client, token, method, params=None, id=1, **extra):
    body = {"jsonrpc": "2.0", "method": method}
    if id is not None:
        body["id"] = id
    if params is not None:
        body["params"] = params
    headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
    return client.post(reverse("mcp_endpoint"), data=json.dumps(body), content_type="application/json", **headers, **extra)


def call(client, token, name, arguments=None):
    return rpc(client, token, "tools/call", {"name": name, "arguments": arguments or {}}).json()


def text_of(reply) -> str:
    return "".join(part.get("text", "") for part in reply["result"]["content"])


class McpHttpBase(TestCase):
    def setUp(self):
        cache.clear()
        self.status = Status.objects.get(name="Evaluated")
        self.ann = User.objects.create_user("ann", email="ann@example.com", password="x" * 20)
        self.bob = User.objects.create_user("bob", email="bob@example.com", password="x" * 20)
        Application.objects.create(owner=self.ann, company="AnnCo", role="Dev", status=self.status, score=4.0)
        Application.objects.create(owner=self.bob, company="BobCo", role="Dev", status=self.status, score=4.0)
        self.read_record, self.read = ApiToken.issue(self.ann, "read", can_write=False)
        self.write_record, self.write = ApiToken.issue(self.ann, "write", can_write=True)
        self.bob_record, self.bob_token = ApiToken.issue(self.bob, "bob", can_write=True)


class Protocol(McpHttpBase):
    def test_initialize_lists_tools_and_never_needs_cookies(self):
        reply = rpc(self.client, self.read, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "t", "version": "1"}}).json()
        self.assertEqual(reply["result"]["serverInfo"]["name"], "stillopen")
        self.assertIn("tools", reply["result"]["capabilities"])
        self.assertIn("instructions", reply["result"])

    def test_notifications_get_202_and_get_is_not_allowed(self):
        self.assertEqual(rpc(self.client, self.read, "notifications/initialized", id=None).status_code, 202)
        self.assertEqual(self.client.get(reverse("mcp_endpoint")).status_code, 405)

    def test_ping_and_unknown_methods(self):
        self.assertEqual(rpc(self.client, self.read, "ping").json()["result"], {})
        self.assertEqual(rpc(self.client, self.read, "nonsense/method").json()["error"]["code"], -32601)

    def test_bad_json_is_a_parse_error(self):
        r = self.client.post(reverse("mcp_endpoint"), data="{not json", content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.read}")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["error"]["code"], -32700)


class Auth(McpHttpBase):
    def test_no_token_or_a_wrong_one_is_401(self):
        for token in (None, "so_wrong", "not-even-prefixed", "x" * 300):
            self.assertEqual(rpc(self.client, token, "ping").status_code, 401, token)
        self.assertIn("Bearer", rpc(self.client, None, "ping")["WWW-Authenticate"])

    def test_a_session_cookie_alone_gets_nothing(self):
        self.client.force_login(self.ann)
        self.assertEqual(rpc(self.client, None, "tools/list").status_code, 401)

    def test_revoked_expired_and_deactivated_owners_are_refused(self):
        ApiToken.objects.filter(pk=self.read_record.pk).update(revoked_at=timezone.now())
        self.assertEqual(rpc(self.client, self.read, "ping").status_code, 401)
        ApiToken.objects.filter(pk=self.write_record.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(rpc(self.client, self.write, "ping").status_code, 401)
        User.objects.filter(pk=self.bob.pk).update(is_active=False)
        self.assertEqual(rpc(self.client, self.bob_token, "ping").status_code, 401)

    def test_only_a_hash_is_stored(self):
        self.assertNotEqual(self.read, self.read_record.token_hash)
        self.assertEqual(len(self.read_record.token_hash), 64)
        self.assertTrue(self.read.startswith(self.read_record.hint))
        self.assertLess(len(self.read_record.hint), len(self.read))

    def test_cross_site_browser_requests_are_refused(self):
        self.assertEqual(rpc(self.client, self.read, "ping", HTTP_ORIGIN="https://evil.example").status_code, 403)
        self.assertEqual(rpc(self.client, self.read, "ping", HTTP_ORIGIN="http://testserver").status_code, 200)

    @override_settings(STILLOPEN_MCP_BAD_TOKENS_PER_MINUTE=3)
    def test_guessing_tokens_is_throttled(self):
        for _ in range(3):
            self.assertEqual(rpc(self.client, "so_guess", "ping").status_code, 401)
        self.assertEqual(rpc(self.client, "so_guess", "ping").status_code, 429)

    @override_settings(STILLOPEN_MCP_CALLS_PER_MINUTE=2)
    def test_a_token_is_rate_limited(self):
        self.assertEqual(rpc(self.client, self.read, "ping").status_code, 200)
        self.assertEqual(rpc(self.client, self.read, "ping").status_code, 200)
        self.assertEqual(rpc(self.client, self.read, "ping").status_code, 429)

    def test_the_admin_switch_turns_the_endpoint_off(self):
        SiteConfig.objects.filter(pk=1).update(mcp_remote_enabled=False)
        self.assertEqual(rpc(self.client, self.read, "ping").status_code, 404)
        self.client.force_login(self.ann)
        self.assertEqual(self.client.get(reverse("assistant")).status_code, 404)

    def test_last_used_is_recorded(self):
        self.assertIsNone(ApiToken.objects.get(pk=self.read_record.pk).last_used_at)
        rpc(self.client, self.read, "ping")
        self.assertIsNotNone(ApiToken.objects.get(pk=self.read_record.pk).last_used_at)


class Tools(McpHttpBase):
    def test_read_only_token_lists_only_tools_that_cannot_change_anything(self):
        names = {t["name"] for t in rpc(self.client, self.read, "tools/list").json()["result"]["tools"]}
        self.assertIn("summary", names)
        self.assertIn("list_applications", names)
        for blocked in ("add_application", "update_status", "save_evaluation", "add_note", "check_open", "record_application"):
            self.assertNotIn(blocked, names)
        everything = {t["name"] for t in rpc(self.client, self.write, "tools/list").json()["result"]["tools"]}
        self.assertIn("add_application", everything)
        self.assertFalse({n for n in everything if "delete" in n or "remove" in n})

    def test_read_only_token_cannot_call_a_write_tool(self):
        reply = call(self.client, self.read, "add_application", {"company": "X", "role": "Y"})
        self.assertIn("read-only", reply["error"]["message"])
        self.assertFalse(Application.objects.filter(company="X").exists())

    def test_a_token_acts_only_for_its_owner(self):
        mine = text_of(call(self.client, self.read, "list_applications"))
        self.assertIn("AnnCo", mine)
        self.assertNotIn("BobCo", mine)
        theirs = text_of(call(self.client, self.bob_token, "list_applications"))
        self.assertIn("BobCo", theirs)
        self.assertNotIn("AnnCo", theirs)

    def test_another_persons_job_cannot_be_read_or_changed_by_id(self):
        bobs = Application.objects.get(owner=self.bob)
        for name, args in (("get_application", {"app_id": bobs.pk}), ("add_note", {"app_id": bobs.pk, "text": "hi"}),
                           ("update_status", {"app_id": bobs.pk, "status": "Applied"})):
            self.assertTrue(call(self.client, self.write, name, args)["result"]["isError"], name)
        bobs.refresh_from_db()
        self.assertEqual(bobs.events.count(), 0)
        self.assertEqual(bobs.status, self.status)

    def test_a_write_token_creates_rows_owned_by_its_person(self):
        reply = call(self.client, self.write, "add_application", {"company": "NewCo", "role": "Engineer"})
        self.assertFalse(reply["result"].get("isError"))
        self.assertEqual(Application.objects.get(company="NewCo").owner, self.ann)

    def test_bad_arguments_come_back_as_a_tool_error_not_a_crash(self):
        self.assertTrue(call(self.client, self.write, "get_application", {"app_id": "not a number"})["result"]["isError"])
        self.assertIn("error", call(self.client, self.write, "no_such_tool"))

    def test_each_request_is_independent_even_on_one_thread(self):
        a = text_of(call(self.client, self.read, "list_applications"))
        b = text_of(call(self.client, self.bob_token, "list_applications"))
        a2 = text_of(call(self.client, self.read, "list_applications"))
        self.assertIn("AnnCo", a)
        self.assertIn("BobCo", b)
        self.assertIn("AnnCo", a2)
        self.assertNotIn("BobCo", a2)


class TokenPage(McpHttpBase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.ann)

    def test_page_loads_and_is_linked_from_the_profile(self):
        self.assertContains(self.client.get(reverse("profile")), reverse("assistant"))
        page = self.client.get(reverse("assistant"))
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, self.read)  # a token is never shown again
        self.assertContains(page, self.read_record.hint)

    def test_login_is_required(self):
        self.client.logout()
        self.assertEqual(self.client.get(reverse("assistant")).status_code, 302)
        self.assertEqual(self.client.post(reverse("assistant_create"), {"name": "x"}).status_code, 302)

    def test_making_a_token_shows_it_once_with_ready_commands(self):
        r = self.client.post(reverse("assistant_create"), {"name": "Laptop", "access": "write", "expires": "30"})
        self.assertEqual(r.status_code, 200)
        raw = r.context["new_token"]
        self.assertContains(r, "claude mcp add --transport http stillopen")
        self.assertContains(r, raw)
        record = ApiToken.objects.get(name="Laptop")
        self.assertTrue(record.can_write)
        self.assertEqual(record.owner, self.ann)
        self.assertEqual(ApiToken.lookup(raw), record)
        self.assertNotContains(self.client.get(reverse("assistant")), raw)

    def test_bad_expiry_and_name_fall_back_safely(self):
        self.client.post(reverse("assistant_create"), {"name": "", "access": "root", "expires": "99999"})
        record = ApiToken.objects.order_by("-pk").first()
        self.assertEqual(record.name, "Assistant")
        self.assertFalse(record.can_write)  # anything but "write" is read-only
        self.assertIsNotNone(record.expires_at)

    @override_settings(STILLOPEN_MAX_API_TOKENS=2)
    def test_the_number_of_active_tokens_is_capped(self):
        before = ApiToken.objects.filter(owner=self.ann).count()
        self.client.post(reverse("assistant_create"), {"name": "third"})
        self.assertEqual(ApiToken.objects.filter(owner=self.ann).count(), before)

    def test_revoking_stops_the_token_and_only_owners_can_revoke(self):
        self.assertEqual(rpc(self.client, self.read, "ping").status_code, 200)
        self.client.post(reverse("assistant_revoke", args=[self.read_record.pk]))
        self.assertEqual(rpc(self.client, self.read, "ping").status_code, 401)
        self.assertEqual(self.client.post(reverse("assistant_revoke", args=[self.bob_record.pk])).status_code, 404)
        self.assertIsNone(ApiToken.objects.get(pk=self.bob_record.pk).revoked_at)
        self.assertEqual(self.client.get(reverse("assistant_revoke", args=[self.read_record.pk])).status_code, 405)

    def test_tokens_vanish_with_the_account(self):
        self.ann.delete()
        self.assertEqual(ApiToken.objects.filter(name__in=["read", "write"]).count(), 0)
