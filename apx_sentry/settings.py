"""Where a setting comes from, in order: the process environment (`AP_SENTRY_<KEY>`), then the plugin's options on this machine."""

from __future__ import annotations

import os
from typing import Any, Optional

from action_platform.core.service_access import AccessError, Http
from action_platform.plugins.options import FileOptions

from apx_sentry.observe import Sentry

SLUG = "sentry"
URL = "https://sentry.io"


def setting(key: str, options: Any = None) -> Optional[str]:
    found = os.environ.get(f"AP_{SLUG}_{key}".upper())

    if not found:
        found = (options or FileOptions(SLUG)).get(key)

    return str(found) if found else None


def credentials(options: Any = None) -> tuple[str, str, str]:
    """The organization slug, the token and the base url, or an `AccessError` naming what is missing."""
    org, token = setting("org", options), setting("token", options)
    missing = [k for k, v in (("org", org), ("token", token)) if not v]

    if missing:
        names = ", ".join(f"AP_SENTRY_{k.upper()}" for k in missing)
        raise AccessError(f"sentry: set {names} (or the plugin's options)")

    return str(org), str(token), setting("url", options) or URL


def connect(options: Any = None) -> Sentry:
    org, token, url = credentials(options)

    return Sentry(org, Http("sentry", url, {"authorization": f"Bearer {token}"}))
