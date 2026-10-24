"""Copy an existing SQLite install into PostgreSQL.

    DATABASE_URL=postgres://... python manage.py copy_to_postgres --from db.sqlite3

Run it once, after pointing DATABASE_URL at an empty PostgreSQL database. It creates the tables, then loads everything from the
SQLite file (people, jobs, CVs, postings, settings) and checks the row counts match. The SQLite file is only read, never changed.
Sessions are not copied: everyone signs in again. Keep the same secret key, or stored API keys cannot be decrypted.
"""
import tempfile
from pathlib import Path

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, connections

SOURCE = "sqlite_source"
SKIP = ["contenttypes", "auth.permission", "sessions", "admin.logentry"]


class Command(BaseCommand):
    help = "Copy an existing SQLite database into the PostgreSQL database named by DATABASE_URL."

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="source", required=True, help="Path of the SQLite file, e.g. db.sqlite3.")
        parser.add_argument("--replace", action="store_true", help="The PostgreSQL database already has data (e.g. a first sign-up): erase it first.")

    def handle(self, *args, source, replace, **options):
        if connection.vendor != "postgresql":
            raise CommandError("DATABASE_URL must point at PostgreSQL (postgres://user:password@host:5432/name) before you run this.")
        path = Path(source)
        if not path.is_file():
            raise CommandError(f"No such file: {path}")
        connections.databases[SOURCE] = {
            "ENGINE": "django.db.backends.sqlite3", "NAME": str(path.resolve()), "ATOMIC_REQUESTS": False, "AUTOCOMMIT": True,
            "CONN_MAX_AGE": 0, "CONN_HEALTH_CHECKS": False, "OPTIONS": {}, "TIME_ZONE": None, "USER": "", "PASSWORD": "", "HOST": "", "PORT": "",
            "TEST": {},
        }
        call_command("migrate", "--noinput", verbosity=0)
        from django.contrib.auth import get_user_model

        if get_user_model().objects.exists() and not replace:
            raise CommandError("The PostgreSQL database already has accounts. Use an empty database, or add --replace to erase it and copy over.")
        with tempfile.TemporaryDirectory() as tmp:
            dump = Path(tmp) / "dump.json"
            self.stdout.write("Reading the SQLite file...")
            with dump.open("w", encoding="utf-8") as out:  # explicit UTF-8: the platform default (Windows cp1252) cannot hold every name
                call_command("dumpdata", database=SOURCE, natural_foreign=True, natural_primary=True, exclude=SKIP, stdout=out, verbosity=0)
            self.stdout.write("Writing to PostgreSQL...")
            call_command("flush", "--noinput", verbosity=0)
            call_command("loaddata", str(dump), verbosity=0)
        bad = []
        for model in apps.get_models():
            label = model._meta.label_lower
            if label in SKIP or model._meta.app_label in SKIP or model._meta.proxy or not model._meta.managed:
                continue
            old = model._default_manager.using(SOURCE).count()
            new = model._default_manager.count()
            if old != new:
                bad.append(f"{model._meta.label}: {old} in SQLite, {new} in PostgreSQL")
        if bad:
            raise CommandError("Row counts differ:\n  " + "\n  ".join(bad))
        self.stdout.write(self.style.SUCCESS("Copied. Every table has the same number of rows. Start the app on PostgreSQL."))
