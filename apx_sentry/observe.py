"""Read-only looks at a Sentry organization's issues: what a release introduced and what broke since a moment."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from action_platform.core.exception import ActionPlatformError
from action_platform.core.service_access import Http
from pydantic import BaseModel

MAX = 100


class Issue(BaseModel):
    id: str
    short_id: str
    title: str
    culprit: Optional[str] = None
    level: Optional[str] = None
    status: Optional[str] = None
    count: int
    users: int
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    permalink: Optional[str] = None
    project: str


class Sentry:
    def __init__(self, org: str, http: Http) -> None:
        self.org = org
        self.http = http

    def project_id(self, project: str) -> str:
        found = self.http.call("GET", f"api/0/projects/{self.org}/{project}/")

        if not isinstance(found, dict) or not found.get("id"):
            raise ActionPlatformError(f"sentry: no project {project!r} in {self.org}")

        return str(found["id"])

    def release_issues(
        self, project: str, release: str, period: str = "30d", limit: int = 25
    ) -> list[Issue]:
        """Issues whose first event came in `release`, newest first."""
        return self._issues(
            {
                "project": self.project_id(project),
                "query": f"firstRelease:{_quote(release)}",
                "statsPeriod": period,
                "sort": "new",
                "limit": _limit(limit),
            }
        )

    def latest_errors(
        self, project: str, since: str, limit: int = 25, until: Optional[str] = None
    ) -> list[Issue]:
        """Unresolved issues with events between `since` and `until` (now), the most recently seen first."""
        start = _moment(since)
        end = _moment(until) if until else _now()

        return self._issues(
            {
                "project": self.project_id(project),
                "query": "is:unresolved",
                "start": start,
                "end": end,
                "sort": "date",
                "limit": _limit(limit),
            }
        )

    def _issues(self, query: dict[str, Any]) -> list[Issue]:
        rows = self.http.call(
            "GET", f"api/0/organizations/{self.org}/issues/", query=query
        )

        if not isinstance(rows, list):
            raise ActionPlatformError("sentry: the issues listing is not a list")

        return [_issue(r) for r in rows]


def _issue(row: dict[str, Any]) -> Issue:
    return Issue(
        id=str(row["id"]),
        short_id=str(row.get("shortId") or row["id"]),
        title=row.get("title") or "",
        culprit=row.get("culprit"),
        level=row.get("level"),
        status=row.get("status"),
        count=int(row.get("count") or 0),
        users=int(row.get("userCount") or 0),
        first_seen=row.get("firstSeen"),
        last_seen=row.get("lastSeen"),
        permalink=row.get("permalink"),
        project=(row.get("project") or {}).get("slug", ""),
    )


def _quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _limit(limit: int) -> int:
    return max(1, min(limit, MAX))


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _moment(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.strip())
    except ValueError as e:
        raise ActionPlatformError(
            f"sentry: {value!r} is not an ISO 8601 time, e.g. 2026-11-24T14:30:00Z"
        ) from e

    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc)

    return parsed.strftime("%Y-%m-%dT%H:%M:%S")
