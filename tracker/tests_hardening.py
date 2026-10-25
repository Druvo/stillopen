"""Platform hardening: the shared cache choice, atomic throttling, sign-up and sign-in abuse protection (no CAPTCHA, nothing third-party),
the reverse-proxy sanity checks, and DNS-rebinding-proof outbound requests."""
import datetime as dt
import http.server
import re
import socket
import ssl
import tempfile
import threading
import time
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.core.checks import Warning as CheckWarning
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from config.cache_config import LOCAL_MEMORY, REDIS, build_caches
from tracker import checks, middleware
from tracker.models import SiteConfig
from tracker.services import abuse, netguard, throttle
from tracker.services.netguard import FetchError

User = get_user_model()
PW = "correct-horse-battery-staple"
PUBLIC = "93.184.216.34"


# ---- 1. the shared cache ------------------------------------------------------------------------------------------------

class CacheChoice(SimpleTestCase):
    def test_without_redis_the_cache_is_each_process_s_own_memory(self):
        self.assertEqual(build_caches({}), {"default": {"BACKEND": LOCAL_MEMORY}})
        self.assertEqual(build_caches({"REDIS_URL": "   "})["default"]["BACKEND"], LOCAL_MEMORY)

    def test_with_redis_url_it_is_djangos_own_redis_backend(self):
        caches = build_caches({"REDIS_URL": " redis://redis:6379/0 "})
        self.assertEqual(caches["default"]["BACKEND"], REDIS)
        self.assertEqual(caches["default"]["BACKEND"], "django.core.cache.backends.redis.RedisCache")
        self.assertEqual(caches["default"]["LOCATION"], "redis://redis:6379/0")
        self.assertEqual(caches["default"]["KEY_PREFIX"], "stillopen")
        self.assertEqual(build_caches({"REDIS_URL": "redis://x", "STILLOPEN_CACHE_PREFIX": "site2"})["default"]["KEY_PREFIX"], "site2")

    def test_redis_is_only_in_the_hosting_requirements(self):
        root = Path(__file__).resolve().parent.parent
        self.assertIn("redis>=5", (root / "requirements-hosting.txt").read_text(encoding="utf-8"))
        self.assertNotIn("redis", (root / "requirements.txt").read_text(encoding="utf-8").lower())

    def test_the_compose_file_adds_redis_without_disk_state_and_with_a_healthcheck(self):
        root = Path(__file__).resolve().parent.parent
        text = (root / "docker-compose.redis.yml").read_text(encoding="utf-8")
        self.assertIn("redis:7-alpine", text)
        self.assertIn("--appendonly", text)
        self.assertIn("healthcheck", text)
        self.assertIn("REDIS_URL: redis://redis:6379/0", text)
        self.assertNotIn("\nvolumes:", text)

    def test_every_compose_service_rotates_its_logs(self):
        root = Path(__file__).resolve().parent.parent
        for name in ("docker-compose.yml", "docker-compose.selfhost.yml", "docker-compose.postgres.yml", "docker-compose.caddy.yml", "docker-compose.redis.yml"):
            blocks, current, in_services = {}, None, False
            for line in (root / name).read_text(encoding="utf-8").splitlines():
                if re.match(r"^\S", line):
                    in_services = line.startswith("services:")
                    current = None
                elif in_services and (m := re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)):
                    current = m.group(1)
                    blocks[current] = []
                elif current:
                    blocks[current].append(line)
            self.assertTrue(blocks, name)
            for service, lines in blocks.items():
                body = "\n".join(lines)
                if service == "stillopen" and name != "docker-compose.selfhost.yml":
                    continue  # an override file that only adds settings to a service the main file defines
                if name == "docker-compose.postgres.yml" and service == "stillopen":
                    continue
                self.assertIn("json-file", body, f"{name}: {service}")
                self.assertIn('max-size: "10m"', body, f"{name}: {service}")
                self.assertIn('max-file: "3"', body, f"{name}: {service}")


class FakeRedisLikeCache:
    """Just enough of Django's cache API to replay the race two workers can run into: `incr` on a key that does not exist yet."""

    def __init__(self, other_worker_creates_first=False):
        self.data = {}
        self.calls = []
        self.other = other_worker_creates_first

    def incr(self, key):
        self.calls.append("incr")
        if key not in self.data:
            raise ValueError(key)
        self.data[key] += 1
        return self.data[key]

    def add(self, key, value, timeout=None):
        self.calls.append("add")
        if self.other:
            self.data[key] = 1  # the other worker got there between our incr and our add
            self.other = False
        if key in self.data:
            return False
        self.data[key] = value
        return True

    def set(self, key, value, timeout=None):
        self.calls.append("set")
        self.data[key] = value


class AtomicThrottle(TestCase):
    def test_counting_and_the_limit(self):
        cache.clear()
        user = User.objects.create_user("thr", password=PW)
        self.assertEqual([throttle.throttled(user, "x", 2) for _ in range(4)], [False, False, True, True])
        self.assertFalse(throttle.throttled(User.objects.create_user("thr2", password=PW), "x", 2))  # someone else's count

    def test_first_hit_creates_the_counter_with_one_atomic_add_not_a_zero_then_incr(self):
        fake = FakeRedisLikeCache()
        with mock.patch.object(throttle, "cache", fake):
            self.assertEqual(throttle.bump("k", 60), 1)
            self.assertEqual(throttle.bump("k", 60), 2)
        self.assertEqual(fake.calls, ["incr", "add", "incr"])

    def test_a_worker_that_loses_the_creation_race_still_counts_every_hit(self):
        fake = FakeRedisLikeCache(other_worker_creates_first=True)
        with mock.patch.object(throttle, "cache", fake):
            self.assertEqual(throttle.bump("k", 60), 2)  # the other worker's 1 plus ours, nothing overwritten
        self.assertNotIn("set", fake.calls)

    def test_the_mcp_counters_use_the_same_helper(self):
        from tracker import views_mcp

        cache.clear()
        self.assertEqual([views_mcp._bump("mcp-calls:1", 60) for _ in range(3)], [1, 2, 3])


# ---- 2. sign-up and sign-in abuse protection ----------------------------------------------------------------------------------

class RateLimitNumbers(TestCase):
    def test_defaults(self):
        limits = abuse.build_rate_limits(SiteConfig.load())
        self.assertEqual(limits["signup"], "5/h/ip")
        self.assertEqual(limits["login_failed"], "10/10m/ip,5/5m/key")
        self.assertEqual(limits["reset_password"], "5/h/ip,5/h/key")
        self.assertEqual(limits["confirm_email"], "1/180s/key")
        self.assertEqual(limits["change_password"], "5/m/user")

    def test_the_admin_numbers_reach_allauths_limiter(self):
        from allauth.account import app_settings

        SiteConfig.objects.filter(pk=1).update(signup_per_hour_per_ip=2, login_failures_per_account=3, email_resend_seconds=0)
        limits = app_settings.RATE_LIMITS
        self.assertEqual(limits["signup"], "2/h/ip")
        self.assertIn("3/5m/key", limits["login_failed"])
        self.assertIsNone(limits["confirm_email"])  # 0 means no wait
        self.assertEqual(limits["login"], "30/m/ip")  # allauth's own defaults still fill the rest

    def test_an_environment_variable_still_wins(self):
        with mock.patch.dict("os.environ", {"STILLOPEN_SIGNUP_RATE": "9/m/ip", "STILLOPEN_LOGIN_FAILED_RATE": "7/m/ip"}):
            limits = abuse.build_rate_limits(SiteConfig.load())
        self.assertEqual((limits["signup"], limits["login_failed"]), ("9/m/ip", "7/m/ip"))

    def test_wrong_passwords_trip_a_plain_message_then_the_right_one_waits(self):
        cache.clear()
        User.objects.create_user("victim", email="victim@example.com", password=PW)
        SiteConfig.objects.filter(pk=1).update(login_failures_per_account=3)
        url = reverse("account_login")
        last = None
        for _ in range(5):
            last = self.client.post(url, {"login": "victim", "password": "wrong-wrong-wrong"})
        self.assertContains(last, "Too many failed login attempts", status_code=200)
        right = self.client.post(url, {"login": "victim", "password": PW})
        self.assertNotIn("_auth_user_id", self.client.session)  # the limit holds even for the right password
        self.assertContains(right, "Too many failed login attempts")

    def test_a_flood_of_signups_from_one_address_gets_the_friendly_429_page(self):
        cache.clear()
        SiteConfig.objects.filter(pk=1).update(signup_mode="open", signup_per_hour_per_ip=2)
        with override_settings(STILLOPEN_SIGNUP_MIN_SECONDS=0):
            codes = [self.client.post(reverse("account_signup"), {"email": f"p{i}@example.com", "password1": PW}) for i in range(4)]
        self.assertEqual([r.status_code for r in codes][:2], [302, 302])
        self.assertEqual(codes[3].status_code, 429)
        self.assertContains(codes[3], "Too many tries", status_code=429)
        self.assertContains(codes[3], "wait a few minutes", status_code=429)

    def test_password_reset_requests_are_limited_per_address(self):
        cache.clear()
        SiteConfig.objects.filter(pk=1).update(password_reset_per_hour=2)
        codes = [self.client.post(reverse("account_reset_password"), {"email": "nobody@example.com"}).status_code for _ in range(4)]
        self.assertIn(429, codes)


class SignupTraps(TestCase):
    def setUp(self):
        cache.clear()
        SiteConfig.objects.filter(pk=1).update(signup_mode="open")
        self.url = reverse("account_signup")

    def token(self):
        tag = re.search(r"<input[^>]*name=\"form_started\"[^>]*>", self.client.get(self.url).content.decode()).group(0)
        return re.search(r'value="([^"]+)"', tag).group(1)

    def post(self, email="kim@example.com", **extra):
        data = {"email": email, "password1": PW}
        data.update(extra)
        return self.client.post(self.url, data)

    def assertNeutral(self, response):
        """The same 'check your email' page a person would see, so a bot cannot tell it was turned away."""
        self.assertRedirects(response, reverse("account_email_verification_sent"), fetch_redirect_response=False)
        self.assertContains(self.client.get(reverse("account_email_verification_sent")), "Check your email")

    def assertNoAccount(self, email="kim@example.com"):
        self.assertFalse(User.objects.filter(email=email).exists())
        self.assertEqual(mail.outbox, [])

    def test_the_trap_is_hidden_accessibly_and_asks_nothing_of_people(self):
        page = self.client.get(self.url).content.decode()
        box = re.search(r"<input[^>]*name=\"website\"[^>]*>", page).group(0)
        self.assertIn('tabindex="-1"', box)
        self.assertIn('autocomplete="off"', box)
        self.assertIn('aria-hidden="true"', box)
        self.assertIn("left:-10000px", page)
        self.assertNotIn('required', box)

    @override_settings(STILLOPEN_SIGNUP_MIN_SECONDS=0)
    def test_a_filled_trap_gets_the_neutral_page_and_no_account(self):
        self.assertNeutral(self.post(website="http://spam.example"))
        self.assertNoAccount()

    def test_too_fast_gets_the_neutral_page_and_no_account(self):
        token = self.token()
        with override_settings(STILLOPEN_SIGNUP_MIN_SECONDS=2):
            self.assertNeutral(self.post(form_started=token))
        self.assertNoAccount()

    def test_the_default_minimum_comes_from_the_admin_and_is_two_seconds(self):
        self.assertEqual(abuse.signup_min_seconds(), 2)
        SiteConfig.objects.filter(pk=1).update(signup_min_seconds=10)
        self.assertEqual(abuse.signup_min_seconds(), 10)
        token = self.token()
        self.assertNeutral(self.post(form_started=token))  # well inside ten seconds
        with mock.patch("time.time", return_value=time.time() + 11):
            self.post(form_started=token)
        self.assertTrue(User.objects.filter(email="kim@example.com").exists())

    def test_a_normal_person_gets_through_and_is_told_to_check_their_email(self):
        token = self.token()
        with mock.patch("time.time", return_value=time.time() + 6):
            response = self.post(form_started=token)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(User.objects.filter(email="kim@example.com").exists())
        self.assertEqual(len(mail.outbox), 1)

    def test_a_token_can_make_only_one_account_a_replayed_page_is_turned_away(self):
        token = self.token()
        with mock.patch("time.time", return_value=time.time() + 6):
            self.post("first@example.com", form_started=token)
            self.assertNeutral(self.post("second@example.com", form_started=token))
        self.assertTrue(User.objects.filter(email="first@example.com").exists())
        self.assertFalse(User.objects.filter(email="second@example.com").exists())

    def test_a_person_who_mistyped_can_resubmit_the_same_page(self):
        token = self.token()
        with mock.patch("time.time", return_value=time.time() + 6):
            bad = self.post(password1="short", form_started=token)
            self.assertEqual(bad.status_code, 200)  # the form again, with a plain reason
            self.post(form_started=token)
        self.assertTrue(User.objects.filter(email="kim@example.com").exists())

    def test_an_old_page_has_to_be_reloaded_and_says_so(self):
        token = self.token()
        SiteConfig.objects.filter(pk=1).update(signup_form_max_hours=1)
        with mock.patch("time.time", return_value=time.time() + 2 * 3600):
            response = self.post(form_started=token)
        self.assertContains(response, "This page expired")
        self.assertNoAccount()

    def test_a_forged_or_missing_token_cannot_sign_up(self):
        for token in ("garbage", "", signing_dumps_with_wrong_salt()):
            response = self.post(form_started=token)
            self.assertContains(response, "This page expired")
        self.assertNoAccount()

    def test_the_switch_turns_the_traps_off(self):
        SiteConfig.objects.filter(pk=1).update(signup_protection=False)
        self.assertNeutralOrCreated()

    def assertNeutralOrCreated(self):
        self.post(form_started="garbage", website="x")
        self.assertTrue(User.objects.filter(email="kim@example.com").exists())

    def test_signup_page_loads_nothing_from_another_host(self):
        from tracker.tests_selfhost import EXTERNAL_ASSET

        page = self.client.get(self.url).content.decode()
        self.assertIsNone(EXTERNAL_ASSET.search(page))
        self.assertNotRegex(page, r"(?i)captcha|recaptcha|turnstile|hcaptcha")
        for ref in re.findall(r'(?:src|href|action)="(https?://[^"]+)"', page):
            self.assertTrue(ref.startswith("http://testserver"), ref)


def signing_dumps_with_wrong_salt():
    from django.core import signing

    return signing.dumps(time.time() - 100, salt="some-other-salt")


class AdminSettings(TestCase):
    def test_the_numbers_are_in_the_registration_tab(self):
        boss = User.objects.create_superuser("boss", "boss@example.com", PW)
        self.client.force_login(boss)
        page = self.client.get("/admin/tracker/siteconfig/1/change/").content.decode()
        for name in ("signup_protection", "signup_min_seconds", "signup_form_max_hours", "signup_per_hour_per_ip", "login_failures_per_ip",
                     "login_failures_per_account", "password_reset_per_hour", "email_resend_seconds"):
            self.assertIn(f'name="{name}"', page)


class ProxySanity(SimpleTestCase):
    def req(self, peer="203.0.113.9", forwarded=None):
        request = RequestFactory().get("/", REMOTE_ADDR=peer)
        if forwarded is not None:
            request.META["HTTP_X_FORWARDED_FOR"] = forwarded
        return request

    def test_not_behind_a_proxy_and_nothing_set_is_fine(self):
        self.assertIsNone(middleware.proxy_problem(self.req(), False, 0))

    def test_behind_a_proxy_with_no_count_every_visitor_looks_the_same(self):
        problem = middleware.proxy_problem(self.req(forwarded="198.51.100.4"), True, 0)
        self.assertIn("ALLAUTH_TRUSTED_PROXY_COUNT", problem)
        self.assertIn("every visitor looks like the proxy", problem)

    def test_a_missing_forwarded_header_is_named(self):
        self.assertIn("no X-Forwarded-For", middleware.proxy_problem(self.req(), True, 1))

    def test_the_local_health_check_without_the_header_is_not_a_problem(self):
        self.assertIsNone(middleware.proxy_problem(self.req(peer="127.0.0.1"), True, 1))

    def test_a_count_larger_than_the_chain_would_break_sign_in(self):
        self.assertIn("fewer addresses", middleware.proxy_problem(self.req(forwarded="198.51.100.4"), True, 2))

    def test_a_count_without_a_proxy_lets_visitors_forge_their_address(self):
        self.assertIn("forge", middleware.proxy_problem(self.req(forwarded="1.2.3.4"), False, 1))

    def test_correct_settings_are_quiet(self):
        self.assertIsNone(middleware.proxy_problem(self.req(forwarded="198.51.100.4"), True, 1))

    @override_settings(STILLOPEN_BEHIND_PROXY=True, ALLAUTH_TRUSTED_PROXY_COUNT=1)
    def test_the_middleware_logs_a_problem_once(self):
        cache.clear()
        seen = middleware.ProxyWatchMiddleware(lambda request: "response")
        with self.assertLogs("tracker.proxy", "WARNING") as logs:
            seen(self.req())
            seen(self.req())
        self.assertEqual(len(logs.records), 1)
        self.assertIn("X-Forwarded-For", logs.output[0])

    def run_check(self):
        return {w.id for w in checks.deployment_settings(None)}

    @override_settings(STILLOPEN_BEHIND_PROXY=True, ALLAUTH_TRUSTED_PROXY_COUNT=0)
    def test_manage_check_warns_about_a_proxy_without_a_count(self):
        self.assertIn("stillopen.W001", self.run_check())

    @override_settings(STILLOPEN_BEHIND_PROXY=False, ALLAUTH_TRUSTED_PROXY_COUNT=1)
    def test_manage_check_warns_about_a_count_without_a_proxy(self):
        self.assertIn("stillopen.W002", self.run_check())

    @override_settings(STILLOPEN_BEHIND_PROXY=True, ALLAUTH_TRUSTED_PROXY_COUNT=1)
    def test_manage_check_is_quiet_when_both_are_set(self):
        self.assertEqual(self.run_check() & {"stillopen.W001", "stillopen.W002"}, set())

    def test_several_workers_without_redis_is_a_warning_and_with_redis_is_not(self):
        with mock.patch.dict("os.environ", {"STILLOPEN_WORKERS": "4"}):
            self.assertIn("stillopen.W003", self.run_check())
            with override_settings(CACHES=build_caches({"REDIS_URL": "redis://x:6379/0"})):
                self.assertNotIn("stillopen.W003", self.run_check())
        with mock.patch.dict("os.environ", {"STILLOPEN_WORKERS": "1"}):
            self.assertNotIn("stillopen.W003", self.run_check())

    def test_checks_return_real_warnings(self):
        with override_settings(STILLOPEN_BEHIND_PROXY=True, ALLAUTH_TRUSTED_PROXY_COUNT=0):
            self.assertTrue(all(isinstance(w, CheckWarning) for w in checks.deployment_settings(None)))


# ---- 3. DNS rebinding -----------------------------------------------------------------------------------------------------------

def make_cert(common_name: str, directory: str):
    """A self-signed certificate valid only for `common_name`, written to files; returns (cert path, key path)."""
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, common_name)])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key()).serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1)).not_valid_after(now + dt.timedelta(days=2))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName(common_name)]), critical=False)
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    cert_path, key_path = Path(directory) / f"{common_name}.pem", Path(directory) / f"{common_name}.key"
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL, serialization.NoEncryption()))
    return str(cert_path), str(key_path)


class LocalServer:
    """A throwaway HTTP or HTTPS server on 127.0.0.1 that records the Host header and (for TLS) the server name the client asked for."""

    def __init__(self, cert=None):
        outer = self
        self.hosts, self.sni = [], []

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                outer.hosts.append(self.headers.get("Host"))
                body = b"hello from the pinned address"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        if cert:
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(*cert)
            context.sni_callback = lambda sock, name, ctx: self.sni.append(name)
            self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def as_public(*addresses):
    """Make the guard treat the loopback test server as a public address and have the resolver answer with `addresses`."""
    return (
        mock.patch.object(netguard, "_resolve", return_value=list(addresses)),
        mock.patch.object(netguard, "is_public_address", return_value=True),
    )


class AddressRules(SimpleTestCase):
    def test_what_counts_as_public(self):
        for ok in (PUBLIC, "8.8.8.8", "2606:4700:4700::1111"):
            self.assertTrue(netguard.is_public_address(ok), ok)
        for bad in ("127.0.0.1", "10.1.2.3", "192.168.0.1", "172.16.5.5", "169.254.169.254", "0.0.0.0", "::1", "fe80::1", "fc00::1", "224.0.0.1",
                    "100.64.0.1", "::ffff:127.0.0.1", "::ffff:10.0.0.1", "not-an-ip", "fe80::1%eth0"):
            self.assertFalse(netguard.is_public_address(bad), bad)

    def test_literal_ip_urls(self):
        for url in ("http://127.0.0.1/", "http://[::1]/", "http://10.0.0.5:8080/x", "http://169.254.169.254/latest/meta-data/", "http://[::ffff:127.0.0.1]/",
                    "http://0.0.0.0/", "http://100.64.0.1/", "ftp://example.com/x", "file:///etc/passwd", "http:///nohost"):
            with self.assertRaises(FetchError, msg=url):
                netguard.check_public_url(url)
        netguard.check_public_url("http://93.184.216.34/")
        netguard.check_public_url("https://[2606:4700:4700::1111]:8443/")

    def test_a_bad_port_is_a_fetch_error_not_a_crash(self):
        with self.assertRaises(FetchError):
            netguard.check_public_url("http://example.com:99999/")


class Rebinding(SimpleTestCase):
    def test_every_address_the_name_returns_must_be_public(self):
        """A name answering public AND private in one reply is refused outright."""
        with mock.patch.object(netguard, "_resolve", return_value=[PUBLIC, "127.0.0.1"]), \
                mock.patch("urllib3.util.connection.create_connection", side_effect=AssertionError("must never connect")):
            with self.assertRaisesMessage(FetchError, "not a public website"):
                netguard.safe_get("http://evil.example/")

    def test_the_name_is_resolved_once_so_a_second_private_answer_is_never_seen(self):
        """Public first, private second: the connection goes to the public address that was checked, and the second lookup never happens."""
        resolver = mock.Mock(side_effect=[[PUBLIC], ["127.0.0.1"]])
        connected = []

        def fake_connect(address, *args, **kwargs):
            connected.append(address[0])
            raise OSError("refused (the test never reaches the internet)")

        with mock.patch.object(netguard, "_resolve", resolver), mock.patch("urllib3.util.connection.create_connection", side_effect=fake_connect):
            with self.assertRaises(FetchError):
                netguard.safe_get("http://rebind.example/")
        self.assertEqual(resolver.call_count, 1)
        self.assertEqual(connected, [PUBLIC])
        self.assertNotIn("127.0.0.1", connected)

    def test_a_redirect_is_resolved_and_checked_again(self):
        first = mock.Mock(is_redirect=True, headers={"location": "http://internal.example/admin"})
        resolver = mock.Mock(side_effect=lambda host, port: ["127.0.0.1"] if host == "internal.example" else [PUBLIC])
        with mock.patch.object(netguard, "_resolve", resolver), mock.patch.object(netguard, "_get_pinned", return_value=first) as get:
            with self.assertRaises(FetchError):
                netguard.safe_get("https://jobs.example/1")
        self.assertEqual(get.call_count, 1)  # the private hop was never fetched
        self.assertEqual(resolver.call_count, 2)

    def test_a_redirect_to_a_literal_private_ip_is_refused(self):
        first = mock.Mock(is_redirect=True, headers={"location": "http://[::1]:8000/"})
        with mock.patch.object(netguard, "_resolve", return_value=[PUBLIC]), mock.patch.object(netguard, "_get_pinned", return_value=first):
            with self.assertRaises(FetchError):
                netguard.safe_get("https://jobs.example/1")

    def test_too_many_redirects(self):
        loop = mock.Mock(is_redirect=True, headers={"location": "https://jobs.example/again"})
        with mock.patch.object(netguard, "_resolve", return_value=[PUBLIC]), mock.patch.object(netguard, "_get_pinned", return_value=loop):
            with self.assertRaisesMessage(FetchError, "Too many redirects"):
                netguard.safe_get("https://jobs.example/1")

    def test_a_host_that_does_not_resolve_is_a_plain_error(self):
        with mock.patch.object(netguard.socket, "getaddrinfo", side_effect=socket.gaierror("no such host")):
            with self.assertRaisesMessage(FetchError, "Cannot resolve"):
                netguard.check_public_url("http://nowhere.invalid/")

    def test_resolve_deduplicates_and_keeps_both_families(self):
        infos = [(2, 1, 6, "", (PUBLIC, 80)), (10, 1, 6, "", ("2606:4700:4700::1111", 80, 0, 0)), (2, 1, 6, "", (PUBLIC, 80))]
        with mock.patch.object(netguard.socket, "getaddrinfo", return_value=infos):
            self.assertEqual(netguard._resolve("dual.example", 80), [PUBLIC, "2606:4700:4700::1111"])

    def test_with_a_proxy_in_the_environment_the_old_behaviour_is_kept(self):
        response = mock.Mock(is_redirect=False)
        with mock.patch.object(netguard, "_proxied", return_value=True), mock.patch.object(netguard.requests, "get", return_value=response) as get:
            self.assertIs(netguard._get_pinned("http://x.example/", [PUBLIC], 5, {}, True), response)
        get.assert_called_once()


class PinnedConnections(SimpleTestCase):
    """Real sockets on 127.0.0.1, with the guard told the loopback address is public; no internet involved."""

    def test_plain_http_connects_to_the_pinned_address_and_keeps_the_host_name_in_the_header(self):
        server = LocalServer()
        self.addCleanup(server.close)
        a, b = as_public("127.0.0.1")
        with a, b:
            response = netguard.safe_get(f"http://pinned.example:{server.port}/page")
        self.assertEqual((response.status_code, response.text), (200, "hello from the pinned address"))
        self.assertEqual(server.hosts, [f"pinned.example:{server.port}"])  # the name, not 127.0.0.1

    def test_https_verifies_the_certificate_against_the_host_name_and_sends_it_as_sni(self):
        with tempfile.TemporaryDirectory() as directory:
            cert = make_cert("pinned.example", directory)
            server = LocalServer(cert)
            self.addCleanup(server.close)
            a, b = as_public("127.0.0.1")
            with a, b:
                response = netguard.safe_get(f"https://pinned.example:{server.port}/", verify=cert[0])
            self.assertEqual(response.status_code, 200)
            self.assertEqual(server.sni, ["pinned.example"])
            self.assertEqual(server.hosts, [f"pinned.example:{server.port}"])

    def test_https_to_a_certificate_for_another_name_is_refused_even_though_the_ip_matches_a_real_server(self):
        with tempfile.TemporaryDirectory() as directory:
            cert = make_cert("someone-else.example", directory)
            server = LocalServer(cert)
            self.addCleanup(server.close)
            a, b = as_public("127.0.0.1")
            with a, b:
                with self.assertRaises(FetchError):
                    netguard.safe_get(f"https://pinned.example:{server.port}/", verify=cert[0])
            self.assertEqual(server.hosts, [])  # the request was never sent over the unverified connection

    def test_https_with_the_system_trust_store_rejects_a_self_signed_certificate(self):
        with tempfile.TemporaryDirectory() as directory:
            server = LocalServer(make_cert("pinned.example", directory))
            self.addCleanup(server.close)
            a, b = as_public("127.0.0.1")
            with a, b, self.assertRaises(FetchError):
                netguard.safe_get(f"https://pinned.example:{server.port}/")

    def test_a_dead_first_address_falls_through_to_the_next_one(self):
        server = LocalServer()
        self.addCleanup(server.close)
        real = __import__("urllib3.util.connection", fromlist=["create_connection"]).create_connection
        tried = []

        def flaky(address, *args, **kwargs):
            tried.append(address[0])
            if address[0] == "198.51.100.1":
                raise OSError("no route")
            return real(address, *args, **kwargs)

        a, b = as_public("198.51.100.1", "127.0.0.1")
        with a, b, mock.patch("urllib3.util.connection.create_connection", side_effect=flaky):
            response = netguard.safe_get(f"http://pinned.example:{server.port}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(tried, ["198.51.100.1", "127.0.0.1"])

    def test_the_adapter_pins_both_schemes_and_leaves_the_host_name_on_the_connection(self):
        adapter = netguard.PinnedAdapter("203.0.113.7")
        for scheme in ("http", "https"):
            pool = adapter.poolmanager.connection_from_url(f"{scheme}://real-name.example/")
            conn = pool._new_conn()
            self.assertEqual(conn.host, "real-name.example")  # Host header, SNI and certificate check use this
            with mock.patch("urllib3.util.connection.create_connection", side_effect=OSError("stop")) as connect:
                with self.assertRaises(Exception):
                    conn.connect()
            self.assertEqual(connect.call_args[0][0][0], "203.0.113.7")  # the socket goes to the pinned address
            if scheme == "https":
                self.assertIn(conn.cert_reqs, (ssl.CERT_REQUIRED, "CERT_REQUIRED"))
                self.assertIsNone(conn.assert_hostname)  # so the certificate is matched against `conn.host`
