import unittest

from action_platform.core.service_access import (
    Access,
    AccessError,
    Grant,
    Op,
    Person,
    spec,
)
from action_platform.testing.access import MemoryDirectory

from apx_sentry.access import SentryProvider
from tests.fake import FakeSentry

ANA = Person("ana@acme.dev", "u-ana", "Ana", "owner", ("platform",))
BEN = Person("ben@acme.dev", "u-ben", "Ben", "developer", ("backend",))


class World(unittest.TestCase):
    def setUp(self):
        self.sentry = FakeSentry(page=1)
        self.sentry.add("ana@acme.dev", "owner", {"web": "admin"})
        self.sentry.add("ben@acme.dev", "member", {"web": None})
        self.sentry.add("old@agency.dev", "member")
        self.directory = MemoryDirectory([ANA, BEN])
        self.access = Access(
            self.directory, {"sentry": SentryProvider("acme", "t", http=self.sentry)}
        )

    def bootstrapped(self):
        self.access.sync(apply=True)


class Reading(World):
    def test_every_page_of_members_and_teams_is_read(self):
        fake = FakeSentry(page=1)

        for n in range(3):
            fake.add(f"p{n}@acme.dev", "member", {"web": "admin"})

        grants = SentryProvider("acme", "t", http=fake).read()

        self.assertEqual(len([g for g in grants if g.resource == "org"]), 3)
        self.assertEqual(
            [g.level for g in grants if g.resource == "team/web"], ["admin"] * 3
        )
        listing = [c for c in fake.calls if c[1].endswith("acme/members")]
        self.assertEqual(len(listing), 3)

    def test_team_members_without_a_role_are_contributors(self):
        grants = SentryProvider("acme", "t", http=self.sentry).read()

        self.assertIn(
            Grant("sentry", "ben@acme.dev", "team/web", "contributor"), grants
        )
        self.assertIn(Grant("sentry", "ana@acme.dev", "team/web", "admin"), grants)
        self.assertIn(Grant("sentry", "ana@acme.dev", "org", "owner"), grants)


class Import(World):
    def test_first_sync_imports_and_changes_nothing(self):
        plan = self.access.sync(apply=True)

        self.assertTrue(plan.bootstrap)
        self.assertEqual(plan.changes, [])
        self.assertEqual(self.sentry.writes(), [])
        self.assertEqual(sorted(self.directory.mapping.imported), ["sentry"])
        self.assertEqual(self.access.sync().changes, [])

    def test_members_link_by_email_and_outsiders_are_kept(self):
        self.bootstrapped()
        m = self.directory.mapping

        self.assertEqual(m.people["ben@acme.dev"]["sentry"], "ben@acme.dev")
        self.assertIn(
            ("sentry", "old@agency.dev"), {(r["service"], r["account"]) for r in m.keep}
        )
        self.assertIn(spec("sentry", "team/web", "admin"), m.grants["ana@acme.dev"])

    def test_dry_run_import_stores_nothing(self):
        plan = self.access.sync()

        self.assertTrue(plan.bootstrap and plan.dry_run)
        self.assertEqual(self.directory.saved, 0)
        self.assertEqual(self.sentry.writes(), [])


class Changes(World):
    def test_grant_dry_run_writes_nothing(self):
        self.bootstrapped()

        plan = self.access.grant("ben@acme.dev", "sentry", "team/web", "admin")

        self.assertEqual(plan.changes[0].action, "change")
        self.assertEqual(self.sentry.writes(), [])

    def test_grant_changes_the_team_role_only(self):
        self.bootstrapped()

        self.access.grant("ben@acme.dev", "sentry", "team/web", "admin", apply=True)

        sent = [(m, r.split("/", 5)[-1], b) for m, r, b in self.sentry.writes()]
        self.assertEqual(
            sent,
            [
                (
                    "PUT",
                    f"{self.sentry.members[1]['id']}/teams/web",
                    {"teamRole": "admin"},
                )
            ],
        )
        self.assertEqual(self.access.sync().changes, [])

    def test_grant_refuses_a_level_sentry_does_not_have(self):
        self.bootstrapped()

        with self.assertRaisesRegex(AccessError, "takes member, billing"):
            self.access.grant("ben@acme.dev", "sentry", "org", "root")

    def test_policy_drives_an_invitation(self):
        self.bootstrapped()
        self.directory.members.append(
            Person("cy@acme.dev", "u-cy", "Cy", "developer", ())
        )
        self.directory.mapping.people["cy@acme.dev"] = {"sentry": "cy@acme.dev"}
        self.directory.mapping.roles["developer"] = [spec("sentry", "org", "member")]

        plan = self.access.sync(apply=True)

        self.assertEqual([c.action for c in plan.changes], ["add"])
        self.assertTrue(self.sentry.members[-1]["pending"])
        self.assertEqual(self.sentry.writes()[0][2]["email"], "cy@acme.dev")
        self.assertEqual(self.access.sync().changes, [])

    def test_leaving_the_organization_is_drift(self):
        self.bootstrapped()
        self.directory.members = [ANA]

        drift = {
            (c.account, c.action) for s in self.access.audit().services for c in s.drift
        }

        self.assertIn(("ben@acme.dev", "remove"), drift)

    def test_offboard_removes_the_member(self):
        self.bootstrapped()

        self.access.offboard("ben@acme.dev", apply=True)

        self.assertNotIn("ben@acme.dev", [m["email"] for m in self.sentry.members])
        self.assertEqual(self.access.sync().changes, [])


class LastOwner(World):
    def test_the_last_owner_is_never_removed(self):
        self.bootstrapped()

        plan = self.access.offboard("ana@acme.dev", apply=True)

        refused = {(c.resource, c.status) for c in plan.changes}
        self.assertIn(("org", "refused"), refused)
        self.assertIn("ana@acme.dev", [m["email"] for m in self.sentry.members])
        self.assertEqual(self.sentry.members[0]["orgRole"], "owner")

    def test_guard_names_the_owner_and_the_organization(self):
        provider = SentryProvider("acme", "t", http=self.sentry)
        live = provider.read()
        op = Op("change", Grant("sentry", "ana@acme.dev", "org", "admin"), "owner")

        refused = provider.guard([op], live)

        self.assertEqual(
            refused, {op: "sentry: ana@acme.dev is the last owner of acme"}
        )

    def test_a_second_owner_lets_the_first_go(self):
        self.sentry.add("zoe@acme.dev", "owner")
        provider = SentryProvider("acme", "t", http=self.sentry)
        op = Op("remove", Grant("sentry", "ana@acme.dev", "org", "owner"))

        self.assertEqual(provider.guard([op], provider.read()), {})

    def test_an_account_that_is_not_a_member_is_named(self):
        provider = SentryProvider("acme", "t", http=self.sentry)

        with self.assertRaisesRegex(AccessError, "ghost@acme.dev is not a member"):
            provider.apply(
                Op("remove", Grant("sentry", "ghost@acme.dev", "org", "member"))
            )


class Failures(unittest.TestCase):
    def test_a_refusal_names_the_call_and_no_credential(self):
        fake = FakeSentry()
        provider = SentryProvider("acme", "secret-token", http=fake)

        with self.assertRaises(AccessError) as caught:
            provider.apply(
                Op("add", Grant("sentry", "x@acme.dev", "team/none", "contributor"))
            )

        self.assertNotIn("secret-token", str(caught.exception))
