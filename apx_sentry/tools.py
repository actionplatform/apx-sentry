"""`sentry_*` MCP tools: read-only looks at issues. Access is changed through the core's `access_*` tools."""

from __future__ import annotations

from typing import Annotated, Any

from action_platform.mcp.annotations import READ_ONLY
from pydantic import Field

from apx_sentry.observe import Issue
from apx_sentry.settings import connect

Project = Annotated[str, Field(description="The project's slug in Sentry")]
Limit = Annotated[int, Field(description="How many issues, at most 100")]


def register_tools(mcp: Any, options: Any) -> None:
    @mcp.tool(annotations=READ_ONLY)
    def release_issues(
        project: Project,
        release: Annotated[
            str, Field(description="The release version as Sentry has it")
        ],
        period: Annotated[
            str, Field(description="How far back to look, as 14d, 30d or 90d")
        ] = "30d",
        limit: Limit = 25,
    ) -> list[Issue]:
        """Issues first seen in a release of a project, newest first, each with its title, culprit, event and user counts, first and last seen, and link."""
        return connect(options).release_issues(project, release, period, limit)

    @mcp.tool(annotations=READ_ONLY)
    def latest_errors(
        project: Project,
        since: Annotated[
            str,
            Field(
                description="ISO 8601 time to look from, such as the deploy's: 2026-11-24T14:30:00Z"
            ),
        ],
        limit: Limit = 25,
    ) -> list[Issue]:
        """Unresolved issues of a project with events since a moment, the most recently seen first — what broke after a deploy."""
        return connect(options).latest_errors(project, since, limit)
