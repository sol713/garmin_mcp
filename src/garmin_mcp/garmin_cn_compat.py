"""Compatibility fixes for Garmin Connect China authentication.

The pinned garminconnect release still uses international mobile SSO URLs and
does not persist the JWT_WEB fallback session.  Garmin Connect China needs the
regional SSO URLs, and preserving the fallback state lets saved tokens survive
the auth process when DI OAuth is unavailable.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from garminconnect import client as garmin_client


_SERIALIZER_PATCHED = False


def configure_garmin_region(is_cn: bool) -> None:
    """Configure mobile SSO URLs for the selected Garmin account region."""
    if is_cn and sys.version_info < (3, 12):
        raise RuntimeError(
            "Garmin Connect China authentication requires Python 3.12 or newer"
        )

    domain = "garmin.cn" if is_cn else "garmin.com"
    garmin_client.IOS_SERVICE_URL = f"https://mobile.integration.{domain}/gcm/ios"
    garmin_client.MOBILE_SSO_SERVICE_URL = (
        f"https://mobile.integration.{domain}/gcm/android"
    )
    _patch_token_serialization()


def _patch_token_serialization() -> None:
    """Persist JWT_WEB, CSRF, and cookies in addition to DI token fields."""
    global _SERIALIZER_PATCHED
    if _SERIALIZER_PATCHED:
        return

    original_dumps = garmin_client.Client.dumps
    original_loads = garmin_client.Client.loads

    # Avoid patching twice if a future garminconnect release adds these fields.
    probe = garmin_client.Client().dumps()
    if "jwt_web" in json.loads(probe):
        _SERIALIZER_PATCHED = True
        return

    def dumps(client: Any) -> str:
        data = json.loads(original_dumps(client))
        data.update(
            {
                "jwt_web": client.jwt_web,
                "csrf_token": client.csrf_token,
                "cookies": client.cs.cookies.get_dict(),
            }
        )
        return json.dumps(data)

    def loads(client: Any, tokenstore: str) -> None:
        data = json.loads(tokenstore)
        if data.get("di_token"):
            original_loads(client, tokenstore)
        else:
            client.di_token = data.get("di_token")
            client.di_refresh_token = data.get("di_refresh_token")
            client.di_client_id = data.get("di_client_id")

        client.jwt_web = data.get("jwt_web")
        client.csrf_token = data.get("csrf_token")
        client.cs.cookies.update(data.get("cookies") or {})

        if not client.is_authenticated:
            original_loads(client, tokenstore)

    garmin_client.Client.dumps = dumps
    garmin_client.Client.loads = loads
    _SERIALIZER_PATCHED = True
