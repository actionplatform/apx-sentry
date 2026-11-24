import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from action_platform.core.service_access import AccessError
from action_platform.plugins.options import FileOptions

from apx_sentry import SentryPlugin
from apx_sentry.access import SentryProvider
from apx_sentry.settings import connect, credentials


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

    def test_a_missing_token_is_named(self):
        self.options.set("org", "acme")

        with self.assertRaisesRegex(AccessError, "token"):
            SentryPlugin().access(self.options)

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
