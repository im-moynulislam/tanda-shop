"""
Smoke tests for the whole project. They do not depend on your model or view
names, so they can run before anything else is written.

Copy this file into your  config/  folder, then run:

    python manage.py test config.test_smoke -v 2

Django builds a separate empty test database, so db.sqlite3 is never touched.
"""
import os
import unittest
from io import StringIO
from pathlib import Path

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.template.loader import get_template
from django.test import SimpleTestCase, TestCase
from django.urls import URLResolver, get_resolver, reverse
from django.urls.resolvers import RoutePattern

from config.admin import admin_site  # the custom admin used in config/urls.py


def public_routes():
    """Every URL that needs no arguments, such as '' or 'cart/'."""
    routes = set()

    def walk(patterns, prefix):
        for p in patterns:
            if not isinstance(p.pattern, RoutePattern):
                continue
            route = prefix + str(p.pattern)
            if isinstance(p, URLResolver):
                walk(p.url_patterns, route)
            elif "<" not in route:
                routes.add(route)

    walk(get_resolver().url_patterns, "")
    return sorted(r for r in routes if not r.startswith(("admin/", "static/", "media/")))


def project_template_names():
    """Template names from your own apps and TEMPLATES DIRS (not Django's)."""
    base = Path(settings.BASE_DIR).resolve()
    roots = [Path(c.path) / "templates" for c in apps.get_app_configs()]
    for cfg in settings.TEMPLATES:
        roots += [Path(d) for d in cfg.get("DIRS", [])]
    names = set()
    for root in roots:
        root = root.resolve()
        if not root.is_dir() or base not in root.parents or ".venv" in root.parts:
            continue
        for f in root.rglob("*.html"):
            names.add(f.relative_to(root).as_posix())
    return sorted(names)


def make_user(username, staff=False):
    User = get_user_model()
    user = User(**{User.USERNAME_FIELD: username, "is_staff": staff, "is_superuser": staff})
    user.set_password("Test-pass-12345")
    user.save()
    return user


class ProjectHealthTest(TestCase):
    def test_django_system_check_passes(self):
        call_command("check", stdout=StringIO())

    def test_no_missing_migrations(self):
        out = StringIO()
        try:
            call_command("makemigrations", "--check", "--dry-run", stdout=out, stderr=out)
        except SystemExit:
            self.fail("Models changed but a migration is missing:\n" + out.getvalue())

    def test_every_template_compiles(self):
        problems = []
        for name in project_template_names():
            try:
                get_template(name)
            except Exception as exc:
                problems.append(f"{name}: {exc!r}")
        self.assertFalse(problems, "Broken templates:\n" + "\n".join(problems))

    def test_gitignore_protects_secrets_and_database(self):
        path = Path(settings.BASE_DIR) / ".gitignore"
        self.assertTrue(path.exists(), ".gitignore is missing")
        lines = {ln.strip().strip("/") for ln in path.read_text(encoding="utf-8").splitlines()}
        self.assertTrue(lines & {".env", ".env*", "*.env"}, ".env is not ignored by git")
        self.assertTrue(lines & {"db.sqlite3", "*.sqlite3"}, "SQLite database is not ignored by git")
        self.assertTrue(lines & {".venv", "venv", ".venv*"}, "Virtual environment is not ignored by git")


class PublicPagesSmokeTest(TestCase):
    def test_every_url_without_arguments_does_not_crash(self):
        problems = []
        for route in public_routes():
            url = "/" + route
            try:
                response = self.client.get(url)
            except Exception as exc:
                problems.append(f"{url} raised {exc!r}")
                continue
            if response.status_code >= 500:
                problems.append(f"{url} returned {response.status_code}")
        self.assertFalse(problems, "Pages that crash:\n" + "\n".join(problems))

    def test_unknown_page_gives_404_not_a_crash(self):
        self.assertEqual(self.client.get("/this-page-does-not-exist-xyz/").status_code, 404)


class AdminSecurityTest(TestCase):
    def test_anonymous_visitor_is_sent_to_admin_login(self):
        response = self.client.get(reverse(f"{admin_site.name}:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_normal_customer_cannot_open_admin(self):
        self.client.force_login(make_user("customer_test", staff=False))
        response = self.client.get(reverse(f"{admin_site.name}:index"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("login", response["Location"])

    def test_every_registered_model_opens_for_admin(self):
        self.client.force_login(make_user("admin_test", staff=True))
        problems = []
        for model in admin_site._registry:
            opts = model._meta
            for kind in ("changelist", "add"):
                name = f"{admin_site.name}:{opts.app_label}_{opts.model_name}_{kind}"
                try:
                    response = self.client.get(reverse(name))
                except Exception as exc:
                    problems.append(f"{name}: {exc!r}")
                    continue
                if response.status_code != 200:
                    problems.append(f"{name}: status {response.status_code}")
        self.assertFalse(problems, "Admin pages that fail:\n" + "\n".join(problems))


@unittest.skipUnless(
    os.environ.get("CHECK_PRODUCTION") == "1",
    "Only runs with CHECK_PRODUCTION=1 and your real production settings loaded",
)
class ProductionSettingsTest(SimpleTestCase):
    """Run this last, with your production .env loaded, right before deploying."""

    def test_secret_key_is_not_the_default(self):
        self.assertFalse(settings.SECRET_KEY.startswith("django-insecure"), "Using the default SECRET_KEY")

    def test_allowed_hosts_are_set_and_not_wildcard(self):
        self.assertTrue(settings.ALLOWED_HOSTS, "ALLOWED_HOSTS is empty")
        self.assertNotIn("*", settings.ALLOWED_HOSTS)

    def test_https_and_secure_cookies_are_on(self):
        self.assertTrue(settings.SECURE_SSL_REDIRECT, "SECURE_SSL_REDIRECT is off")
        self.assertTrue(settings.SESSION_COOKIE_SECURE, "SESSION_COOKIE_SECURE is off")
        self.assertTrue(settings.CSRF_COOKIE_SECURE, "CSRF_COOKIE_SECURE is off")
