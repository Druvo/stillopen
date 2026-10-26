"""Test runner that keeps PostgreSQL's end-of-run clean-up from failing on a stray connection.

A test that starts a background worker (a search, a streamed download) can leave that thread's own database connection open when
the suite ends. SQLite does not care; PostgreSQL refuses to drop the test database while another session is on it
("is being accessed by other users"), which fails an otherwise green run. Before the databases are dropped, any other session
still on a test database is ended.
"""
from django.test.runner import DiscoverRunner


class StrayConnectionSafeRunner(DiscoverRunner):
    def teardown_databases(self, old_config, **kwargs):
        for connection, _old_name, _destroy in old_config:
            if connection.vendor != "postgresql":
                continue
            name = connection.settings_dict["NAME"]
            try:
                connection.close()
                with connection._nodb_cursor() as cursor:
                    cursor.execute(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s AND pid <> pg_backend_pid()", [name]
                    )
            except Exception:  # noqa: BLE001 - best effort; the normal clean-up below reports a real problem
                pass
        super().teardown_databases(old_config, **kwargs)
