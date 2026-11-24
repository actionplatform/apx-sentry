"""`action-platform sentry …` — the same reads as the tools, from a terminal."""

from __future__ import annotations

from typing import Any

import typer

from apx_sentry.observe import Issue
from apx_sentry.settings import connect

app = typer.Typer(
    help="Sentry: issues of a release, errors since a moment.", no_args_is_help=True
)
options: Any | None = None


def show(issues: list[Issue]) -> None:
    for i in issues:
        typer.echo(
            f"{i.short_id}\t{i.count} events\t{i.users} users\t{i.last_seen}\t{i.title}\t{i.culprit or '-'}\t{i.permalink or '-'}"
        )


@app.command("release-issues")
def release_issues(
    project: str,
    release: str,
    period: str = typer.Option("30d", help="How far back to look"),
    limit: int = typer.Option(25),
) -> None:
    """Issues first seen in a release of a project."""
    show(connect(options).release_issues(project, release, period, limit))


@app.command("latest-errors")
def latest_errors(
    project: str,
    since: str = typer.Argument(..., help="ISO 8601 time, e.g. 2026-11-24T14:30:00Z"),
    limit: int = typer.Option(25),
) -> None:
    """Unresolved issues of a project with events since a moment."""
    show(connect(options).latest_errors(project, since, limit))
