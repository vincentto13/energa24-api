"""Synchronous wrapper around EnergaClient."""
from __future__ import annotations

import asyncio
from datetime import date
from typing import Any

from .client import EnergaClient
from .models import Account, Balance, Client, Invoice


class EnergaClientSync:
    """Blocking wrapper around :class:`EnergaClient`.

    Runs a dedicated event loop so it works in any synchronous context
    (scripts, Django views, Home Assistant integrations, etc.).

    Usage::

        with EnergaClientSync("user@example.com", "password") as client:
            balance = client.get_balance("1234567890")
            invoices = client.get_invoices("1234567890")
    """

    def __init__(self, username: str, password: str) -> None:
        self._loop = asyncio.new_event_loop()
        self._async = EnergaClient(username, password)
        try:
            self._run(self._async.login())
        except Exception:
            self._loop.close()
            raise

    # ── context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "EnergaClientSync":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ── properties (no I/O — safe to expose directly) ─────────────────────────

    @property
    def clients(self) -> list[Client]:
        return self._async.clients

    @property
    def accounts(self) -> list[Account]:
        return self._async.accounts

    def get_account(self, account_number: str) -> Account:
        return self._async.get_account(account_number)

    # ── API methods ───────────────────────────────────────────────────────────

    def get_balance(self, account_number: str) -> Balance:
        return self._run(self._async.get_balance(account_number))

    def get_invoices(
        self,
        account_number: str,
        *,
        date_from: date | None = None,
        date_to: date | None = None,
        page: int = 0,
        size: int = 10,
    ) -> list[Invoice]:
        return self._run(
            self._async.get_invoices(
                account_number,
                date_from=date_from,
                date_to=date_to,
                page=page,
                size=size,
            )
        )

    def download_invoice(self, account_number: str, dms_id: str) -> bytes:
        return self._run(self._async.download_invoice(account_number, dms_id))

    def close(self) -> None:
        """Close the HTTP session and shut down the event loop."""
        self._run(self._async.close())
        self._loop.close()

    # ── internal ──────────────────────────────────────────────────────────────

    def _run(self, coro: Any) -> Any:
        return self._loop.run_until_complete(coro)
