"""Against a real Sentry, read only: set AP_SENTRY_LIVE=1, AP_SENTRY_ORG and AP_SENTRY_TOKEN, and AP_SENTRY_PROJECT (a project slug) for the issue tools. Nothing here changes Sentry."""

import os
import unittest

from apx_sentry.access import SentryProvider
from apx_sentry.settings import connect, credentials

LIVE = os.environ.get("AP_SENTRY_LIVE") == "1"
PROJECT = os.environ.get("AP_SENTRY_PROJECT", "")


@unittest.skipUnless(LIVE, "AP_SENTRY_LIVE=1 and AP_SENTRY_* settings run this suite")
class LiveRead(unittest.TestCase):
    def test_access_reads_members_and_teams(self):
        org, token, url = credentials()

        grants = SentryProvider(org, token, url).read()

        self.assertTrue(grants)
        self.assertTrue(all(g.service == "sentry" for g in grants))
        self.assertEqual(len({g.key for g in grants}), len(grants))
        self.assertTrue(any(g.resource == "org" and g.level == "owner" for g in grants))

    @unittest.skipUnless(PROJECT, "AP_SENTRY_PROJECT names a project")
    def test_latest_errors_answers_typed_issues(self):
        found = connect().latest_errors(PROJECT, "2020-01-01T00:00:00Z", limit=5)

        self.assertLessEqual(len(found), 5)

        for issue in found:
            self.assertTrue(issue.id and issue.title)
            self.assertGreaterEqual(issue.count, 0)
            self.assertEqual(issue.project, PROJECT)

    @unittest.skipUnless(PROJECT, "AP_SENTRY_PROJECT names a project")
    @unittest.skipUnless(
        os.environ.get("AP_SENTRY_RELEASE"), "AP_SENTRY_RELEASE names a release"
    )
    def test_release_issues_answers_typed_issues(self):
        found = connect().release_issues(
            PROJECT, os.environ["AP_SENTRY_RELEASE"], limit=5
        )

        for issue in found:
            self.assertEqual(issue.project, PROJECT)
