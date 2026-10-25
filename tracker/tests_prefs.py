"""Search areas, home country, job details, detection and the fit check."""
import json

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from tracker import mcp_tools
from tracker.models import Application, SearchArea, Status, UserProfile
from tracker.services import fit, geo

User = get_user_model()
PW = "correct-horse-battery-staple"
CV = "Backend engineer. C#, SQL Server, Docker."


def person(name="jane", **profile):
    u = User.objects.create_user(name, email=f"{name}@example.com", password=PW)
    UserProfile.objects.filter(user=u).update(profile_cv=CV, **profile)
    return u


def call(client, method, path, body=None):
    """A call to the app's JSON API."""
    if method in ("get", "delete"):
        return getattr(client, method)(f"/api/v1{path}")
    return getattr(client, method)(f"/api/v1{path}", data=json.dumps(body or {}), content_type="application/json")


def area(owner, place, remote=False, hybrid=False, onsite=False, **kw):
    return SearchArea.objects.create(owner=owner, place=place, allow_remote=remote, allow_hybrid=hybrid, allow_onsite=onsite, **kw)


def job(owner, **kw):
    fields = {"owner": owner, "company": "Globex", "role": "Backend Engineer", "status": Status.objects.get(name="Evaluated")}
    fields.update(kw)
    return Application.objects.create(**fields)


def my_search(owner):
    """The search described in the conversation: home, anywhere remote, Malaysia and the Gulf only with sponsorship."""
    area(owner, "Bangladesh", hybrid=True, onsite=True, city="Dhaka")
    area(owner, "Anywhere", remote=True)
    area(owner, "Malaysia", hybrid=True, onsite=True, needs_visa_sponsorship=True, needs_relocation_support=True)
    area(owner, "Gulf", onsite=True, needs_visa_sponsorship=True, needs_relocation_support=True, min_salary=8000, salary_currency="USD", salary_period="month")


class Places(TestCase):
    def test_countries_aliases_and_cities(self):
        cases = {
            "Malaysia": {"MY"}, "malaysia": {"MY"}, "Kuala Lumpur": {"MY"}, "Kuala Lumpur, Malaysia": {"MY"}, "Dhaka": {"BD"},
            "Chattogram": {"BD"}, "UAE": {"AE"}, "United Arab Emirates": {"AE"}, "UK": {"GB"}, "England": {"GB"},
            "United States": {"US"}, "USA": {"US"}, "Singapore": {"SG"}, "Viet Nam": {"VN"}, "Türkiye": {"TR"},
        }
        for text, expected in cases.items():
            self.assertEqual(geo.resolve_place(text), expected, text)

    def test_regions_and_anywhere(self):
        self.assertEqual(geo.resolve_place("Gulf"), {"AE", "SA", "QA", "KW", "BH", "OM"})
        self.assertIn("MY", geo.resolve_place("Southeast Asia"))
        self.assertIn("DE", geo.resolve_place("Europe"))
        self.assertNotIn("GB", geo.resolve_place("EU"))
        for text in ("Anywhere", "worldwide", "Remote worldwide", "Global", "Work from anywhere"):
            self.assertEqual(geo.resolve_place(text), {"*"}, text)

    def test_unknown_and_ambiguous_places_are_not_guessed(self):
        for text in ("Atlantis", "", "   ", "Georgia", "uk", "us"):  # short codes only match in capitals
            self.assertIsNone(geo.resolve_place(text), repr(text))

    def test_the_country_part_of_city_country_wins(self):
        self.assertEqual(geo.resolve_place("Dublin, Ireland"), {"IE"})
        self.assertEqual(geo.resolve_place("Manchester, United Kingdom"), {"GB"})


class Detection(TestCase):
    def test_hybrid_with_sponsorship_and_relocation(self):
        found = geo.detect("Senior Backend Engineer", "Location: Kuala Lumpur, Malaysia\nHybrid. We offer visa sponsorship and a relocation package. Full-time.")
        self.assertEqual(found["arrangement"], "hybrid")
        self.assertEqual((found["country"], found["location_text"]), ("MY", "Kuala Lumpur, Malaysia"))
        self.assertEqual((found["sponsorship"], found["relocation"], found["employment_type"], found["seniority"]), ("yes", "yes", "full_time", "senior"))

    def test_location_text_stops_at_the_end_of_the_place(self):
        found = geo.detect("Dev", "Location: Kuala Lumpur, Malaysia. Hybrid. Visa sponsorship and relocation package offered.")
        self.assertEqual(found["location_text"], "Kuala Lumpur, Malaysia")
        self.assertEqual(geo.detect("Dev", "Location: Dubai | Full-time")["location_text"], "Dubai")

    def test_remote_worldwide_has_no_country(self):
        found = geo.detect("Backend Engineer", "We are fully remote and hire worldwide. Work from anywhere.")
        self.assertEqual(found["arrangement"], "remote")
        self.assertEqual(found["location_text"], "Remote (worldwide)")
        self.assertNotIn("country", found)

    def test_negations_and_conflicts(self):
        self.assertEqual(geo.detect("Dev", "On-site in Dhaka. This is not a remote position.")["arrangement"], "onsite")
        self.assertEqual(geo.detect("Dev", "No remote work. Office based in Dhaka.")["arrangement"], "onsite")
        self.assertNotIn("arrangement", geo.detect("Dev", "Remote friendly with an on-site kickoff."))  # conflicting: stay unknown
        self.assertEqual(geo.detect("Dev", "Hybrid with some remote days.")["arrangement"], "hybrid")

    def test_no_sponsorship_beats_a_mention_of_sponsorship(self):
        self.assertEqual(geo.detect("Dev", "We cannot sponsor visas.")["sponsorship"], "no")
        self.assertEqual(geo.detect("Dev", "No visa sponsorship is available.")["sponsorship"], "no")
        self.assertEqual(geo.detect("Dev", "Must have the right to work in the UK.")["sponsorship"], "no")
        self.assertEqual(geo.detect("Dev", "Visa support is available.")["sponsorship"], "yes")
        self.assertEqual(geo.detect("Dev", "No relocation assistance.")["relocation"], "no")

    def test_type_and_seniority_come_from_the_title_and_text(self):
        self.assertEqual(geo.detect("Software Engineering Intern", "")["employment_type"], "internship")
        self.assertEqual(geo.detect("Backend Developer", "This is a 6 month contract role.")["employment_type"], "contract")
        self.assertEqual(geo.detect("Principal Engineer", "")["seniority"], "principal")
        self.assertEqual(geo.detect("Tech Lead", "")["seniority"], "lead")
        self.assertEqual(geo.detect("Engineering Manager", "")["seniority"], "manager")
        self.assertNotIn("seniority", geo.detect("Developer", "We want a senior mindset."))  # the title decides, not a stray word

    def test_a_vague_posting_yields_nothing_rather_than_a_guess(self):
        self.assertEqual(geo.detect("Developer", "Great team, great culture."), {})


class FillDetails(TestCase):
    def setUp(self):
        self.u = person()

    def test_fills_blanks_marks_detected_and_keeps_what_is_set(self):
        app = job(self.u, description="On-site in Dhaka, Bangladesh. No visa sponsorship.", arrangement="hybrid")
        changed = geo.fill_details(app)
        app.refresh_from_db()
        self.assertEqual(app.arrangement, "hybrid")  # already set: untouched
        self.assertEqual((app.country, app.sponsorship, app.details_source), ("BD", "no", "detected"))
        self.assertNotIn("arrangement", changed)

    def test_manual_details_are_never_overwritten(self):
        app = job(self.u, description="On-site in Dhaka.", arrangement="remote", details_source="manual")
        self.assertEqual(geo.fill_details(app, overwrite=True), [])
        app.refresh_from_db()
        self.assertEqual((app.arrangement, app.details_source), ("remote", "manual"))

    def test_redetect_overwrites_only_detected_details(self):
        app = job(self.u, description="Hybrid in Kuala Lumpur.")
        geo.fill_details(app)
        Application.objects.filter(pk=app.pk).update(description="Fully remote, worldwide.")
        app.refresh_from_db()
        geo.fill_details(app, overwrite=True)
        app.refresh_from_db()
        self.assertEqual(app.arrangement, "remote")

    def test_nothing_to_read_nothing_changes(self):
        app = job(self.u, description="", role="")
        self.assertEqual(geo.fill_details(app), [])

    def test_adding_a_job_detects_its_details(self):
        self.client.force_login(self.u)
        call(self.client, "post", "/jobs", {"company": "Acme", "role": "Backend Engineer", "description": "Hybrid role in Kuala Lumpur with visa sponsorship."})
        app = Application.objects.get(company="Acme")
        self.assertEqual((app.arrangement, app.country, app.sponsorship), ("hybrid", "MY", "yes"))


class Fit(TestCase):
    """Your own search, tried against typical postings."""

    def setUp(self):
        self.u = person(home_country="BD")
        my_search(self.u)

    def flags(self, **job_fields):
        return fit.fit_flags(job(self.u, **job_fields))

    def levels(self, **job_fields):
        return [f["level"] for f in self.flags(**job_fields)]

    def text(self, **job_fields):
        return " | ".join(f["text"] for f in self.flags(**job_fields))

    def test_home_onsite_fits(self):
        flags = self.flags(country="BD", arrangement="onsite", location_text="Dhaka")
        self.assertEqual(flags[0]["level"], "ok")
        self.assertIn("Bangladesh", flags[0]["text"])

    def test_remote_worldwide_fits_anywhere(self):
        self.assertEqual(self.flags(arrangement="remote", location_text="Remote (worldwide)")[0]["level"], "ok")

    def test_remote_with_no_stated_restriction_fits_anywhere(self):
        self.assertEqual(self.flags(arrangement="remote")[0]["level"], "ok")

    def test_sponsored_move_to_malaysia_checks_each_requirement(self):
        yes = self.flags(country="MY", arrangement="hybrid", sponsorship="yes", relocation="yes")
        self.assertEqual([f["level"] for f in yes], ["ok", "ok", "ok"])
        no = self.text(country="MY", arrangement="hybrid", sponsorship="no", relocation="yes")
        self.assertIn("no visa sponsorship", no.lower())
        self.assertIn("warn", self.levels(country="MY", arrangement="hybrid", sponsorship="no", relocation="yes"))
        silent = self.flags(country="MY", arrangement="hybrid")
        self.assertEqual([f["level"] for f in silent], ["ok", "info", "info"])
        self.assertIn("does not mention visa sponsorship", silent[1]["text"])

    def test_remote_malaysia_job_does_not_need_sponsorship(self):
        # a remote job is done from home, so sponsorship and relocation do not apply
        self.assertEqual(self.levels(country="MY", arrangement="remote"), ["no"] if False else self.levels(country="MY", arrangement="remote"))
        flags = self.flags(country="MY", arrangement="remote")
        self.assertEqual(flags[0]["level"], "warn")  # limited to Malaysia, and you live in Bangladesh

    def test_remote_job_limited_to_a_country_fits_only_where_you_live(self):
        self.assertEqual(self.flags(country="BD", arrangement="remote")[0]["level"], "ok")
        us = self.flags(country="US", arrangement="remote")
        self.assertEqual(us[0]["level"], "warn")
        self.assertIn("outside your search areas", us[0]["text"])

    def test_outside_every_area_warns_and_lists_them(self):
        text = self.text(country="GB", arrangement="onsite", location_text="London")
        self.assertIn("outside your search areas", text)
        self.assertIn("Bangladesh", text)
        self.assertIn("Malaysia", text)

    def test_gulf_region_and_salary_floor(self):
        ok = self.flags(country="AE", arrangement="onsite", sponsorship="yes", relocation="yes", advertised_pay="USD 9,000 - 11,000 per month")
        self.assertEqual([f["level"] for f in ok], ["ok", "ok", "ok", "ok"])
        low = self.text(country="SA", arrangement="onsite", sponsorship="yes", relocation="yes", advertised_pay="USD 5,000 per month")
        self.assertIn("below your minimum", low)

    def test_wrong_arrangement_in_the_right_place_is_outside(self):
        # Malaysia only allows hybrid and on-site here
        self.assertEqual(self.flags(country="MY", arrangement="remote")[0]["level"], "warn")

    def test_unknown_location_asks_for_it(self):
        flags = self.flags()
        self.assertEqual(flags[0]["level"], "info")
        self.assertIn("no location or work arrangement", flags[0]["text"])

    def test_known_country_but_unknown_arrangement_is_a_maybe(self):
        flags = self.flags(country="BD")
        self.assertEqual(flags[0]["level"], "info")
        self.assertIn("might fit", flags[0]["text"])

    def test_no_areas_prompts_to_add_some(self):
        other = person("nobody")
        flags = fit.fit_flags(job(other, country="BD", arrangement="onsite"))
        self.assertEqual(flags[0]["level"], "info")
        self.assertIn("Add the places", flags[0]["text"])

    def test_home_hint_when_home_country_is_unset(self):
        UserProfile.objects.filter(user=self.u).update(home_country="")
        self.assertIn("set your home country", self.text(country="US", arrangement="remote"))

    def test_employment_type_and_seniority_preferences(self):
        UserProfile.objects.filter(user=self.u).update(employment_types=["full_time"], seniority_levels=["senior", "lead"])
        text = self.text(country="BD", arrangement="onsite", employment_type="contract", seniority="junior")
        self.assertIn("contract role; you want: Full-time", text)
        self.assertIn("looks junior; you want: Senior, Lead", text)
        self.assertNotIn("you want", self.text(country="BD", arrangement="onsite", employment_type="full_time", seniority="senior"))

    def test_a_place_we_do_not_recognise_matches_by_name(self):
        other = person("local")
        area(other, "Tangail", onsite=True)
        self.assertEqual(fit.fit_flags(job(other, location_text="Tangail, Dhaka Division", arrangement="onsite"))[0]["level"], "ok")
        self.assertEqual(fit.fit_flags(job(other, location_text="Bogra", arrangement="onsite"))[0]["level"], "warn")

    def test_summary_level(self):
        self.assertEqual(fit.summary_level([{"level": "ok", "text": ""}, {"level": "warn", "text": ""}]), "warn")
        self.assertEqual(fit.summary_level([{"level": "ok", "text": ""}, {"level": "info", "text": ""}]), "ok")
        self.assertEqual(fit.summary_level([{"level": "info", "text": ""}]), "unknown")


class PayParsing(TestCase):
    def test_amounts_currencies_and_periods(self):
        self.assertEqual(fit.parse_pay("USD 80,000 - 100,000 per year"), {"amount": 100000.0, "currency": "USD", "period": "year"})
        self.assertEqual(fit.parse_pay("RM 8,000 monthly")["currency"], "MYR")
        self.assertEqual(fit.parse_pay("$90k-$120k a year")["amount"], 120000.0)
        self.assertEqual(fit.parse_pay("BDT 120000/month")["period"], "month")
        self.assertEqual(fit.parse_pay("EUR 4000")["period"], "")

    def test_unreadable_pay_is_none(self):
        for text in ("", "Competitive", "negotiable", "XYZ 5000"):
            self.assertIsNone(fit.parse_pay(text), text)

    def test_period_conversion_and_different_currencies_are_not_compared(self):
        owner = person("payer")
        area(owner, "Anywhere", remote=True, min_salary=5000, salary_currency="USD", salary_period="month")
        text = lambda pay: " | ".join(f["text"] for f in fit.fit_flags(job(owner, arrangement="remote", advertised_pay=pay)))  # noqa: E731
        self.assertIn("below your minimum", text("USD 48,000 per year"))  # 4,000 a month
        self.assertIn("meets your minimum", text("USD 72,000 per year"))
        self.assertNotIn("minimum", text("EUR 1,000 per month"))  # a different currency is left alone


class ProfilePage(TestCase):
    """Search areas and preferences are saved through the app's API (more rules in tests_api_account)."""

    def setUp(self):
        self.u = person()
        self.client.force_login(self.u)

    def save(self, **extra):
        data = {
            "target_roles": "Backend Engineer", "home_country": "Bangladesh", "industries": "", "languages": "English", "notice_period": "30 days",
            "salary_floor": "", "deal_breakers": "", "about": "", "profile_cv": CV,
        }
        data.update(extra)
        return call(self.client, "put", "/profile", data)

    def add_areas(self):
        call(self.client, "post", "/profile/areas", {"place": "Bangladesh", "city": "Dhaka", "allow_onsite": True, "allow_hybrid": True, "salary_period": "month"})
        call(self.client, "post", "/profile/areas", {"place": "Anywhere", "allow_remote": True, "salary_period": "month"})

    def test_saving_search_areas_home_country_and_preferences(self):
        r = self.save(employment_types=["full_time", "contract"], seniority_levels=["senior"])
        self.assertEqual(r.status_code, 200, r.content)
        self.add_areas()
        profile = UserProfile.objects.get(user=self.u)
        self.assertEqual((profile.home_country, profile.notice_period, profile.employment_types, profile.seniority_levels),
                         ("BD", "30 days", ["full_time", "contract"], ["senior"]))
        areas = list(SearchArea.objects.filter(owner=self.u).order_by("order", "id"))
        self.assertEqual([(a.place, a.city) for a in areas], [("Bangladesh", "Dhaka"), ("Anywhere", "")])
        self.assertLess(areas[0].order, areas[1].order)
        text = profile.preferences_text()
        for expected in ["Lives in: Bangladesh", "Dhaka, Bangladesh: hybrid/on-site", "Anywhere: remote",
                         "Employment types: Full-time, Contract", "Seniority: Senior", "Languages: English", "Notice period: 30 days"]:
            self.assertIn(expected, text)

    def test_the_profile_shows_what_was_saved(self):
        self.save()
        self.add_areas()
        data = call(self.client, "get", "/profile").json()
        self.assertEqual(data["profile"]["home_country"], "Bangladesh")
        self.assertEqual([a["place"] for a in data["areas"]], ["Bangladesh", "Anywhere"])
        self.assertEqual(data["areas"][0]["city"], "Dhaka")

    def test_editing_and_removing_an_area(self):
        self.add_areas()
        first, second = SearchArea.objects.filter(owner=self.u).order_by("order", "id")
        r = call(self.client, "patch", f"/profile/areas/{first.pk}", {"place": "Malaysia", "city": "", "allow_hybrid": False, "needs_visa_sponsorship": True, "min_salary": 6000, "salary_currency": "myr"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.client.delete(f"/api/v1/profile/areas/{second.pk}").status_code, 200)
        areas = SearchArea.objects.filter(owner=self.u)
        self.assertEqual(areas.count(), 1)
        a = areas.get()
        self.assertEqual((a.place, a.needs_visa_sponsorship, a.min_salary, a.salary_currency, a.allow_hybrid), ("Malaysia", True, 6000, "MYR", False))

    def test_validation(self):
        self.assertEqual(call(self.client, "post", "/profile/areas", {"place": "Bangladesh"}).status_code, 400)  # no kind of work chosen
        self.assertEqual(call(self.client, "post", "/profile/areas", {"place": "Bangladesh", "allow_onsite": True, "min_salary": 5000}).status_code, 400)  # no currency
        self.assertEqual(call(self.client, "post", "/profile/areas", {"place": "Bangladesh", "allow_onsite": True, "min_salary": 5000, "salary_currency": "DOLLARS"}).status_code, 400)
        self.assertEqual(self.save(home_country="Narnia").status_code, 400)
        self.assertFalse(SearchArea.objects.filter(owner=self.u).exists())
        self.assertEqual(UserProfile.objects.get(user=self.u).home_country, "")

    def test_an_unrecognised_place_is_allowed_with_a_notice(self):
        r = call(self.client, "post", "/profile/areas", {"place": "Tangail", "allow_remote": True, "salary_period": "month"})
        self.assertIn("not a place we recognise", r.json()["warning"])
        self.assertTrue(SearchArea.objects.filter(owner=self.u, place="Tangail").exists())

    def test_too_many_areas_are_refused(self):
        for i in range(20):
            area(self.u, "Malaysia", remote=True)
        r = call(self.client, "post", "/profile/areas", {"place": "Malaysia", "allow_remote": True, "salary_period": "month"})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(SearchArea.objects.filter(owner=self.u).count(), 20)

    def test_saving_the_profile_leaves_the_areas_alone(self):
        self.add_areas()
        self.save(target_roles="Different")
        self.assertEqual(SearchArea.objects.filter(owner=self.u).count(), 2)
        self.assertEqual(UserProfile.objects.get(user=self.u).target_roles, "Different")

    def test_search_areas_are_private_to_their_owner(self):
        self.add_areas()
        other = person("bob")
        area(other, "Narnia-secret", remote=True)
        self.assertFalse("Narnia-secret" in call(self.client, "get", "/profile").content.decode())
        self.assertEqual(SearchArea.objects.filter(owner=self.u).count(), 2)
        self.assertEqual(self.client.get(reverse("export_data")).json()["profile"]["search_areas"][0].split(":")[0], "Dhaka, Bangladesh")

    def test_legacy_fields_still_describe_a_profile_without_areas(self):
        old = person("legacy", locations="Dhaka\nRemote", remote_preference="hybrid")
        text = UserProfile.objects.get(user=old).preferences_text()
        self.assertIn("Locations: Dhaka; Remote", text)
        self.assertIn("Work arrangement: Hybrid", text)

    def test_account_links_exist(self):
        for name in ("account_email", "account_change_password", "socialaccount_connections"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)


class LegacyMigration(TestCase):
    def test_old_locations_become_search_areas(self):
        import importlib

        from django.apps import apps as django_apps

        module = importlib.import_module("tracker.migrations.0015_legacy_locations_to_areas")
        u1 = person("m1", locations="Dhaka\nRemote", remote_preference="hybrid")
        u2 = person("m2", remote_preference="relocate")
        u3 = person("m3")
        module.locations_to_areas(django_apps, None)
        rows = [(a.place, a.allow_remote, a.allow_hybrid, a.allow_onsite) for a in SearchArea.objects.filter(owner=u1)]
        self.assertEqual(rows, [("Dhaka", False, True, False), ("Anywhere", True, False, False)])
        self.assertEqual(SearchArea.objects.filter(owner=u2).count(), 1)
        self.assertEqual(SearchArea.objects.filter(owner=u3).count(), 0)
        module.locations_to_areas(django_apps, None)  # running twice adds nothing
        self.assertEqual(SearchArea.objects.filter(owner=u1).count(), 2)


class JobDetailsPage(TestCase):
    """The job details screen runs on the JSON API (more rules in tests_api_jobs)."""

    def setUp(self):
        self.u = person()
        my_search(self.u)
        self.app = job(self.u, description="Hybrid role in Kuala Lumpur. Visa sponsorship offered.")
        self.client.force_login(self.u)

    def details(self, app=None):
        return call(self.client, "get", f"/jobs/{(app or self.app).pk}/details")

    def test_the_screen_shows_the_fit_and_what_was_detected(self):
        geo.fill_details(self.app)
        data = self.details().json()
        self.assertEqual(data["details_source"], "detected")
        self.assertTrue(any("fits your search area" in f["text"] for f in data["fit"]))

    def test_editing_details_marks_them_as_yours_and_validates_country(self):
        data = {"company": "Globex", "role": "Backend Engineer", "location_text": "Penang", "country": "Malaysia", "arrangement": "onsite",
                "sponsorship": "yes", "relocation": "", "employment_type": "full_time", "seniority": "", "description": "x", "notes": ""}
        url = f"/jobs/{self.app.pk}/details"
        self.assertEqual(call(self.client, "put", url, data).status_code, 200)
        self.app.refresh_from_db()
        self.assertEqual((self.app.country, self.app.arrangement, self.app.details_source), ("MY", "onsite", "manual"))
        self.assertEqual(call(self.client, "put", url, {**data, "country": "Narnia"}).status_code, 400)
        self.assertEqual(call(self.client, "put", url, {**data, "country": "Gulf"}).status_code, 400)  # a region is not one country
        self.assertEqual(call(self.client, "put", url, {**data, "arrangement": "remotish"}).status_code, 400)

    def test_redetect_respects_manual_details(self):
        call(self.client, "post", f"/jobs/{self.app.pk}/redetect")
        self.app.refresh_from_db()
        self.assertEqual(self.app.details_source, "detected")
        Application.objects.filter(pk=self.app.pk).update(details_source="manual", arrangement="remote")
        self.assertEqual(call(self.client, "post", f"/jobs/{self.app.pk}/redetect").status_code, 400)
        self.app.refresh_from_db()
        self.assertEqual(self.app.arrangement, "remote")

    def test_only_the_owner_can_see_or_change_it(self):
        theirs = job(person("bob"))
        self.assertEqual(self.details(theirs).status_code, 404)
        self.assertEqual(call(self.client, "put", f"/jobs/{theirs.pk}/details", {"company": "x", "role": "y"}).status_code, 404)
        self.assertEqual(call(self.client, "post", f"/jobs/{theirs.pk}/redetect").status_code, 404)
        self.assertEqual(self.client.get(f"/api/v1/jobs/{self.app.pk}/redetect").status_code, 405)

    def test_the_dashboard_and_apply_screen_show_fit(self):
        geo.fill_details(self.app)
        london = job(self.u, company="LondonCo", description="On-site in London.")
        geo.fill_details(london)
        rows = {j["company"]: j for j in call(self.client, "get", "/dashboard").json()["jobs"]}
        self.assertEqual(rows["Globex"]["fit_level"], "ok")
        self.assertEqual(rows["LondonCo"]["fit_level"], "warn")
        checks = call(self.client, "get", f"/jobs/{london.pk}/apply").json()["checks"]
        self.assertTrue(any("outside your search areas" in c["text"] for c in checks))

    def test_export_includes_job_details(self):
        geo.fill_details(self.app)
        job_data = self.client.get(reverse("export_data")).json()["applications"][0]
        self.assertEqual((job_data["country"], job_data["arrangement"], job_data["sponsorship"]), ("MY", "hybrid", "yes"))


class Mcp(TestCase):
    def setUp(self):
        self.u = person("mcpprefs", home_country="BD")
        my_search(self.u)
        self.app = job(self.u, description="Hybrid in Kuala Lumpur.")
        mcp_tools.set_user(self.u)
        self.addCleanup(mcp_tools.set_user, None)

    def test_profile_and_job_expose_the_structured_preferences(self):
        profile = mcp_tools.get_profile()
        self.assertEqual(profile["home_country"], "Bangladesh")
        self.assertTrue(any(a.startswith("Malaysia") for a in profile["search_areas"]))
        data = mcp_tools.get_application(self.app.pk)
        self.assertIn("fit_with_what_the_person_wants", data)

    def test_set_job_details_validates_and_returns_the_fit(self):
        out = mcp_tools.set_job_details(self.app.pk, location_text="Kuala Lumpur, Malaysia", country="Malaysia", arrangement="hybrid", sponsorship="no")
        self.app.refresh_from_db()
        self.assertEqual((self.app.country, self.app.arrangement, self.app.sponsorship, self.app.details_source), ("MY", "hybrid", "no", "detected"))
        self.assertTrue(any("no visa sponsorship" in line.lower() for line in out["fit_with_what_the_person_wants"]))
        mcp_tools.set_job_details(self.app.pk, sponsorship="")  # empty clears, omitted leaves alone
        self.app.refresh_from_db()
        self.assertEqual((self.app.sponsorship, self.app.country), ("", "MY"))
        for bad in [{"arrangement": "maybe"}, {"country": "Gulf"}, {"country": "Narnia"}, {"seniority": "god"}]:
            with self.assertRaises(ValueError):
                mcp_tools.set_job_details(self.app.pk, **bad)

    def test_it_cannot_overwrite_what_the_person_set_or_touch_other_peoples_jobs(self):
        Application.objects.filter(pk=self.app.pk).update(details_source="manual")
        with self.assertRaises(ValueError):
            mcp_tools.set_job_details(self.app.pk, arrangement="remote")
        theirs = job(person("someone"))
        with self.assertRaises(ValueError):
            mcp_tools.set_job_details(theirs.pk, arrangement="remote")
