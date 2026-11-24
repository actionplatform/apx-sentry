"""The plugin: access on a Sentry organization, `sentry_*` tools and `action-platform sentry` commands."""

from __future__ import annotations

from typing import Any, Optional

from action_platform.abc import Option, Plugin, Surface

try:
    from action_platform.abc import Connection
except ImportError:
    Connection = None
from action_platform.core.service_access import AccessError, AccessProvider

from apx_sentry import cli
from apx_sentry.access import SCOPES, SentryProvider
from apx_sentry.settings import URL
from apx_sentry.tools import register_tools


class SentryPlugin(Plugin):
    slug = "sentry"
    name = "Sentry"
    description = (
        "Manage who belongs to a Sentry organization and its teams; "
        "read a release's new issues and the errors after a deploy"
    )
    min_core = "0.33"
    needs = [
        "env: AP_SENTRY_ORG, AP_SENTRY_TOKEN, AP_SENTRY_URL on a machine (the plugin's options on the platform)",
        "net: sentry.io, or the self-hosted Sentry's url",
        "connection: the organization's Sentry connection on a hosted platform (core 0.34)",
    ]
    connections = (
        [
            Connection(
                "sentry", SCOPES, (), "manage members and teams of the organization"
            )
        ]
        if Connection
        else []
    )
    options = [
        Option(
            "org",
            "Organization slug",
            "text",
            help="The organization's slug in Sentry, as in sentry.io/organizations/<slug>/. Access is off while it is empty.",
        ),
        Option(
            "token",
            "Token",
            "secret",
            help="Optional on a platform with Settings → Services → Connect Sentry. Otherwise a personal or internal integration token: member:admin, team:write, org:read to change access; project:read, event:read for the issue tools.",
        ),
        Option(
            "url",
            "Sentry URL",
            "url",
            help=f"Only for a self-hosted Sentry. Empty means {URL}.",
        ),
    ]

    def register(self, surface: Surface) -> None:
        if surface.mcp is not None:
            register_tools(surface.mcp, surface.options)

        if surface.cli is not None:
            cli.options = surface.options
            surface.cli.add_typer(cli.app, name="sentry")

    def access(self, options: Any) -> Optional[AccessProvider]:
        org = options.get("org")

        if not org:
            return None

        token = options.get("token")
        url = options.get("url") or URL

        if token:
            return SentryProvider(str(org), str(token), url)

        credential = getattr(options, "credential", None)
        found = credential("sentry") if credential else None

        if found is None:
            raise AccessError(
                "sentry: connect Sentry under Settings → Services (or set the plugin's token option)"
            )

        missing = [
            s for s in SCOPES if found.scopes is not None and s not in found.scopes
        ]

        if missing:
            raise AccessError(
                f"sentry: the Sentry connection lacks {', '.join(missing)}; reconnect Sentry under Settings → Services, which asks for it"
            )

        return SentryProvider(
            str(org),
            found.token,
            (found.api_url or "").removesuffix("/api/0") or url,
        )
