"""MCP server exposing Energa self-care portal as tools.

Run with:
    uv run python -m energa.mcp_server
    energa-mcp                           # after pip install energa24-api[mcp]

Required environment variables:
    ENERGA_USERNAME   — your 24.energa.pl login e-mail
    ENERGA_PASSWORD   — your 24.energa.pl password
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from contextlib import asynccontextmanager
from datetime import date
from typing import Any, AsyncIterator

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    sys.exit(
        "The 'mcp' package is required to run the MCP server.\n"
        "Install it with:  pip install energa24-api[mcp]"
    )

from .client import EnergaClient
from .exceptions import (
    EnergaAPIError,
    EnergaAuthError,
    EnergaForbiddenError,
    EnergaNotFoundError,
)
from .models import Account, Balance, Client, Invoice


# ── serialisation helpers (also unit-tested independently) ───────────────────

def _account_to_dict(acc: Account) -> dict[str, Any]:
    ppes = []
    for p in acc.ppes:
        ppe: dict[str, Any] = {"ppe_number": p.ppe_number, "alias": p.alias}
        if p.address:
            ppe["address"] = {
                "street": p.address.street,
                "house_number": p.address.house_number,
                "apartment_number": p.address.apartment_number,
                "zip_code": p.address.zip_code,
                "city": p.address.city,
            }
        ppes.append(ppe)
    return {
        "account_number": acc.account_number,
        "client_number": acc.client_number,
        "account_type": acc.account_type,
        "access": acc.access,
        "alias": acc.alias,
        "ppes": ppes,
    }


def _client_to_dict(c: Client) -> dict[str, Any]:
    return {
        "client_number": c.client_number,
        "name": c.name,
        "client_type": c.client_type,
        "accounts": [_account_to_dict(a) for a in c.accounts],
    }


def _balance_to_dict(b: Balance) -> dict[str, Any]:
    return {
        "account_number": b.account_number,
        "balance": b.balance,
        "status": b.status,
        "max_limit_reached": b.max_limit_reached,
    }


def _invoice_to_dict(inv: Invoice) -> dict[str, Any]:
    return {
        "document_id": inv.document_id,
        "invoice_number": inv.invoice_number,
        "title": inv.title,
        "issue_date": inv.issue_date.isoformat(),
        "payment_date": inv.payment_date.isoformat() if inv.payment_date else None,
        "amount": inv.amount,
        "status": inv.status,
        "dms_id": inv.dms_id,
        "downloadable": inv.downloadable,
        "accrued_interest": inv.accrued_interest,
    }


# ── lifespan: single shared client ───────────────────────────────────────────

_client: EnergaClient | None = None


@asynccontextmanager
async def lifespan(_app: Any) -> AsyncIterator[None]:
    global _client
    username = os.environ.get("ENERGA_USERNAME", "")
    password = os.environ.get("ENERGA_PASSWORD", "")
    if not username or not password:
        sys.exit(
            "ENERGA_USERNAME and ENERGA_PASSWORD environment variables must be set."
        )
    _client = EnergaClient(username, password)
    await _client.login()
    try:
        yield
    finally:
        await _client.close()
        _client = None


mcp = FastMCP("Energa", lifespan=lifespan)


def _get_client() -> EnergaClient:
    if _client is None:
        raise RuntimeError("Client not initialised.")
    return _client


# ── tools ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def list_accounts() -> str:
    """List all electricity accounts associated with the logged-in user.

    Returns a JSON array of account objects. Each object includes the account
    number, type, access level, optional alias, and a list of PPEs (meters)
    with their addresses. No network request is made — data is cached at login.
    """
    try:
        clients = _get_client().clients
        return json.dumps([_client_to_dict(c) for c in clients], ensure_ascii=False)
    except EnergaAuthError as e:
        raise ValueError(f"Authentication error: {e}. Restart the MCP server.") from e


@mcp.tool()
async def get_balance(account_number: str) -> str:
    """Get the current balance for an electricity account.

    Args:
        account_number: The account number (visible in list_accounts).

    Returns JSON with balance (PLN), status, and whether the max limit is reached.
    A negative balance means the account is in credit (overpayment).
    """
    client = _get_client()
    try:
        balance = await client.get_balance(account_number)
        return json.dumps(_balance_to_dict(balance))
    except KeyError:
        raise ValueError(
            f"Account '{account_number}' not found. Use list_accounts to see available accounts."
        )
    except EnergaAuthError as e:
        raise ValueError(f"Authentication error: {e}. Restart the MCP server.") from e
    except EnergaAPIError as e:
        raise ValueError(f"Energa API error (HTTP {e.status_code}): {e}") from e


@mcp.tool()
async def get_invoices(
    account_number: str,
    date_from: str | None = None,
    date_to: str | None = None,
    page: int = 0,
    size: int = 10,
) -> str:
    """List invoices for an electricity account.

    Args:
        account_number: The account number (visible in list_accounts).
        date_from:      Start of date range in ISO 8601 format (YYYY-MM-DD).
                        Defaults to 180 days ago.
        date_to:        End of date range in ISO 8601 format (YYYY-MM-DD).
                        Defaults to today.
        page:           Zero-based page number (default 0).
        size:           Number of invoices per page (default 10).

    Returns a JSON array of invoice objects. Each invoice includes the invoice
    number, amount (PLN), status, issue date, and a 'downloadable' flag
    indicating whether download_invoice can be called for it.
    """
    client = _get_client()
    try:
        parsed_from = date.fromisoformat(date_from) if date_from else None
        parsed_to = date.fromisoformat(date_to) if date_to else None
    except ValueError as e:
        raise ValueError(f"Invalid date format: {e}. Use YYYY-MM-DD.") from e

    try:
        invoices = await client.get_invoices(
            account_number,
            date_from=parsed_from,
            date_to=parsed_to,
            page=page,
            size=size,
        )
        return json.dumps([_invoice_to_dict(i) for i in invoices], ensure_ascii=False)
    except KeyError:
        raise ValueError(
            f"Account '{account_number}' not found. Use list_accounts to see available accounts."
        )
    except EnergaAuthError as e:
        raise ValueError(f"Authentication error: {e}. Restart the MCP server.") from e
    except EnergaAPIError as e:
        raise ValueError(f"Energa API error (HTTP {e.status_code}): {e}") from e


@mcp.tool()
async def download_invoice(account_number: str, dms_id: str) -> str:
    """Download an invoice PDF and save it to a temporary file.

    Only call this for invoices where downloadable=true (from get_invoices).

    Args:
        account_number: The account number the invoice belongs to.
        dms_id:         The dms_id field from the invoice (from get_invoices).

    Returns JSON with the absolute file path, file size in bytes, and dms_id.
    The file is saved to the system temp directory and will persist until
    the OS cleans up temp files.
    """
    client = _get_client()
    try:
        pdf_bytes = await client.download_invoice(account_number, dms_id)
    except EnergaForbiddenError as e:
        raise ValueError(
            f"The server denied access to invoice {dms_id}. "
            "This restriction also applies in the browser and cannot be bypassed."
        ) from e
    except EnergaNotFoundError as e:
        raise ValueError(f"Invoice {dms_id} not found for account {account_number}.") from e
    except EnergaAuthError as e:
        raise ValueError(f"Authentication error: {e}. Restart the MCP server.") from e
    except EnergaAPIError as e:
        raise ValueError(f"Energa API error (HTTP {e.status_code}): {e}") from e

    fd, path = tempfile.mkstemp(suffix=".pdf", prefix=f"energa_{dms_id}_")
    try:
        os.write(fd, pdf_bytes)
    finally:
        os.close(fd)

    return json.dumps({"path": path, "size_bytes": len(pdf_bytes), "dms_id": dms_id})


# ── entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
