# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.2] - 2026-03-26

### Added
- OrlenID login support: `EnergaClient("email", "pass", use_orlenid=True)` authenticates
  via `oid-ws.orlen.pl` instead of Energa's native login form. Energa Keycloak brokers
  to OrlenID — required for accounts that use OrlenID (Orlen Group) credentials.
- Credential auto-detection in MCP server and smoke test: set `ORLENID_USERNAME` /
  `ORLENID_PASSWORD` for OrlenID login, or `ENERGA_USERNAME` / `ENERGA_PASSWORD` for
  native Energa login. OrlenID takes priority if both are set.

### Fixed
- HAR capture files (`*.har`) added to `.gitignore` — they contain session tokens and credentials.

## [0.2.1] - 2026-03-26

### Fixed
- Transparent re-login on refresh token expiry: when a token refresh fails
  (e.g. after 30 minutes of inactivity), the client now attempts a full
  re-login silently up to 2 times before raising `EnergaAuthError`. The
  counter resets to 0 after any successful refresh, so transient failures
  each get their own two attempts.

## [0.2.0] - 2026-03-25

### Added
- MCP server (`energa.mcp_server`) exposing four tools: `list_accounts`, `get_balance`, `get_invoices`, `download_invoice`
- `mcp` optional dependency group: `pip install energa24-api[mcp]`
- `energa-mcp` script entry point

## [0.1.0] - 2026-03-25

### Added
- Async client (`EnergaClient`) with OIDC Authorization Code + PKCE (S256) login via Keycloak
- Sync wrapper (`EnergaClientSync`) with a dedicated event loop for use in non-async contexts
- Transparent token refresh (access token refreshed 30 s before expiry)
- `get_balance(account_number)` — fetch current account balance
- `get_invoices(account_number, ...)` — list invoices with date range and pagination
- `download_invoice(account_number, dms_id)` — two-step PDF download
- Typed models: `Account`, `Client`, `Balance`, `Invoice`, `PPE`, `Address`
- Exception hierarchy: `EnergaError`, `EnergaAuthError`, `EnergaForbiddenError`, `EnergaNotFoundError`, `EnergaAPIError`
- PEP 561 `py.typed` marker
