"""Sentry in memory. It answers only the routes and fields the REST API documents and keeps state, so a change shows up on the next read."""

from __future__ import annotations

import json
import urllib.parse
from typing import Any, Optional

from action_platform.core.service_access import Http, Response


class FakeHttp(Http):
    def __init__(self, service: str, base: str) -> None:
        super().__init__(service, base, {})
        self.calls: list[tuple[str, str, Any]] = []
        self.queries: list[dict[str, str]] = []

    def send(self, method, path, body=None, query=None, form=None) -> Response:
        url = urllib.parse.urlsplit(self.url(path, query))
        q = {k: v[0] for k, v in urllib.parse.parse_qs(url.query).items()}
        route = url.path.replace(urllib.parse.urlsplit(self.base).path, "", 1).strip(
            "/"
        )
        sent = json.loads(json.dumps(body)) if body is not None else None
        self.calls.append((method, route, sent))
        self.queries.append(q)

        return self.handle(method, route, q, sent)

    def writes(self) -> list[tuple[str, str, Any]]:
        return [c for c in self.calls if c[0] != "GET"]

    def handle(self, method: str, route: str, q: dict, body: Any) -> Response:
        raise NotImplementedError


def _page(items: list, q: dict, size: Optional[int], url: str) -> Response:
    if size is None:
        return Response(200, items)

    start = int(q.get("cursor", "0"))
    chunk = items[start : start + size]
    headers = {}

    if start + size < len(items):
        headers["link"] = (
            f'<https://fake/next?cursor=0:0:1>; rel="previous"; results="false", '
            f'<{url}?cursor={start + size}>; rel="next"; results="true"; cursor="{start + size}"'
        )

    return Response(200, chunk, headers)


class FakeSentry(FakeHttp):
    """The member list carries no teams; team membership and team role come from each team's member list, as on sentry.io. Issues carry `count` as a string and `userCount` as an integer, as the issues listing sends them."""

    def __init__(self, page: Optional[int] = None) -> None:
        super().__init__("sentry", "https://sentry.io")
        self.page = page
        self.members: list[dict] = []
        self.teams: dict[str, dict[str, Optional[str]]] = {}
        self.next_id = 100
        self.projects: dict[str, dict] = {}
        self.issues: list[dict] = []
        self.first_release: dict[str, str] = {}

    def add(
        self, email: str, role: str, teams: dict[str, Optional[str]] | None = None
    ) -> None:
        self.next_id += 1
        member = {
            "id": str(self.next_id),
            "email": email,
            "orgRole": role,
            "role": role,
            "pending": False,
        }
        self.members.append(member)

        for slug, team_role in (teams or {}).items():
            self.teams.setdefault(slug, {})[member["id"]] = team_role

    def project(self, slug: str, platform: str = "python") -> dict:
        row = {
            "id": str(4505278496 + len(self.projects)),
            "slug": slug,
            "name": slug.title(),
            "platform": platform,
        }
        self.projects[slug] = row

        return row

    def issue(
        self,
        project: str,
        title: str,
        release: str,
        count: int = 1,
        users: int = 1,
        first_seen: str = "2026-11-24T10:00:00Z",
        last_seen: str = "2026-11-24T10:05:00Z",
        status: str = "unresolved",
        culprit: str = "app.views in index",
    ) -> dict:
        self.next_id += 1
        row = {
            "id": str(self.next_id),
            "shortId": f"{project.upper()}-{self.next_id}",
            "title": title,
            "culprit": culprit,
            "permalink": f"https://sentry.io/organizations/acme/issues/{self.next_id}/",
            "level": "error",
            "status": status,
            "count": str(count),
            "userCount": users,
            "firstSeen": first_seen,
            "lastSeen": last_seen,
            "project": {
                "id": self.projects[project]["id"],
                "name": self.projects[project]["name"],
                "slug": project,
                "platform": self.projects[project]["platform"],
            },
            "metadata": {"title": title},
        }
        self.issues.append(row)
        self.first_release[row["id"]] = release

        return row

    def handle(self, method, route, q, body):
        p = route.split("/")
        base = ["api", "0", "organizations", "acme", "members"]

        if p[:3] == ["api", "0", "projects"] and len(p) == 5 and method == "GET":
            found = self.projects.get(p[4]) if p[3] == "acme" else None

            if found is None:
                return Response(
                    404, {"detail": "The requested resource does not exist"}
                )

            return Response(200, found)

        if p == ["api", "0", "organizations", "acme", "issues"] and method == "GET":
            return self.listing(q)

        if p == ["api", "0", "organizations", "acme", "teams"]:
            return _page(
                [{"slug": s} for s in self.teams], q, self.page, self.url(route)
            )

        if p[:4] == ["api", "0", "teams", "acme"] and p[5] == "members":
            rows = [
                {**m, "teamRole": self.teams[p[4]][m["id"]], "teamSlug": p[4]}
                for m in self.members
                if m["id"] in self.teams.get(p[4], {})
            ]
            return _page(rows, q, self.page, self.url(route))

        if p == base and method == "GET":
            return _page(self.members, q, self.page, self.url(route))

        if p == base and method == "POST":
            self.add(body["email"], body["orgRole"])
            self.members[-1]["pending"] = True
            return Response(201, {"id": self.members[-1]["id"], "email": body["email"]})

        member = next((m for m in self.members if p[:6] == base + [m["id"]]), None)

        if member is None:
            return Response(404, {"detail": "The requested resource does not exist"})

        if len(p) == 6 and method == "PUT":
            member["orgRole"] = member["role"] = body["orgRole"]
            return Response(200, member)

        if len(p) == 6 and method == "DELETE":
            self.members.remove(member)

            for team in self.teams.values():
                team.pop(member["id"], None)
            return Response(204, None)

        team = self.teams.get(p[7])

        if team is None:
            return Response(404, {"detail": "The requested resource does not exist"})

        if method == "POST":
            team.setdefault(member["id"], None)
            return Response(201, {})

        if method == "PUT":
            team[member["id"]] = body["teamRole"]
            return Response(200, {})

        team.pop(member["id"], None)
        return Response(204, None)

    def listing(self, q: dict) -> Response:
        if "start" in q and "end" not in q:
            return Response(400, {"detail": "start and end go together"})

        rows = [i for i in self.issues if i["project"]["id"] == q.get("project")]
        query = q.get("query", "is:unresolved")

        for term in _terms(query):
            if term == "is:unresolved":
                rows = [i for i in rows if i["status"] == "unresolved"]
            elif term.startswith("firstRelease:"):
                wanted = term.split(":", 1)[1].strip('"')
                rows = [i for i in rows if self.first_release[i["id"]] == wanted]

        if "start" in q:
            rows = [i for i in rows if q["start"] <= i["lastSeen"][:19] <= q["end"]]

        key = {"date": "lastSeen", "new": "firstSeen"}[q.get("sort", "date")]
        rows = sorted(rows, key=lambda i: i[key], reverse=True)

        return Response(200, rows[: int(q.get("limit", 100))])


def _terms(query: str) -> list[str]:
    terms, current, quoted = [], "", False

    for ch in query:
        if ch == '"':
            quoted = not quoted

        if ch == " " and not quoted:
            terms.append(current)
            current = ""
        else:
            current += ch

    return [t for t in terms + [current] if t]
