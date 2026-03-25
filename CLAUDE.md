# Energa API — Project Context

## What this is
A reverse-engineered Python client library for the **24.energa.pl** self-care portal.
Built by capturing browser HAR files and replicating the login + API flow.

---

## Auth flow (important)

The portal uses **Keycloak** with **OIDC Authorization Code + PKCE (S256)**.

| Parameter | Value |
|---|---|
| Base URL | `https://24.energa.pl` |
| Keycloak realm | `Energa-Selfcare` |
| Client ID | `energa-selfcare` |
| Redirect URI | `https://24.energa.pl/ss/` |
| Response mode | `fragment` (auth code comes back in URL fragment) |
| Access token TTL | 300s (5 min) |
| Refresh token TTL | 1800s (30 min) |

**Login steps:**
1. GET `/auth/realms/Energa-Selfcare/protocol/openid-connect/auth` with PKCE params → Keycloak login page
2. POST credentials to Keycloak form action URL → follow redirects until `redirect_uri#code=...`
3. GET `/ss/` (establishes Next.js session context)
4. POST `/auth/realms/Energa-Selfcare/protocol/openid-connect/token` with `code` + `code_verifier`
5. Set `Authorization: Bearer <access_token>` on all subsequent API calls

**Authenticated API calls** use:
- `Authorization: Bearer <access_token>` header
- `KeycloakId: <sub from JWT>` header
- `X-Client-Type: WEB` header

**Token refresh:** POST to token endpoint with `grant_type=refresh_token`.

---

## Key API endpoints

| Method | Path | Notes |
|---|---|---|
| POST | `/api/dashboard` | Body: `{keycloakId, email}`. Returns clients/accounts. Cache this at login. |
| GET | `/api/clients/{clientNumber}/accounts/{accountNumber}/balance` | Returns balance |
| GET | `/api/clients/{clientNumber}/accounts/{accountNumber}/invoices` | Params: `page`, `size`, `localDateFrom`, `localDateTo` |
| GET | `/api/accounts/{accountNumber}/invoices/file/{dmsId}` | Returns a UUID string (download token) |
| GET | `/api/accounts/{accountNumber}/invoices/file/download/{dmsId}/{uuid}` | Returns PDF bytes. Needs `kcToken` cookie (base64-encoded access token). |

**Invoice download flow** (two steps):
1. GET `.../invoices/file/{dmsId}` → returns UUID
2. GET `.../invoices/file/download/{dmsId}/{uuid}` → PDF bytes
   - Requires `kcToken` cookie = `base64.b64encode(access_token.encode())`
   - Note: some accounts return 403 (server-side restriction, also fails in browser)

---

## Library structure

```
energa/
  __init__.py      # exports: EnergaClient, EnergaClientSync, models, exceptions
  client.py        # async EnergaClient (aiohttp)
  sync.py          # EnergaClientSync — blocking wrapper with own event loop
  models.py        # Address, PPE, Account, Client, Balance, Invoice (dataclasses)
  exceptions.py    # EnergaError, EnergaAuthError, EnergaForbiddenError, EnergaNotFoundError, EnergaAPIError
  _helpers.py      # PKCE generation, JWT decode, response parsers (internal)
  mcp_server.py    # FastMCP server exposing library as MCP tools
  py.typed         # PEP 561 marker
```

**Dependencies:** `aiohttp>=3.9`, optional `mcp>=1.0.0` (managed via `uv`)

---

## Usage

```python
# Async
async with EnergaClient("user@example.com", "password") as client:
    client.accounts          # cached from login, no I/O
    client.clients           # same
    await client.get_balance("1234567890")
    await client.get_invoices("1234567890")
    await client.download_invoice("1234567890", dms_id="000000000")  # → bytes

# Sync
with EnergaClientSync("user@example.com", "password") as client:
    client.get_balance("1234567890")

# MCP server
uv run python -m energa.mcp_server   # reads ENERGA_USERNAME / ENERGA_PASSWORD from env
```

---

## What's done
- [x] Login flow (OIDC + PKCE)
- [x] Dashboard fetch + account caching
- [x] Balance per account
- [x] Invoice list per account (paginated, date range)
- [x] Invoice PDF download (prepare UUID → download)
- [x] Transparent token refresh
- [x] Async client (`EnergaClient`)
- [x] Sync wrapper (`EnergaClientSync`)
- [x] uv-managed virtualenv
- [x] Package published as `energa24-api` on PyPI
- [x] MCP server (`energa/mcp_server.py`) — 4 tools: `list_accounts`, `get_balance`, `get_invoices`, `download_invoice`
- [x] 65 unit tests (no live calls)
- [x] `.mcp.json` for Claude Code integration

## What's next / ideas
- [ ] Consumption chart data (`GET /api/accounts/{account}/ppes/chart`)
- [ ] Notifications (`POST /api/notifications`)
- [ ] Overdue invoice status (`GET /api/accounts/{account}/invoices/overdue-invoice-status`)
- [ ] Bump to v0.2.0 and publish to PyPI

---

## Known quirks
- `/ss/api/server-cookie` (Next.js BFF token storage) returns 500 from scripts — not needed, skip it
- Invoice download 403: some accounts are restricted server-side; same 403 happens in the browser
- The `response_mode=fragment` means the auth code is in the URL fragment — must be extracted manually from the `Location` header (not a query param)
- `CookieJar(unsafe=True)` is intentional — required to set the `kcToken` cookie for invoice downloads (Keycloak sets non-RFC-compliant cookies)

---

## Security notes

These are known trade-offs, not bugs:

- **No JWT signature verification** — `decode_jwt_payload()` decodes without verifying. The token comes directly from Keycloak over TLS; verification would require fetching the public key. Acceptable for a trusted-server client.
- **`CookieJar(unsafe=True)`** — required by the portal's cookie handling. Documented above.
- **Credentials in memory** — `self._username` / `self._password` persist on the `EnergaClient` instance. Required by the sync wrapper's event loop model. Do not log or serialize client objects.
- **Temp files for PDF downloads** — `download_invoice` in the MCP server writes to `tempfile.mkstemp()` (mode 0600, owner-only). Files are not auto-deleted; OS temp cleanup handles them eventually. Users can delete manually.
- **No input validation on API responses** — parsers trust the server response shape. A breaking API change will surface as a `KeyError` or `AttributeError`, not a clean `EnergaAPIError`.
