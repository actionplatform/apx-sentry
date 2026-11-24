import importlib
import json
import os
import tempfile
import unittest
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from unittest import mock

from action_platform.core.service_access import AccessError
from action_platform.plugins.options import FileOptions

from apx_sentry import SentryPlugin
from apx_sentry.access import SCOPES, SentryProvider
from apx_sentry.settings import connect, credentials


@dataclass(frozen=True)
class Credential:
    kind: str
    token: str
    login: str = ""
    api_url: Optional[str] = None
    scopes: Optional[tuple] = None
    app: Optional[str] = None


class Connected(dict):
    def __init__(self, found, **values):
        super().__init__(**values)
        self.found = found

    def credential(self, kind):
        return self.found if kind == "sentry" else None


HAS_CONNECTIONS = hasattr(importlib.import_module("action_platform.abc"), "Connection")


class Options(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.options = FileOptions("sentry", Path(self.dir.name))
        self.env = mock.patch.dict(
            os.environ,
            {k: v for k, v in os.environ.items() if not k.startswith("AP_SENTRY_")},
            clear=True,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.dir.cleanup()


class Declaration(unittest.TestCase):
    def test_the_plugin_declares_what_it_reads_and_touches(self):
        plugin = SentryPlugin()

        self.assertEqual(
            (plugin.slug, plugin.name, plugin.min_core), ("sentry", "Sentry", "0.33")
        )
        self.assertEqual([o.key for o in plugin.options], ["org", "token", "url"])
        self.assertEqual(
            {o.key: o.kind for o in plugin.options},
            {"org": "text", "token": "secret", "url": "url"},
        )
        self.assertTrue(any("AP_SENTRY_TOKEN" in n for n in plugin.needs))
        self.assertTrue(any("sentry.io" in n for n in plugin.needs))


class Access(Options):
    def test_no_organization_means_no_access(self):
        self.assertIsNone(SentryPlugin().access(self.options))

    def test_without_token_nor_connection_it_says_to_connect(self):
        self.options.set("org", "acme")

        with self.assertRaisesRegex(AccessError, "connect Sentry under Settings"):
            SentryPlugin().access(self.options)

    def test_the_connection_is_used_when_the_token_option_is_empty(self):
        found = Credential("sentry", "sntr-x", "ana", None, SCOPES)
        provider = SentryPlugin().access(Connected(found, org="acme"))

        self.assertEqual(provider.http.headers["authorization"], "Bearer sntr-x")
        self.assertEqual(provider.http.base, "https://sentry.io")

    def test_the_connection_never_goes_to_the_url_option(self):
        found = Credential("sentry", "x", "ana", None, SCOPES)
        provider = SentryPlugin().access(
            Connected(found, org="acme", url="https://elsewhere.example")
        )

        self.assertEqual(provider.http.base, "https://sentry.io")

    def test_a_self_hosted_connection_keeps_its_url(self):
        found = Credential(
            "sentry", "x", "ana", "https://sentry.example.com/api/0", SCOPES
        )
        provider = SentryPlugin().access(Connected(found, org="acme"))

        self.assertEqual(provider.http.base, "https://sentry.example.com")

    def test_a_missing_scope_is_named_with_the_way_to_grant_it(self):
        found = Credential("sentry", "x", "ana", None, ("org:read",))

        with self.assertRaisesRegex(
            AccessError, "lacks member:admin, team:write; reconnect Sentry"
        ):
            SentryPlugin().access(Connected(found, org="acme"))

    def test_the_token_option_wins_over_the_connection(self):
        found = Credential("sentry", "x", "ana", None, ())
        provider = SentryPlugin().access(Connected(found, org="acme", token="t"))

        self.assertEqual(provider.http.headers["authorization"], "Bearer t")

    @unittest.skipUnless(HAS_CONNECTIONS, "core without connections")
    def test_it_declares_the_sentry_connection(self):
        (declared,) = SentryPlugin.connections

        self.assertEqual((declared.kind, declared.scopes), ("sentry", SCOPES))

    def test_the_provider_is_built_from_the_options(self):
        self.options.set("org", "acme")
        self.options.set("token", "t")
        self.options.set("url", "https://sentry.example.com")

        provider = SentryPlugin().access(self.options)

        self.assertIsInstance(provider, SentryProvider)
        self.assertEqual(provider.org, "acme")
        self.assertEqual(provider.http.base, "https://sentry.example.com")

    def test_access_ignores_the_environment(self):
        with mock.patch.dict(os.environ, {"AP_SENTRY_ORG": "env-org"}):
            self.assertIsNone(SentryPlugin().access(self.options))


class Settings(Options):
    def test_the_environment_wins_over_the_options_file(self):
        self.options.set("org", "file-org")
        self.options.set("token", "file-token")

        with mock.patch.dict(os.environ, {"AP_SENTRY_ORG": "env-org"}):
            org, token, url = credentials(self.options)

        self.assertEqual(
            (org, token, url), ("env-org", "file-token", "https://sentry.io")
        )

    def test_missing_keys_are_named(self):
        with self.assertRaisesRegex(AccessError, "AP_SENTRY_ORG, AP_SENTRY_TOKEN"):
            connect(self.options)

    def test_the_file_is_plain_json(self):
        self.options.set("org", "acme")

        self.assertEqual(json.loads(self.options.file.read_text()), {"org": "acme"})
