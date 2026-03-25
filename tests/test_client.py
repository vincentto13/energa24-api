"""Tests for EnergaClient token refresh and re-login behaviour."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from energa.client import EnergaClient
from energa.exceptions import EnergaAuthError


def _make_client() -> EnergaClient:
    client = EnergaClient("user@example.com", "password")
    # Simulate a logged-in state
    client._tokens = {
        "access_token": "old.access.token",
        "refresh_token": "old-refresh-token",
        "expires_in": 300,
    }
    client._token_expires_at = 0.0  # already expired
    client._keycloak_id = "test-user-id"
    client._email = "user@example.com"
    return client


class TestReloginOnRefreshFailure:
    async def test_relogin_on_first_refresh_failure(self):
        """A single refresh failure triggers a transparent re-login."""
        client = _make_client()
        login_mock = AsyncMock()

        with patch.object(client, "_get_session") as mock_session, \
             patch.object(client, "login", login_mock):
            resp = AsyncMock()
            resp.status = 400
            resp.__aenter__ = AsyncMock(return_value=resp)
            resp.__aexit__ = AsyncMock(return_value=False)
            mock_session.return_value.post.return_value = resp

            await client._do_refresh()

        login_mock.assert_awaited_once()
        assert client._relogin_attempts == 1

    async def test_relogin_twice_before_giving_up(self):
        """Two refresh failures trigger two re-logins before raising."""
        client = _make_client()
        login_mock = AsyncMock()

        with patch.object(client, "_get_session") as mock_session, \
             patch.object(client, "login", login_mock):
            resp = AsyncMock()
            resp.status = 400
            resp.__aenter__ = AsyncMock(return_value=resp)
            resp.__aexit__ = AsyncMock(return_value=False)
            mock_session.return_value.post.return_value = resp

            await client._do_refresh()  # attempt 1 → re-login
            assert client._relogin_attempts == 1

            await client._do_refresh()  # attempt 2 → re-login
            assert client._relogin_attempts == 2

        assert login_mock.await_count == 2

    async def test_raises_after_max_relogin_attempts(self):
        """After MAX_RELOGIN_ATTEMPTS re-logins, EnergaAuthError is raised."""
        client = _make_client()
        client._relogin_attempts = client._MAX_RELOGIN_ATTEMPTS

        with patch.object(client, "_get_session") as mock_session:
            resp = AsyncMock()
            resp.status = 400
            resp.__aenter__ = AsyncMock(return_value=resp)
            resp.__aexit__ = AsyncMock(return_value=False)
            mock_session.return_value.post.return_value = resp

            with pytest.raises(EnergaAuthError, match="re-login attempt"):
                await client._do_refresh()

    async def test_counter_resets_on_successful_refresh(self):
        """A successful refresh resets the re-login counter to zero."""
        client = _make_client()
        client._relogin_attempts = 1  # had one failure before

        with patch.object(client, "_get_session") as mock_session, \
             patch.object(client, "_update_kc_token_cookie"):
            resp = AsyncMock()
            resp.status = 200
            resp.json = AsyncMock(return_value={
                "access_token": "new.access.token",
                "refresh_token": "new-refresh-token",
                "expires_in": 300,
            })
            resp.__aenter__ = AsyncMock(return_value=resp)
            resp.__aexit__ = AsyncMock(return_value=False)
            mock_session.return_value.post.return_value = resp
            mock_session.return_value.headers = {}

            await client._do_refresh()

        assert client._relogin_attempts == 0

    async def test_error_message_includes_attempt_count(self):
        """The raised error message mentions the number of attempts."""
        client = _make_client()
        client._relogin_attempts = client._MAX_RELOGIN_ATTEMPTS

        with patch.object(client, "_get_session") as mock_session:
            resp = AsyncMock()
            resp.status = 401
            resp.__aenter__ = AsyncMock(return_value=resp)
            resp.__aexit__ = AsyncMock(return_value=False)
            mock_session.return_value.post.return_value = resp

            with pytest.raises(EnergaAuthError) as exc_info:
                await client._do_refresh()

        assert "2" in str(exc_info.value)
