"""CV builder publications/references, the extra ATS-safe looks, and the whole-account export/import round trip."""
import io
import json
import zipfile

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from docx import Document as DocxDocument

from tracker.models import Application, CoverLetter, CVVersion, Status, UserProfile
from tracker.services import ats, cvbuilder, cvexport, dataexport, dataimport
from tracker.services.cvversions import CVError

User = get_user_model()
BASE = {"name": "Ada Lovelace", "email": "ada@example.com", "roles": [{"title": "Engineer", "company": "Acme", "start": "Jan 2020", "bullets": ["Built things"]}]}


class Publications(TestCase):
    def test_plain_and_apa_lines_without_emphasis(self):
        pubs = [{"title": "**Bold** *idea*", "venue": "Journal", "year": "2022", "link": "example.org/p"}]
        plain = cvbuilder.to_markdown(cvbuilder.clean_answers({**BASE, "publications": pubs}))
        self.assertIn("## Publications\nBold idea - Journal, 2022 - example.org/p", plain)
        apa = cvbuilder.to_markdown(cvbuilder.clean_answers({**BASE, "publications": pubs, "citation_style": "apa"}))
        self.assertIn("(2022). Bold idea. Journal. example.org/p", apa)
        self.assertNotIn("*", plain.split("## Publications")[1])

    def test_bad_year_style_and_caps(self):
        with self.assertRaises(CVError):
            cvbuilder.clean_answers({**BASE, "publications": [{"title": "T", "year": "last year"}]})
        a = cvbuilder.clean_answers({**BASE, "citation_style": "<script>", "publications": [{"title": f"T{i}"} for i in range(20)]})
        self.assertEqual(a["citation_style"], "plain")
        self.assertEqual(len(a["publications"]), cvbuilder.MAX_PUBLICATIONS)

    def test_injected_headings_are_flattened(self):
        a = cvbuilder.clean_answers({**BASE, "publications": [{"title": "# Skills | a | b |", "venue": "## X"}]})
        md = cvbuilder.to_markdown(a)
        self.assertEqual(md.count("\n## Publications"), 1)
        self.assertNotIn("\n#", md.split("## Publications")[1])


class References(TestCase):
    def test_default_is_off(self):
        self.assertNotIn("References", cvbuilder.to_markdown(cvbuilder.clean_answers(BASE)))

    def test_on_request_line_and_listed(self):
        md = cvbuilder.to_markdown(cvbuilder.clean_answers({**BASE, "references_mode": "on_request"}))
        self.assertIn("## References\nReferences available on request.", md)
        listed = cvbuilder.clean_answers({**BASE, "references_mode": "listed", "references": [{"name": "Bo Chan", "role": "Manager, Acme", "contact": "bo@example.com"}] * 5})
        self.assertEqual(len(listed["references"]), cvbuilder.MAX_REFERENCES)
        self.assertIn("Bo Chan - Manager, Acme - bo@example.com", cvbuilder.to_markdown(listed))

    def test_listed_without_anyone_falls_back_and_name_required(self):
        self.assertEqual(cvbuilder.clean_answers({**BASE, "references_mode": "listed"})["references_mode"], "on_request")
        with self.assertRaises(CVError):
            cvbuilder.clean_answers({**BASE, "references_mode": "listed", "references": [{"role": "Boss"}]})

    def test_ats_still_recognises_sections(self):
        md = cvbuilder.to_markdown(cvbuilder.clean_answers({**BASE, "publications": [{"title": "T", "year": "2021"}], "references_mode": "on_request"}))
        report = ats.check_text(md)
        self.assertNotIn("creative names", " ".join(c["title"] for c in report["checks"]))


class Looks(TestCase):
    MD = "# Ada\n\nada@example.com\n\n## Work experience\n\n**Engineer** - Acme, Jan 2020 - Present\n- Built things\n\n## Skills\nTools: Python\n"

    def test_every_look_is_plain(self):
        self.assertGreaterEqual(len(cvexport.TEMPLATES), 6)
        html = cvexport.to_html(self.MD)
        for tag in ("<table", "<img", "<svg", "<col"):
            self.assertNotIn(tag, html)
        for name in cvexport.TEMPLATES:
            data = cvexport.to_docx(self.MD, name)
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                xml = z.read("word/document.xml").decode()
                for marker in ("<w:tbl", "<w:drawing", "<w:pict", "w:num="):
                    self.assertNotIn(marker, xml, name)
                self.assertFalse([n for n in z.namelist() if n.startswith("word/media")], name)
            text = " ".join(p.text for p in DocxDocument(io.BytesIO(data)).paragraphs)
            for word in ("Ada", "Engineer", "Acme", "Built things", "Python"):
                self.assertIn(word, text, name)

    def test_print_page_for_each_look(self):
        user = User.objects.create_user("look", password="x" * 20)
        v = CVVersion.objects.create(owner=user, kind="master", content=self.MD, approved=True)
        self.client.force_login(user)
        for name in cvexport.TEMPLATES:
            body = self.client.get(reverse("cv_print", args=[v.pk]) + f"?template={name}").content.decode()
            self.assertIn("Built things", body)
            self.assertNotIn("<table", body)

    def test_default_unchanged_and_tokens_in_whitelist(self):
        self.assertEqual(cvexport.DEFAULT_TEMPLATE, "classic")
        for style in cvexport.TEMPLATES.values():
            self.assertRegex(style["accent"], r"^[0-9A-F]{6}$")
            self.assertEqual(set(style) - {"label", "font", "heading_font", "accent", "body_pt", "print_pt", "line_height", "upper_h2"}, set())


def make_user(name):
    return User.objects.create_user(name, email=f"{name}@example.com", password="x" * 20)


def job(owner, company="Acme", role="Dev", **kw):
    return Application.objects.create(owner=owner, company=company, role=role, status=Status.objects.get(name="Evaluated"), **kw)


class RoundTrip(TestCase):
    def setUp(self):
        self.a, self.b = make_user("rt-a"), make_user("rt-b")
        p = UserProfile.for_user(self.a)
        p.target_roles, p.about, p.home_country, p.profile_cv = "Engineer", "Likes cats", "MY", "# Ada\nOld"
        p.save()
        CVVersion.objects.create(owner=self.a, kind="master", content="# Ada\nOld", label="First")
        CVVersion.objects.create(owner=self.a, kind="master", content="# Ada\nNew", label="Second")
        ja = job(self.a, notes="my note")
        CoverLetter.objects.create(owner=self.a, application=ja, content="Dear team, I like Acme.")
        self.file = json.dumps(dataexport.build(self.a)).encode()

    def wipe(self):
        CVVersion.objects.filter(owner=self.a).delete()
        CoverLetter.objects.filter(owner=self.a).delete()
        Application.objects.filter(owner=self.a).update(notes="")
        UserProfile.objects.filter(user=self.a).update(target_roles="", about="", home_country="")

    def test_export_has_format_and_profile_fields(self):
        data = json.loads(self.file)
        self.assertEqual(data["format"], "stillopen-export")
        self.assertEqual(data["profile"]["home_country"], "MY")
        self.assertNotIn("password", self.file.decode().lower())

    def test_preview_writes_nothing_then_import_restores(self):
        self.wipe()
        r = dataimport.read(self.a, self.file, preview=True)
        self.assertEqual((r["cvs"]["add"], r["covers"]["add"], r["notes"]["add"]), (2, 1, 1))
        self.assertFalse(CVVersion.objects.filter(owner=self.a).exists())
        dataimport.read(self.a, self.file, preview=False)
        self.assertEqual(CVVersion.objects.filter(owner=self.a).count(), 2)
        self.assertEqual(UserProfile.for_user(self.a).target_roles, "Engineer")
        self.assertEqual(Application.objects.get(owner=self.a).notes, "my note")
        self.assertFalse(CoverLetter.objects.get(owner=self.a).approved)
        self.assertIn("New", CVVersion.objects.filter(owner=self.a, kind="master").first().content)

    def test_second_import_is_a_no_op_and_nothing_is_overwritten(self):
        self.assertTrue(dataimport.read(self.a, self.file, preview=False)["nothing"])
        UserProfile.objects.filter(user=self.a).update(about="Changed since")
        Application.objects.filter(owner=self.a).update(notes="newer note")
        r = dataimport.read(self.a, self.file, preview=False)
        self.assertIn("about you", r["profile"]["kept"])
        self.assertEqual(r["notes"]["kept"], 1)
        self.assertEqual(UserProfile.for_user(self.a).about, "Changed since")
        self.assertEqual(Application.objects.get(owner=self.a).notes, "newer note")

    def test_other_accounts_file_is_refused(self):
        with self.assertRaises(dataimport.ImportProblem):
            dataimport.read(self.b, self.file)

    def test_hostile_files(self):
        for raw in (b"not json", b"[]", b'{"format":"other"}', b'{"format":"stillopen-export","format_version":99,"account":{"username":"rt-a"}}',
                    b"[" * 100000, b"\xff\xfe", b"x" * (dataimport.MAX_BYTES + 1)):
            with self.assertRaises(dataimport.ImportProblem):
                dataimport.read(self.a, raw)
        evil = {"format": "stillopen-export", "format_version": 1, "account": {"username": "rt-a"},
                "profile": {"timezone": "../../etc/passwd", "home_country": "XYZ", "employment_types": "full", "target_roles": 5, "about": {"x": 1}},
                "cv_versions": ["x", {"kind": "master", "content": 7}, {"kind": "master", "content": "   "}],
                "cover_letters": [None, {"for_job": ["a"], "content": "x"}], "applications": "nope"}
        self.wipe()
        dataimport.read(self.a, json.dumps(evil).encode(), preview=False)
        self.assertEqual(UserProfile.for_user(self.a).home_country, "")

    def test_never_touches_another_persons_data(self):
        jb = job(self.b, notes="")
        self.wipe()
        dataimport.read(self.a, self.file, preview=False)
        self.assertEqual(Application.objects.get(pk=jb.pk).notes, "")
        self.assertFalse(CoverLetter.objects.filter(owner=self.b).exists())
        self.assertFalse(CVVersion.objects.filter(owner=self.b).exists())

    def test_api(self):
        self.assertEqual(self.client.post("/api/v1/account/import").status_code, 401)
        self.client.force_login(self.a)
        self.assertEqual(self.client.post("/api/v1/account/import").status_code, 400)
        r = self.client.post("/api/v1/account/import?preview=1", {"file": SimpleUploadedFile("e.json", self.file)})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["preview"])
        self.client.force_login(self.b)
        r = self.client.post("/api/v1/account/import", {"file": SimpleUploadedFile("e.json", self.file)})
        self.assertEqual(r.status_code, 400)
