# energa-api

Python client library for the [24.energa.pl](https://24.energa.pl) self-care portal.
Reverse-engineered from browser traffic. Supports both async and sync usage.

## Features

- Authentication via OIDC Authorization Code + PKCE (Keycloak)
- Native Energa login and OrlenID federated login (shared Orlen Group account)
- Automatic token refresh with transparent re-login on session expiry
- List clients and accounts
- Fetch account balance
- List invoices (with date range and pagination)
- Download invoice PDFs

## Installation

### From PyPI

```bash
pip install energa24-api
```

### From source (with [uv](https://docs.astral.sh/uv/))

```bash
git clone https://github.com/vincentto13/energa24-api.git
cd energa-api
uv sync
```

## Configuration

Set credentials for one (or both) of the following:

| Env vars | Login mode | Notes |
|---|---|---|
| `ORLENID_USERNAME` + `ORLENID_PASSWORD` | OrlenID (`oid-ws.orlen.pl`) | Shared across Orlen Group services. Takes priority if both are set. |
| `ENERGA_USERNAME` + `ENERGA_PASSWORD` | Native 24.energa.pl | Use if you have a standalone Energa account. |

```bash
cp .env.example .env
# edit .env
```

## Usage

### Async

```python
from energa import EnergaClient

# Native Energa credentials (24.energa.pl username/password)
async with EnergaClient("user@example.com", "energa-password") as client:
    ...

# OrlenID credentials (shared Orlen Group account — oid-ws.orlen.pl)
async with EnergaClient("user@example.com", "orlenid-password", use_orlenid=True) as client:
    for account in client.accounts:
        balance = await client.get_balance(account.account_number)
        print(balance.balance, "PLN")

        invoices = await client.get_invoices(account.account_number)
        for inv in invoices:
            print(inv.invoice_number, inv.amount, "PLN")

        # Download a PDF
        pdf = await client.download_invoice(account.account_number, inv.dms_id)
```

### Sync

```python
from energa import EnergaClientSync

with EnergaClientSync("user@example.com", "orlenid-password", use_orlenid=True) as client:
    balance = client.get_balance(account_number)
    invoices = client.get_invoices(account_number)
    pdf = client.download_invoice(account_number, dms_id)
```

## Development

### MCP server — local setup with Claude Code

**1. Install the MCP extra**

```bash
uv sync --extra mcp
```

**2. Export your credentials**

```bash
# OrlenID (recommended — works across all Orlen Group services)
export ORLENID_USERNAME=you@example.com
export ORLENID_PASSWORD=your-orlenid-password

# — or — native Energa credentials
export ENERGA_USERNAME=you@example.com
export ENERGA_PASSWORD=your-energa-password
```

Persist in `~/.bashrc` / `~/.zshrc` so they're always available.

**3. Verify the server starts**

```bash
uv run python -m energa.mcp_server
```

The process should start and wait for MCP input on stdin (no output is normal — that's correct stdio behaviour). Press `Ctrl+C` to stop.

**4. Connect Claude Code**

The repo includes a `.mcp.json` that points Claude Code at the server automatically.
Open Claude Code from this project directory — it will pick up `.mcp.json` and prompt you to approve the server on first use.

Check the connection inside a Claude Code session:

```
/mcp
```

You should see `energa` listed as connected with 4 tools.

### Running the smoke test (live API)

```bash
# OrlenID credentials
ORLENID_USERNAME=you@example.com ORLENID_PASSWORD=orlenid-secret uv run scripts/smoke_test.py

# Native Energa credentials
ENERGA_USERNAME=you@example.com ENERGA_PASSWORD=energa-secret uv run scripts/smoke_test.py
```

Or with a `.env` file:

```bash
uv run --env-file .env scripts/smoke_test.py
```

### Running the test suite

```bash
uv run pytest
```

## MCP Server

The library ships an [MCP](https://modelcontextprotocol.io) server that exposes your Energa account
as tools for Claude and other MCP-compatible AI assistants.

### Install

```bash
pip install energa24-api[mcp]
```

### Available tools

| Tool | Description |
|---|---|
| `list_accounts` | List all accounts and meters (cached, no network request) |
| `get_balance` | Get current balance for an account |
| `get_invoices` | List invoices with optional date range and pagination |
| `download_invoice` | Download a PDF invoice — saves to a temp file and returns the path |

### Run standalone

```bash
# OrlenID credentials
ORLENID_USERNAME=you@example.com ORLENID_PASSWORD=orlenid-secret uv run python -m energa.mcp_server

# Native Energa credentials
ENERGA_USERNAME=you@example.com ENERGA_PASSWORD=energa-secret uv run python -m energa.mcp_server
```

### Claude Desktop configuration

Add to `~/.config/claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "energa": {
      "command": "uv",
      "args": ["run", "--project", "/path/to/energa-api", "python", "-m", "energa.mcp_server"],
      "env": {
        "ORLENID_USERNAME": "you@example.com",
        "ORLENID_PASSWORD": "your-orlenid-password"
      }
    }
  }
}
```

Use `ORLENID_USERNAME`/`ORLENID_PASSWORD` for OrlenID, or `ENERGA_USERNAME`/`ENERGA_PASSWORD` for native Energa. If both are set, OrlenID takes priority.

> **Note:** The access token (5 min) is refreshed automatically. If the refresh token
> expires after 30 minutes of inactivity, the client silently re-logs in (up to 2 attempts)
> before raising an error — no manual restart needed in most cases.

### Example prompts

Ask Claude naturally:

- *"What's my Energa balance?"*
- *"Show me my last 3 invoices"*
- *"List all my electricity accounts and their meter addresses"*
- *"Download the latest invoice for account 1234567890"*
- *"Do I have any unpaid invoices?"*

## Acknowledgements

This library was built with the help of [Claude](https://claude.ai) (Anthropic's AI assistant).
Claude assisted with reverse-engineering the authentication flow from browser HAR captures,
designing the library architecture, implementing the async/sync client, and writing the test suite.
