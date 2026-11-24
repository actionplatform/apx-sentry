"""The plugin: access on a Sentry organization, `sentry_*` tools and `action-platform sentry` commands."""

from __future__ import annotations

from typing import Any, Optional

from action_platform.abc import Option, Plugin, Surface
from action_platform.core.service_access import AccessError, AccessProvider

from apx_sentry import cli
from apx_sentry.access import SentryProvider
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
    ]
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
            help="A personal or internal integration token. To read access: member:read, team:read, org:read. To change it: member:admin, team:write, org:read. For the issue tools: project:read, event:read.",
            required=True,
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

        if not token:
            raise AccessError("sentry: set the plugin's token option to read access")

        return SentryProvider(str(org), str(token), options.get("url") or URL)
