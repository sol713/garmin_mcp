"""Regression coverage for regional auth and saved fallback sessions."""

import json

import pytest
from garminconnect import GarminConnectConnectionError, client

from garmin_mcp import garmin_cn_compat
from garmin_mcp.auth_cli import main, verify_tokens


@pytest.fixture(autouse=True)
def restore_international_region():
    yield
    garmin_cn_compat.configure_garmin_region(False)


def test_china_sso_and_di_oauth_use_china_domains():
    garmin_cn_compat.configure_garmin_region(True)
    assert client.IOS_SERVICE_URL == "https://mobile.integration.garmin.cn/gcm/ios"
    assert client.MOBILE_SSO_SERVICE_URL == "https://mobile.integration.garmin.cn/gcm/android"
    cn_client = client.Client(domain="garmin.cn")
    assert cn_client._di_token_url == "https://diauth.garmin.cn/di-oauth2-service/oauth/token"


def test_switching_back_restores_international_sso():
    garmin_cn_compat.configure_garmin_region(True)
    garmin_cn_compat.configure_garmin_region(False)
    assert client.IOS_SERVICE_URL == "https://mobile.integration.garmin.com/gcm/ios"
    assert client.MOBILE_SSO_SERVICE_URL == "https://mobile.integration.garmin.com/gcm/android"


def test_jwt_only_fallback_survives_round_trip():
    garmin_cn_compat.configure_garmin_region(True)
    original = client.Client(domain="garmin.cn")
    original.jwt_web = "test-jwt"
    original.csrf_token = "test-csrf"
    original.cs.cookies.set("JWT_WEB", "test-jwt")
    original.cs.cookies.set("SESSION", "test-session")

    restored = client.Client(domain="garmin.cn")
    restored.loads(original.dumps())
    assert restored.is_authenticated
    assert restored.jwt_web == "test-jwt"
    assert restored.csrf_token == "test-csrf"
    assert restored.cs.cookies.get_dict() == original.cs.cookies.get_dict()


def test_legacy_di_tokens_still_load():
    garmin_cn_compat.configure_garmin_region(True)
    restored = client.Client(domain="garmin.cn")
    restored.loads(json.dumps({"di_token": "test-di", "di_refresh_token": "test-refresh", "di_client_id": "test-client"}))
    assert restored.is_authenticated
    assert restored.di_token == "test-di"
    assert restored.di_refresh_token == "test-refresh"


def test_empty_token_store_is_rejected():
    garmin_cn_compat.configure_garmin_region(True)
    with pytest.raises(GarminConnectConnectionError, match="Missing tokens"):
        client.Client(domain="garmin.cn").loads("{}")


def test_verify_passes_china_region_to_validation(mocker):
    get_info = mocker.patch("garmin_mcp.auth_cli.get_token_info", return_value={"exists": True, "valid": True, "expanded_path": "/test/tokens"})
    assert verify_tokens("/test/tokens", is_cn=True)
    get_info.assert_called_once_with("/test/tokens", is_cn=True)


def test_verify_cli_keeps_china_flag(mocker, monkeypatch):
    monkeypatch.setattr("sys.argv", ["garmin-mcp-auth", "--verify", "--is-cn"])
    monkeypatch.setenv("GARMINTOKENS", "/test/tokens")
    verify = mocker.patch("garmin_mcp.auth_cli.verify_tokens", return_value=True)
    with pytest.raises(SystemExit) as result:
        main()
    assert result.value.code == 0
    verify.assert_called_once_with("/test/tokens", is_cn=True)
