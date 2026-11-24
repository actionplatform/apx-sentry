# AGENTS.md

Rules an AI agent (or a new contributor) follows in this repository.

## What this is

`apx-sentry`, an Action Platform plugin for [Sentry](https://sentry.io): the access provider the core's access engine drives, and read-only tools for a release's new issues and the errors after a deploy. The contract every plugin follows is `SPEC.md` in [apx-example](https://github.com/actionplatform/apx-example); read it before changing the shape of anything here.

## How it works

- `access.py` is the `AccessProvider`: organization members with their role, team members with their team role, invitations by email, never the last owner. The core's `Access` engine reads, diffs and applies; nothing here decides policy.
- `observe.py` reads issues through the REST API with the core's `Http`; `tools.py` and `cli.py` only present it.
- `SentryPlugin.access(options)` reads `options` and nothing else. The tools and the CLI resolve a setting from `AP_SENTRY_<KEY>` first, then the options file (`settings.py`).

## Code

- Python 3.11+, `ruff check . && ruff format --check .`, `pytest` green before a commit.
- No comments in code; no test docstrings. Module docstrings say what the module is for.
- `register` declares only: no I/O at import or in `register`.
- Never monkey-patch `action_platform.*`.
- Tests drive `tests/fake.py`, which answers only the routes and fields Sentry's API documents; `tests/live/` is read-only and runs only with `AP_SENTRY_LIVE=1`.
- `needs` lists every host and environment variable the plugin touches.

## Commits and branches

[Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/): `type(scope): description`; one commit per concern; stage files explicitly. Git-flow: `<kind>/<issue>-<slug>` from `master`, kinds `feature bugfix hotfix release chore docs refactor test ci perf`; never commit on `master`. One pull request per issue.

## Release

`action-platform release <level>`; the tag publishes to PyPI; then a PR to `plugins-index` with the new `latest`.
