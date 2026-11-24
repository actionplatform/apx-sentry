import unittest

from action_platform.core.exception import ActionPlatformError
from action_platform.core.service_access import AccessError

from apx_sentry.observe import Sentry
from tests.fake import FakeSentry


class Observe(unittest.TestCase):
    def setUp(self):
        self.fake = FakeSentry()
        self.fake.project("web")
        self.fake.project("worker")
        self.fake.issue("web", "KeyError: 'id'", "web@1.4.0", 12, 5)
        self.fake.issue(
            "web",
            "TimeoutError",
            "web@1.4.0",
            3,
            2,
            first_seen="2026-11-24T11:00:00Z",
            last_seen="2026-11-24T12:00:00Z",
        )
        self.fake.issue("web", "ValueError", "web@1.3.0", 99, 40)
        self.fake.issue("worker", "Other project", "web@1.4.0")
        self.sentry = Sentry("acme", self.fake)

    def test_release_issues_are_the_ones_first_seen_in_it(self):
        found = self.sentry.release_issues("web", "web@1.4.0")

        self.assertEqual([i.title for i in found], ["TimeoutError", "KeyError: 'id'"])
        first = found[1]
        self.assertEqual((first.count, first.users), (12, 5))
        self.assertEqual(first.culprit, "app.views in index")
        self.assertEqual(first.project, "web")
        self.assertTrue(first.permalink.startswith("https://sentry.io/"))

    def test_release_issues_ask_the_documented_query(self):
        self.sentry.release_issues("web", 'we"ird@1', period="90d", limit=500)

        asked = self.fake.queries[-1]
        self.assertEqual(asked["query"], 'firstRelease:"we\\"ird@1"')
        self.assertEqual(asked["project"], self.fake.projects["web"]["id"])
        self.assertEqual(asked["statsPeriod"], "90d")
        self.assertEqual(asked["sort"], "new")
        self.assertEqual(asked["limit"], "100")
        self.assertEqual(self.fake.writes(), [])

    def test_latest_errors_since_a_moment(self):
        self.fake.issue(
            "web",
            "Resolved",
            "web@1.4.0",
            status="resolved",
            last_seen="2026-11-24T12:30:00Z",
        )

        found = self.sentry.latest_errors(
            "web", "2026-11-24T10:30:00Z", until="2026-11-24T13:00:00Z"
        )

        self.assertEqual([i.title for i in found], ["TimeoutError"])
        asked = self.fake.queries[-1]
        self.assertEqual(asked["start"], "2026-11-24T10:30:00")
        self.assertEqual(asked["end"], "2026-11-24T13:00:00")
        self.assertEqual(asked["query"], "is:unresolved")
        self.assertEqual(asked["sort"], "date")

    def test_a_moment_with_an_offset_is_sent_in_utc(self):
        self.sentry.latest_errors("web", "2026-11-24T09:00:00-03:00")

        self.assertEqual(self.fake.queries[-1]["start"], "2026-11-24T12:00:00")
        self.assertIn("end", self.fake.queries[-1])

    def test_latest_errors_defaults_to_now(self):
        self.assertEqual(self.sentry.latest_errors("web", "2999-01-01T00:00:00Z"), [])

    def test_a_bad_moment_is_refused_before_any_call(self):
        with self.assertRaisesRegex(ActionPlatformError, "not an ISO 8601"):
            self.sentry.latest_errors("web", "after the deploy")

        self.assertEqual(self.fake.calls, [])

    def test_an_unknown_project_names_the_service_call(self):
        with self.assertRaisesRegex(AccessError, "answered 404"):
            self.sentry.release_issues("nope", "web@1.4.0")


class Tools(unittest.TestCase):
    def test_both_tools_are_registered_read_only_and_answer_typed_issues(self):
        from unittest import mock

        from apx_sentry.tools import register_tools

        fake = FakeSentry()
        fake.project("web")
        fake.issue("web", "Boom", "web@2", 4, 2)
        registered = {}

        class Mcp:
            def tool(self, **kwargs):
                def keep(fn):
                    registered[fn.__name__] = (fn, kwargs)
                    return fn

                return keep

        register_tools(Mcp(), None)

        with mock.patch("apx_sentry.tools.connect", return_value=Sentry("acme", fake)):
            found = registered["release_issues"][0]("web", "web@2")
            errors = registered["latest_errors"][0]("web", "2026-11-24T00:00:00Z")

        self.assertEqual(sorted(registered), ["latest_errors", "release_issues"])
        self.assertTrue(
            all(k["annotations"].read_only_hint for _, k in registered.values())
        )
        self.assertEqual([i.title for i in found], ["Boom"])
        self.assertEqual([i.title for i in errors], ["Boom"])
