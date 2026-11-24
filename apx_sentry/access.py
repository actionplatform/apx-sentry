"""A Sentry organization: membership with its organization role, and team membership with its team role."""

from __future__ import annotations

from typing import Optional

from action_platform.core.service_access import (
    AccessError,
    AccessProvider,
    Grant,
    Http,
    Op,
)


class SentryProvider(AccessProvider):
    """Accounts are member emails. An added member gets Sentry's invitation email and counts as granted while it is pending."""

    name = "sentry"
    levels = {
        "org": ("member", "billing", "admin", "manager", "owner"),
        "team": ("contributor", "admin"),
    }

    def __init__(
        self,
        org: str,
        token: str,
        url: str = "https://sentry.io",
        http: Optional[Http] = None,
    ) -> None:
        self.org = org
        self.http = http or Http("sentry", url, {"authorization": f"Bearer {token}"})
        self.ids: dict[str, str] = {}

    def rank(self, grant: Grant) -> int:
        if grant.resource == "org":
            return {
                "member": 0,
                "billing": 0,
                "admin": 1,
                "manager": 2,
                "owner": 3,
            }.get(grant.level, -1)

        return super().rank(grant)

    def read(self) -> list[Grant]:
        grants: list[Grant] = []
        self.ids = {}

        for m in self.http.pages(f"api/0/organizations/{self.org}/members/"):
            email = (m.get("email") or "").lower()

            if not email:
                continue

            self.ids[email] = str(m["id"])
            grants.append(
                Grant(
                    "sentry",
                    email,
                    "org",
                    m.get("orgRole") or m.get("role") or "member",
                )
            )

        for team in self.http.pages(f"api/0/organizations/{self.org}/teams/"):
            slug = team["slug"]

            for m in self.http.pages(f"api/0/teams/{self.org}/{slug}/members/"):
                email = (m.get("email") or "").lower()

                if email:
                    level = m.get("teamRole") or "contributor"
                    grants.append(Grant("sentry", email, f"team/{slug}", level))

        return self.strongest(grants)

    def apply(self, op: Op) -> None:
        g, base = op.grant, f"api/0/organizations/{self.org}/members"
        kind, _, team = g.resource.partition("/")

        if kind == "org" and op.action == "add":
            created = self.http.call(
                "POST",
                f"{base}/",
                {"email": g.account, "orgRole": g.level, "teamRoles": []},
            )
            self.ids[g.account.lower()] = str((created or {}).get("id", ""))
            return

        member = self._id(g.account)

        if kind == "org" and op.action == "change":
            self.http.call("PUT", f"{base}/{member}/", {"orgRole": g.level})
        elif kind == "org":
            self.http.call("DELETE", f"{base}/{member}/")
        elif kind == "team" and op.action == "remove":
            self.http.call("DELETE", f"{base}/{member}/teams/{team}/")
        elif kind == "team":
            if op.action == "add":
                self.http.call("POST", f"{base}/{member}/teams/{team}/")

            if op.action == "change" or g.level != "contributor":
                self.http.call(
                    "PUT", f"{base}/{member}/teams/{team}/", {"teamRole": g.level}
                )
        else:
            raise AccessError(f"sentry: cannot apply {g.resource}")

    def guard(self, ops: list[Op], live: list[Grant]) -> dict[Op, str]:
        owners = {g.account for g in live if g.resource == "org" and g.level == "owner"}
        losing = {
            op.grant.account
            for op in ops
            if op.grant.resource == "org"
            and op.grant.account in owners
            and (op.action == "remove" or op.grant.level != "owner")
        }

        if owners and losing >= owners:
            return {
                op: f"sentry: {op.grant.account} is the last owner of {self.org}"
                for op in ops
                if op.grant.resource == "org" and op.grant.account in losing
            }

        return {}

    def _id(self, email: str) -> str:
        if email.lower() not in self.ids:
            self.read()

        found = self.ids.get(email.lower())

        if not found:
            raise AccessError(f"sentry: {email} is not a member of {self.org}")

        return found
