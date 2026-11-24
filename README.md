# apx-sentry

[Sentry](https://sentry.io) for [Action Platform](https://github.com/actionplatform/action-platform): the access provider the core's access engine drives, and two read-only tools over issues. `apx-` is the prefix every Action Platform extension carries.

```bash
action-platform plugin install sentry
export AP_SENTRY_ORG=… AP_SENTRY_TOKEN=…     # or Plugins → Sentry → Configure on the platform
action-platform sentry release-issues web web@1.4.0
action-platform sentry latest-errors web 2026-11-24T14:30:00Z
```

The access capability runs where the core runs service access: on a hosted platform whose API image carries this plugin, with the options filled under **Plugins** for the organization. It needs no pasted token there: it uses the organization's Sentry connection (**Settings → Services → Connect Sentry**, core 0.34 or later). The tools and commands run on the machine that installed it.

## Access

With `org` set, the core's access tools (`access_audit`, `access_who`, `access_sync`, `access_grant`, `access_revoke`, `access_offboard`) read and change Sentry next to the other services. Accounts are member emails.

| Resource | Levels, lowest first |
|---|---|
| `org` | `member`, `billing`, `admin`, `manager`, `owner` |
| `team/<slug>` | `contributor`, `admin` |

- A member's organization role comes from `orgRole`; a team member's role from `teamRole` (a team member without one is a `contributor`).
- Adding a member sends Sentry's invitation email; the member counts as granted while the invitation is pending.
- The last owner of the organization is never removed or demoted.
- Reads follow Sentry's `Link: rel="next"` paging through every page of members, teams and team members.
- Changes are dry runs until the core's tools are told to apply.

## Tools

Read-only. MCP tools are `sentry_<name>`; each is also `action-platform sentry <name>` with dashes. Both return, per issue: `id`, `short_id`, `title`, `culprit`, `level`, `status`, `count` (events), `users`, `first_seen`, `last_seen`, `permalink`, `project`.

| Tool | Does |
|---|---|
| `sentry_release_issues(project, release, period="30d", limit=25)` | Issues first seen in a release of a project, newest first (`firstRelease:"<release>"` on the organization's issues, sorted by first seen). `period` is how far back Sentry looks. |
| `sentry_latest_errors(project, since, limit=25)` | Unresolved issues of a project with events from `since` (ISO 8601, e.g. the deploy's time) until now, most recently seen first. |

`project` is the project's slug; `limit` is at most 100. A `since` with an offset is converted to UTC.

## Options

An organization fills them in under Plugins → Sentry → Configure; on a machine the tools read `AP_SENTRY_<KEY>` first, then the plugin's options file. Access reads the options and the platform's Sentry connection only.

| Option | |
|---|---|
| `org` | Organization slug. Access is off while it is empty. |
| `token` | Secret, optional on a hosted platform: when empty, access uses the organization's Sentry connection. A personal or internal integration token otherwise. |
| `url` | Only for a self-hosted Sentry; empty means `https://sentry.io`. |

### The Sentry connection

On a hosted platform (core 0.34 or later) set only `org`, then **Settings → Services → Connect Sentry** with a Sentry account that is a Manager or Owner of the organization. The platform asks Sentry for the scopes this plugin declares — `org:read`, `member:admin`, `team:write` — keeps the token sealed and refreshes it before it expires. A connection that lacks one of them fails the audit with the missing scope; *Reconnect Sentry* grants it. Connecting needs the platform's Sentry OAuth app once (Sentry → User settings → API → Applications, Confidential, the callback URL the platform shows). The token option, when set, wins over the connection. The issue tools (`sentry_*`, `action-platform sentry …`) run on a machine and still read a token from `AP_SENTRY_TOKEN` or the options file.

### Token scopes

| For | Scopes |
|---|---|
| Reading access | `member:read`, `team:read`, `org:read` |
| Changing access | `member:admin`, `team:write`, `org:read` |
| The issue tools | `project:read`, `event:read` |

## Develop

```bash
pip install -e ".[dev]"
ruff check . && ruff format --check . && pytest -q
```

Tests run without a network against `tests/fake.py`, which answers only the routes and fields Sentry's [API reference](https://docs.sentry.io/api/) documents. `tests/live/` reads a real Sentry and changes nothing:

```bash
AP_SENTRY_LIVE=1 AP_SENTRY_ORG=… AP_SENTRY_TOKEN=… AP_SENTRY_PROJECT=<slug> AP_SENTRY_RELEASE=<version> pytest tests/live
```
