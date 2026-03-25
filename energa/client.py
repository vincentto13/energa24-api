"""Async Energa API client."""
from __future__ import annotations

import re
import secrets
import time
from datetime import date, timedelta
from typing import Any
from urllib.parse import parse_qs, urldefrag

import aiohttp
from yarl import URL

from .exceptions import (
    EnergaAPIError,
    EnergaAuthError,
    EnergaForbiddenError,
    EnergaNotFoundError,
)
from ._helpers import (
    b64_encode_token,
    decode_jwt_payload,
    generate_pkce,
    parse_balance,
    parse_dashboard,
    parse_invoice_list,
)
from .models import Account, Balance, Client, Invoice


_BASE_URL = "https://24.energa.pl"
_REALM = "Energa-Selfcare"
_CLIENT_ID = "energa-selfcare"
_REDIRECT_URI = f"{_BASE_URL}/ss/"
_AUTH_URL = f"{_BASE_URL}/auth/realms/{_REALM}/protocol/openid-connect/auth"
_TOKEN_URL = f"{_BASE_URL}/auth/realms/{_REALM}/protocol/openid-connect/token"


class EnergaClient:
    """Async client for the Energa self-care portal API.

    Usage::

        async with EnergaClient("user@example.com", "password") as client:
            for account in client.accounts:
                balance = await client.get_balance(account.account_number)
                invoices = await client.get_invoices(account.account_number)
    """

    def __init__(self, username: str, password: str) -> None:
        self._username = username
        self._password = password
        self._session: aiohttp.ClientSession | None = None
        self._tokens: dict | None = None
        self._token_expires_at: float = 0.0
        self._keycloak_id: str = ""
        self._email: str = ""
        self._clients: list[Client] = []

    # ── context manager ───────────────────────────────────────────────────────

    async def __aenter__(self) -> "EnergaClient":
        await self.login()
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    # ── public properties ─────────────────────────────────────────────────────

    @property
    def clients(self) -> list[Client]:
        """All clients populated after login()."""
        if not self._clients:
            raise EnergaAuthError("Not logged in — call login() first.")
        return self._clients

    @property
    def accounts(self) -> list[Account]:
        """Flat list of all accounts across all clients."""
        return [acc for client in self.clients for acc in client.accounts]

    def get_account(self, account_number: str) -> Account:
        """Look up an account by number. Raises KeyError if not found."""
        for acc in self.accounts:
            if acc.account_number == account_number:
                return acc
        raise KeyError(f"Account {account_number!r} not found.")

    # ── auth ──────────────────────────────────────────────────────────────────

    async def login(self) -> None:
        """Authenticate and cache account data.  Safe to call multiple times."""
        session = self._get_session()

        code_verifier, code_challenge = generate_pkce()
        state = secrets.token_urlsafe(16)
        nonce = secrets.token_urlsafe(16)

        # 1. Fetch Keycloak login page
        async with session.get(
            _AUTH_URL,
            params={
                "client_id": _CLIENT_ID,
                "redirect_uri": _REDIRECT_URI,
                "response_type": "code",
                "response_mode": "fragment",
                "scope": "openid",
                "state": state,
                "nonce": nonce,
                "code_challenge": code_challenge,
                "code_challenge_method": "S256",
            },
        ) as resp:
            html = await resp.text()

        match = re.search(r'action="([^"]+)"', html)
        if not match:
            raise EnergaAuthError("Could not find login form — site may have changed.")
        form_action = match.group(1).replace("&amp;", "&")

        # 2. Submit credentials, follow redirects until we reach redirect_uri
        resp = await session.post(
            form_action,
            data={"username": self._username, "password": self._password},
            allow_redirects=False,
        )

        auth_code: str | None = None
        for _ in range(10):
            location = resp.headers.get("Location", "")
            await resp.release()

            if location.startswith(_REDIRECT_URI):
                _, fragment = urldefrag(location)
                auth_code = parse_qs(fragment).get("code", [None])[0]
                break

            if not location:
                raise EnergaAuthError("Login failed — check username and password.")

            resp = await session.get(location, allow_redirects=False)

        if not auth_code:
            raise EnergaAuthError("Could not extract authorization code.")

        # 3. Touch redirect URI (establishes Next.js session)
        async with session.get(_REDIRECT_URI) as resp:
            await resp.read()

        # 4. Exchange code for tokens
        async with session.post(
            _TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": _CLIENT_ID,
                "code": auth_code,
                "redirect_uri": _REDIRECT_URI,
                "code_verifier": code_verifier,
            },
            headers={"Accept": "application/json"},
        ) as resp:
            if resp.status != 200:
                raise EnergaAuthError(f"Token exchange failed ({resp.status}).")
            self._tokens = await resp.json()

        self._token_expires_at = time.monotonic() + self._tokens["expires_in"]

        payload = decode_jwt_payload(self._tokens["access_token"])
        self._keycloak_id = payload["sub"]
        self._email = payload["email"]

        session.headers.update({"Authorization": f"Bearer {self._tokens['access_token']}"})
        self._update_kc_token_cookie()

        # 5. Populate cache
        await self._fetch_dashboard()

    async def close(self) -> None:
        """Close the underlying HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()

    # ── API methods ───────────────────────────────────────────────────────────

    async def get_balance(self, account_number: str) -> Balance:
        """Fetch the current balance for an account."""
        account = self.get_account(account_number)
        data = await self._get_json(
            f"/api/clients/{account.client_number}/accounts/{account_number}/balance"
        )
        return parse_balance(account_number, data)

    async def get_invoices(
        self,
        account_number: str,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 0,
        size: int = 10,
    ) -> list[Invoice]:
        """Fetch invoices for an account.

        Defaults to the last 6 months when date range is omitted.
        """
        today = date.today()
        date_to = date_to or today
        date_from = date_from or (today - timedelta(days=180))

        account = self.get_account(account_number)
        data = await self._get_json(
            f"/api/clients/{account.client_number}/accounts/{account_number}/invoices",
            params={
                "page": page,
                "size": size,
                "localDateFrom": date_from.isoformat(),
                "localDateTo": date_to.isoformat(),
            },
        )
        return parse_invoice_list(data)

    async def download_invoice(self, account_number: str, dms_id: str) -> bytes:
        """Download an invoice PDF. Returns raw bytes.

        Raises EnergaForbiddenError if the server denies the download.
        """
        await self._ensure_fresh_token()
        self._update_kc_token_cookie()

        # Step 1: obtain a server-generated download UUID
        uuid_text = await self._get_text(
            f"/api/accounts/{account_number}/invoices/file/{dms_id}"
        )
        download_uuid = uuid_text.strip().strip('"')

        # Step 2: download the PDF
        return await self._get_bytes(
            f"/api/accounts/{account_number}/invoices/file/download/{dms_id}/{download_uuid}"
        )

    # ── internals ─────────────────────────────────────────────────────────────

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                cookie_jar=aiohttp.CookieJar(unsafe=True),
                headers={"User-Agent": "Mozilla/5.0"},
            )
        return self._session

    def _api_headers(self) -> dict[str, str]:
        return {
            "KeycloakId": self._keycloak_id,
            "X-Client-Type": "WEB",
        }

    def _update_kc_token_cookie(self) -> None:
        if self._tokens:
            encoded = b64_encode_token(self._tokens["access_token"])
            self._get_session().cookie_jar.update_cookies(
                {"kcToken": encoded}, URL(_BASE_URL)
            )

    async def _ensure_fresh_token(self) -> None:
        if self._tokens is None:
            raise EnergaAuthError("Not logged in — call login() first.")
        if time.monotonic() >= self._token_expires_at - 30:
            await self._do_refresh()

    async def _do_refresh(self) -> None:
        session = self._get_session()
        async with session.post(
            _TOKEN_URL,
            data={
                "grant_type": "refresh_token",
                "client_id": _CLIENT_ID,
                "refresh_token": self._tokens["refresh_token"],
            },
            headers={"Accept": "application/json"},
        ) as resp:
            if resp.status != 200:
                raise EnergaAuthError("Token refresh failed — please log in again.")
            self._tokens = await resp.json()

        self._token_expires_at = time.monotonic() + self._tokens["expires_in"]
        session.headers.update({"Authorization": f"Bearer {self._tokens['access_token']}"})
        self._update_kc_token_cookie()

    def _check_status(self, resp: aiohttp.ClientResponse, path: str) -> None:
        if resp.status == 401:
            raise EnergaAuthError(f"Unauthorized: {path}")
        if resp.status == 403:
            raise EnergaForbiddenError(f"Access denied: {path}")
        if resp.status == 404:
            raise EnergaNotFoundError(f"Not found: {path}")
        if not resp.ok:
            raise EnergaAPIError(f"API error {resp.status}: {path}", resp.status)

    async def _get_json(self, path: str, **kwargs: Any) -> Any:
        await self._ensure_fresh_token()
        async with self._get_session().get(
            f"{_BASE_URL}{path}",
            headers=self._api_headers(),
            **kwargs,
        ) as resp:
            self._check_status(resp, path)
            return await resp.json()

    async def _get_text(self, path: str, **kwargs: Any) -> str:
        await self._ensure_fresh_token()
        async with self._get_session().get(
            f"{_BASE_URL}{path}",
            headers=self._api_headers(),
            **kwargs,
        ) as resp:
            self._check_status(resp, path)
            return await resp.text()

    async def _get_bytes(self, path: str, **kwargs: Any) -> bytes:
        await self._ensure_fresh_token()
        async with self._get_session().get(
            f"{_BASE_URL}{path}",
            headers=self._api_headers(),
            **kwargs,
        ) as resp:
            self._check_status(resp, path)
            return await resp.read()

    async def _post_json(self, path: str, body: Any, **kwargs: Any) -> Any:
        await self._ensure_fresh_token()
        async with self._get_session().post(
            f"{_BASE_URL}{path}",
            json=body,
            headers=self._api_headers(),
            **kwargs,
        ) as resp:
            self._check_status(resp, path)
            return await resp.json()

    async def _fetch_dashboard(self) -> None:
        data = await self._post_json(
            "/api/dashboard",
            {"keycloakId": self._keycloak_id, "email": self._email},
        )
        self._clients = parse_dashboard(data)
