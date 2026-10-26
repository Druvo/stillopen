"""Wider job search: Adzuna (keyed, per country), the open regional APIs (JobTech Sweden, Get on Board), the seed lists and the
rule that none of the new connectors reach the public board. All HTTP is mocked; recorded sample payloads live in fixtures_sources/."""
import io
import json
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from tracker import seed_sources
from tracker.admin import SiteConfigForm
from tracker.models import Application, JobSource, Posting, SearchArea, SiteConfig, UserProfile
from tracker.seed import ensure_default_sources
from tracker.services import adzuna, openboards, public, scan
from tracker.services.netguard import FetchError

User = get_user_model()
FIXTURES = Path(__file__).parent / "fixtures_sources"
KEY = "adz-SECRET-key-98765"
APP_ID = "adz-app-id-1"


def fixture(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf8"))


def reply(payload, status=200):
    r = mock.Mock(status_code=status)
    r.json.return_value = payload
    return r


def person(name="rina", roles="Backend Engineer"):
    u = User.objects.create_user(name, email=f"{name}@example.com", password="pw-12345-abc")
    UserProfile.objects.filter(user=u).update(target_roles=roles, profile_cv="Python Django PostgreSQL backend services", onboarding_done=True)
    return u


class AdzunaConnector(TestCase):
    @mock.patch("tracker.services.adzuna.safe_get")
    def test_maps_results_and_keeps_the_redirect_url_unchanged(self, get):
        get.return_value = reply(fixture("adzuna.json"))
        out = adzuna.fetch_adzuna("in", ["python developer"], (APP_ID, KEY))
        first, second = out
        self.assertEqual(first["title"], "Senior Python Developer")  # highlight tags stripped
        self.assertEqual(first["url"], "https://www.adzuna.in/land/ad/1?se=abc&v=def")
        self.assertEqual((first["company"], first["location"]), ("Example Pvt Ltd", "Pune, Maharashtra, India"))
        self.assertEqual(first["salary"], "1,200,000 - 1,800,000")
        self.assertEqual(first["posted"], "2026-10-20")
        self.assertNotIn("<strong>", first["description"])
        self.assertEqual(second["location"], "India")
        self.assertEqual(second["salary"], "900,000 (estimated by Adzuna)")

    @mock.patch("tracker.services.adzuna.safe_get")
    def test_asks_each_role_in_that_country_at_most_three(self, get):
        get.return_value = reply({"results": []})
        adzuna.fetch_adzuna("gb", ["a", "b", "c", "d"], (APP_ID, KEY))
        self.assertEqual(get.call_count, 3)
        url = get.call_args_list[0].args[0]
        self.assertTrue(url.startswith("https://api.adzuna.com/v1/api/jobs/gb/search/1?"))
        self.assertIn("what=a", url)

    @mock.patch("tracker.services.adzuna.safe_get")
    def test_nothing_to_ask_without_keys_or_roles(self, get):
        self.assertEqual(adzuna.fetch_adzuna("gb", ["x"], ("", "")), [])
        self.assertEqual(adzuna.fetch_adzuna("gb", ["x"], (APP_ID, "")), [])
        self.assertEqual(adzuna.fetch_adzuna("gb", [], (APP_ID, KEY)), [])
        get.assert_not_called()

    def test_unknown_country_is_an_error(self):
        with self.assertRaises(FetchError):
            adzuna.fetch_adzuna("zz", ["x"], (APP_ID, KEY))

    @mock.patch("tracker.services.adzuna.safe_get")
    def test_the_key_never_leaks_into_an_error(self, get):
        get.side_effect = FetchError("Request failed: ConnectionError")
        with self.assertRaises(FetchError) as ctx:
            adzuna.fetch_adzuna("gb", ["x"], (APP_ID, KEY))
        self.assertNotIn(KEY, str(ctx.exception))
        get.side_effect = None
        for status in (401, 403, 429, 500):
            get.return_value = reply({}, status)
            with self.assertRaises(FetchError) as ctx:
                adzuna.fetch_adzuna("gb", ["x"], (APP_ID, KEY))
            self.assertNotIn(KEY, str(ctx.exception))
            self.assertNotIn(APP_ID, str(ctx.exception))

    def test_every_documented_country_has_a_home_for_the_credit(self):
        self.assertEqual(len(adzuna.COUNTRIES), 19)
        for code, (name, home) in adzuna.COUNTRIES.items():
            self.assertTrue(home.startswith("https://www.adzuna."), code)
        self.assertEqual(adzuna.attribution("in"), {"label": "Jobs by Adzuna", "url": "https://www.adzuna.in"})
        self.assertEqual(adzuna.attribution("zz")["url"], "https://www.adzuna.co.uk")


class OpenBoardConnectors(TestCase):
    @mock.patch("tracker.services.openboards.safe_get")
    def test_jobtech_sweden(self, get):
        get.return_value = reply(fixture("jobtech.json"))
        out = openboards.fetch_jobtech("se", ["systemutvecklare", "x", "y", "z"])
        self.assertEqual(get.call_count, 3)
        self.assertIn("jobsearch.api.jobtechdev.se/search?q=systemutvecklare&limit=100", get.call_args_list[0].args[0])
        self.assertEqual(len(out), 1)  # the same ad from every role is one job
        job = out[0]
        self.assertEqual((job["title"], job["company"]), ("Systemutvecklare", "Exempelmyndigheten"))
        self.assertEqual(job["location"], "Östersund, Sweden")
        self.assertEqual(job["url"], "https://example.org/platsbanken/annonser/1")
        self.assertEqual(job["posted"], "2026-10-20")

    @mock.patch("tracker.services.openboards.safe_get")
    def test_get_on_board(self, get):
        get.return_value = reply(fixture("getonbrd.json"))
        out = openboards.fetch_getonbrd("latam", ["developer"])
        self.assertEqual([j["title"] for j in out], ["Backend Developer", "Data Engineer"])
        self.assertEqual(out[0]["location"], "Chile")
        self.assertEqual(out[1]["location"], "Remote")
        self.assertEqual(out[0]["company"], "Ejemplo SpA")
        self.assertEqual(out[0]["salary"], "3,000 - 4,500 USD/month")
        self.assertEqual(out[0]["posted"], "2026-10-24")
        self.assertIn("expand=", get.call_args.args[0])

    @mock.patch("tracker.services.openboards.safe_get")
    def test_no_roles_means_no_request_and_bad_answers_are_errors(self, get):
        self.assertEqual(openboards.fetch_jobtech("se", []), [])
        self.assertEqual(openboards.fetch_getonbrd("latam", None), [])
        get.assert_not_called()
        with self.assertRaises(FetchError):
            openboards.fetch_jobtech("xx", ["a"])
        with self.assertRaises(FetchError):
            openboards.fetch_getonbrd("xx", ["a"])
        get.return_value = reply({}, 503)
        with self.assertRaises(FetchError):
            openboards.fetch_jobtech("se", ["a"])


class SeedLists(TestCase):
    def test_every_seeded_source_has_a_connector_and_a_valid_token(self):
        valid = {value for value, _ in JobSource.CONNECTORS}
        for name, connector, token in seed_sources.DEFAULT_SOURCES:
            self.assertIn(connector, valid, name)
            self.assertTrue(callable(getattr(scan, f"fetch_{connector}", None)), f"no fetch_{connector} for {name}")
            self.assertRegex(token, r"^[A-Za-z0-9._-]+$")
        pairs = [(c, t) for _, c, t in seed_sources.DEFAULT_SOURCES]
        self.assertEqual(len(pairs), len(set(pairs)))

    def test_new_connectors_are_never_public(self):
        for connector in seed_sources.SEARCH_CONNECTORS:
            self.assertNotIn(connector, seed_sources.PUBLIC_OK_CONNECTORS)
        self.assertEqual(
            seed_sources.PUBLIC_OK_CONNECTORS, {"greenhouse", "lever", "ashby", "smartrecruiters", "recruitee", "remoteok", "himalayas", "jobicy", "arbeitnow"},
        )

    def test_seed_adds_the_new_sources_and_none_of_them_is_public(self):
        added = ensure_default_sources(JobSource)
        self.assertEqual(added, len(seed_sources.DEFAULT_SOURCES))
        self.assertEqual(JobSource.objects.filter(connector="adzuna").count(), 19)
        self.assertEqual(JobSource.objects.filter(connector__in=seed_sources.SEARCH_CONNECTORS, show_publicly=True).count(), 0)
        self.assertEqual(ensure_default_sources(JobSource), 0)

    def test_regional_boards_and_search_places_are_consistent(self):
        self.assertGreaterEqual(len(seed_sources.REGIONAL_MORE), 50)
        for _, connector, _ in seed_sources.REGIONAL_MORE:
            self.assertIn(connector, JobSource.OWN_CONNECTORS)
        places = {t for _, c, t in seed_sources.JOOBLE + seed_sources.JOOBLE_MORE}
        self.assertEqual(places, set(scan.JOOBLE_PLACES))
        self.assertEqual({t for _, c, t in seed_sources.ADZUNA}, set(adzuna.COUNTRIES))

    def test_migration_seed_adds_once_and_only_to_installs_with_default_sources(self):
        import importlib

        from django.apps import apps

        migration = importlib.import_module("tracker.migrations.0060_more_countries")
        with self.settings(STILLOPEN_SEED_SOURCES=True):
            migration.seed(apps, None)
            self.assertEqual(JobSource.objects.count(), 0)  # an install with no site-wide sources is left to migration 0031
            JobSource.objects.create(name="Mine", connector="greenhouse", board_token="mine")
            migration.seed(apps, None)
            n = JobSource.objects.count()
            self.assertEqual(n, 1 + len(seed_sources.REGIONAL_MORE) + len(seed_sources.JOOBLE_MORE) + 19 + 2)
            migration.seed(apps, None)
            self.assertEqual(JobSource.objects.count(), n)


class KeysAndSkipping(TestCase):
    def setUp(self):
        cache.clear()
        self.u = person()
        self.adz = JobSource.objects.create(name="Adzuna India", connector="adzuna", board_token="in")
        self.jt = JobSource.objects.create(name="JobTech", connector="jobtech", board_token="se")
        self.gob = JobSource.objects.create(name="GoB", connector="getonbrd", board_token="latam")
        self.jo = JobSource.objects.create(name="Jooble Pakistan", connector="jooble", board_token="pk")

    def names(self):
        return set(scan.searchable_sources(self.u).values_list("name", flat=True))

    def test_every_keyed_connector_is_skipped_without_a_key(self):
        self.assertEqual(self.names(), {"JobTech", "GoB"})  # keyless ones still run
        for connector in scan.KEYED_CONNECTORS:
            self.assertFalse(scan.key_ready(connector, scan.site_keys()))

    def test_adzuna_needs_both_id_and_key(self):
        config = SiteConfig.load()
        config.adzuna_app_id = APP_ID
        config.save()
        self.assertNotIn("Adzuna India", self.names())
        config.set_adzuna_app_key(KEY)
        config.save()
        self.assertIn("Adzuna India", self.names())

    def test_environment_keys_win(self):
        with mock.patch.dict("os.environ", {"ADZUNA_APP_ID": "envid", "ADZUNA_APP_KEY": "envkey"}):
            self.assertEqual((SiteConfig.load().effective_adzuna_id, SiteConfig.load().effective_adzuna_key), ("envid", "envkey"))
            self.assertIn("Adzuna India", self.names())

    def test_the_key_is_stored_encrypted_and_never_in_the_form(self):
        config = SiteConfig.load()
        from django.forms.models import model_to_dict

        data = {k: v for k, v in model_to_dict(config).items() if v is not None}
        data["adzuna_app_key"] = KEY
        form = SiteConfigForm(data, instance=config)
        self.assertTrue(form.is_valid(), form.errors.as_json())
        obj = form.save(commit=False)
        obj.save()
        config.refresh_from_db()
        self.assertNotIn(KEY, config.adzuna_app_key_encrypted)
        self.assertEqual(config.effective_adzuna_key, KEY)
        self.assertNotIn(KEY, str(SiteConfigForm(instance=config)["adzuna_app_key"]))

    def test_no_roles_means_no_country_searches(self):
        UserProfile.objects.filter(user=self.u).update(target_roles="")
        self.assertEqual(self.names(), set())

    def test_a_search_only_asks_countries_the_persons_areas_cover(self):
        SiteConfig.objects.filter(pk=1).update(adzuna_app_id=APP_ID, jooble_api_key="k")
        config = SiteConfig.load()
        config.set_adzuna_app_key(KEY)
        config.save()
        SearchArea.objects.create(owner=self.u, place="Pakistan", allow_remote=True)
        self.assertEqual(self.names(), {"Jooble Pakistan"})
        SearchArea.objects.create(owner=self.u, place="Latin America", allow_remote=True)
        self.assertEqual(self.names(), {"Jooble Pakistan", "GoB"})
        SearchArea.objects.create(owner=self.u, place="Anywhere", allow_remote=True)
        self.assertEqual(self.names(), {"Adzuna India", "JobTech", "GoB", "Jooble Pakistan"})

    def test_search_codes(self):
        self.assertEqual(scan.search_codes("adzuna", "in"), {"IN"})
        self.assertEqual(scan.search_codes("jobtech", "se"), {"SE"})
        self.assertIn("BR", scan.search_codes("getonbrd", "latam"))
        self.assertIsNone(scan.search_codes("greenhouse", "x"))


class PublicBoardStaysClean(TestCase):
    def test_a_search_source_never_reaches_the_public_board_even_if_switched_on(self):
        src = JobSource.objects.create(name="Adzuna India", connector="adzuna", board_token="in", show_publicly=True)
        Posting.objects.create(source=src, url="https://www.adzuna.in/land/ad/1", title="Dev", title_key="a :: dev", company="X")
        self.assertEqual(public.public_sources().count(), 0)
        self.assertEqual(public.public_postings().count(), 0)


class AdzunaInASearch(TestCase):
    def setUp(self):
        cache.clear()
        self.u = person()
        self.src = JobSource.objects.create(name="Adzuna India", connector="adzuna", board_token="in")
        SiteConfig.objects.filter(pk=1).update(adzuna_app_id=APP_ID)
        config = SiteConfig.load()
        config.set_adzuna_app_key(KEY)
        config.save()

    def test_results_become_jobs_with_pay_and_a_credit(self):
        jobs = [{"title": "Backend Engineer", "url": "https://www.adzuna.in/land/ad/9?x=1", "location": "Pune, India", "company": "Example Pvt Ltd",
                 "description": "Build APIs with Python and Django.", "salary": "1,200,000 - 1,800,000", "posted": "2026-10-20"}]
        with mock.patch("tracker.services.scan.fetch_adzuna", return_value=jobs) as fetch:
            run = scan.start_run(self.u, background=False)
        self.assertEqual(run.added, 1)
        fetch.assert_called_once()
        self.assertEqual(fetch.call_args.args[0], "in")
        self.assertEqual(fetch.call_args.args[1], ["backend engineer"])
        self.assertEqual(fetch.call_args.args[2], (APP_ID, KEY))
        app = Application.objects.get(owner=self.u)
        self.assertEqual(app.url, "https://www.adzuna.in/land/ad/9?x=1")
        self.assertEqual(app.advertised_pay, "1,200,000 - 1,800,000")
        self.assertEqual(adzuna.credit_for(app.posting), {"label": "Jobs by Adzuna", "url": "https://www.adzuna.in"})

    def test_no_credit_for_other_sources(self):
        other = JobSource.objects.create(name="Acme", connector="greenhouse", board_token="acme")
        posting = Posting.objects.create(source=other, url="https://x.test/1", title="Dev", title_key="acme :: dev")
        self.assertIsNone(adzuna.credit_for(posting))
        self.assertIsNone(adzuna.credit_for(None))


class CheckAdzunaCommand(TestCase):
    def run_cmd(self, *args):
        out = io.StringIO()
        call_command("check_adzuna", *args, stdout=out)
        return out.getvalue()

    def test_needs_keys(self):
        with self.assertRaises(CommandError):
            self.run_cmd()

    def test_reports_success_without_printing_the_key(self):
        SiteConfig.objects.filter(pk=1).update(adzuna_app_id=APP_ID)
        config = SiteConfig.load()
        config.set_adzuna_app_key(KEY)
        config.save()
        jobs = [{"title": "Dev", "company": "Acme", "location": "London, United Kingdom"}]
        with mock.patch("tracker.services.adzuna.fetch_adzuna", return_value=jobs):
            text = self.run_cmd("--country", "gb")
        self.assertIn("Adzuna works", text)
        self.assertIn("Jobs by Adzuna", text)
        self.assertNotIn(KEY, text)
        with self.assertRaises(CommandError):
            self.run_cmd("--country", "zz")
        with mock.patch("tracker.services.adzuna.fetch_adzuna", side_effect=FetchError("Adzuna did not accept the keys.")):
            with self.assertRaises(CommandError):
                self.run_cmd()
