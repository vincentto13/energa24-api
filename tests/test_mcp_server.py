"""Tests for energa.mcp_server — serialisation helpers and tool handlers."""
from __future__ import annotations

import json
import os
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from energa.exceptions import (
    EnergaAPIError,
    EnergaAuthError,
    EnergaForbiddenError,
    EnergaNotFoundError,
)
from energa.models import Account, Address, Balance, Client, Invoice, PPE
from energa.mcp_server import (
    _account_to_dict,
    _balance_to_dict,
    _client_to_dict,
    _invoice_to_dict,
    download_invoice,
    get_balance,
    get_invoices,
    list_accounts,
)


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_address():
    return Address("Lipowa", "12", "80-001", "Gdańsk", apartment_number="3")


@pytest.fixture
def sample_ppe(sample_address):
    return PPE(ppe_number="PL001", alias="Dom", address=sample_address)


@pytest.fixture
def sample_account(sample_ppe):
    return Account(
        account_number="1234567890",
        client_number="9900000001",
        account_type="ELECTRICITY",
        access="FULL",
        ppes=[sample_ppe],
        alias="Mieszkanie",
    )


@pytest.fixture
def sample_client(sample_account):
    return Client(
        client_number="9900000001",
        name="Jan Kowalski",
        client_type="INDIVIDUAL",
        accounts=[sample_account],
    )


@pytest.fixture
def sample_balance():
    return Balance("1234567890", -45.50, "UNPAID", False)


@pytest.fixture
def sample_invoice():
    return Invoice(
        document_id="DOC-001",
        invoice_number="FV/2025/01/001",
        title="Faktura VAT",
        issue_date=date(2025, 1, 15),
        payment_date=date(2025, 2, 5),
        amount=120.30,
        status="PAID",
        dms_id="351461623",
        downloadable=True,
    )


@pytest.fixture
def mock_client(sample_client, sample_balance, sample_invoice):
    """A mock EnergaClient pre-configured with sample data."""
    client = MagicMock()
    client.clients = [sample_client]
    client.accounts = sample_client.accounts
    client.get_balance = AsyncMock(return_value=sample_balance)
    client.get_invoices = AsyncMock(return_value=[sample_invoice])
    client.download_invoice = AsyncMock(return_value=b"%PDF-1.4 fake content")
    return client


# ── serialisation helpers ─────────────────────────────────────────────────────

class TestAccountToDict:
    def test_required_fields(self, sample_account):
        d = _account_to_dict(sample_account)
        assert d["account_number"] == "1234567890"
        assert d["client_number"] == "9900000001"
        assert d["account_type"] == "ELECTRICITY"
        assert d["access"] == "FULL"
        assert d["alias"] == "Mieszkanie"

    def test_ppe_included(self, sample_account):
        ppes = _account_to_dict(sample_account)["ppes"]
        assert len(ppes) == 1
        assert ppes[0]["ppe_number"] == "PL001"
        assert ppes[0]["alias"] == "Dom"

    def test_ppe_address(self, sample_account):
        addr = _account_to_dict(sample_account)["ppes"][0]["address"]
        assert addr["street"] == "Lipowa"
        assert addr["city"] == "Gdańsk"
        assert addr["apartment_number"] == "3"

    def test_ppe_without_address(self):
        acc = Account("A1", "C1", "ELECTRICITY", "FULL", ppes=[PPE("PL001")])
        d = _account_to_dict(acc)
        assert "address" not in d["ppes"][0]


class TestClientToDict:
    def test_fields(self, sample_client):
        d = _client_to_dict(sample_client)
        assert d["client_number"] == "9900000001"
        assert d["name"] == "Jan Kowalski"
        assert d["client_type"] == "INDIVIDUAL"
        assert len(d["accounts"]) == 1


class TestBalanceToDict:
    def test_fields(self, sample_balance):
        d = _balance_to_dict(sample_balance)
        assert d["account_number"] == "1234567890"
        assert d["balance"] == -45.50
        assert d["status"] == "UNPAID"
        assert d["max_limit_reached"] is False


class TestInvoiceToDict:
    def test_fields(self, sample_invoice):
        d = _invoice_to_dict(sample_invoice)
        assert d["invoice_number"] == "FV/2025/01/001"
        assert d["amount"] == 120.30
        assert d["status"] == "PAID"
        assert d["dms_id"] == "351461623"
        assert d["downloadable"] is True

    def test_dates_as_iso(self, sample_invoice):
        d = _invoice_to_dict(sample_invoice)
        assert d["issue_date"] == "2025-01-15"
        assert d["payment_date"] == "2025-02-05"

    def test_null_payment_date(self, sample_invoice):
        sample_invoice.payment_date = None
        assert _invoice_to_dict(sample_invoice)["payment_date"] is None

    def test_not_downloadable(self, sample_invoice):
        sample_invoice.downloadable = False
        assert _invoice_to_dict(sample_invoice)["downloadable"] is False


# ── tool: list_accounts ───────────────────────────────────────────────────────

class TestListAccounts:
    def test_returns_json_array(self, mock_client):
        with patch("energa.mcp_server._client", mock_client):
            result = list_accounts()
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) == 1

    def test_account_fields_present(self, mock_client):
        with patch("energa.mcp_server._client", mock_client):
            result = list_accounts()
        account = json.loads(result)[0]["accounts"][0]
        assert account["account_number"] == "1234567890"

    def test_auth_error_raises_value_error(self, mock_client):
        mock_client.clients = property(lambda self: (_ for _ in ()).throw(
            EnergaAuthError("session expired")
        ))
        # Use a simpler approach: raise on attribute access
        type(mock_client).clients = property(
            lambda self: (_ for _ in ()).throw(EnergaAuthError("expired"))
        )
        with patch("energa.mcp_server._client", mock_client):
            with pytest.raises((ValueError, EnergaAuthError)):
                list_accounts()


# ── tool: get_balance ─────────────────────────────────────────────────────────

class TestGetBalance:
    async def test_returns_json(self, mock_client):
        with patch("energa.mcp_server._client", mock_client):
            result = await get_balance("1234567890")
        data = json.loads(result)
        assert data["balance"] == -45.50
        assert data["status"] == "UNPAID"

    async def test_unknown_account_raises(self, mock_client):
        mock_client.get_balance = AsyncMock(side_effect=KeyError("not found"))
        with patch("energa.mcp_server._client", mock_client):
            with pytest.raises(ValueError, match="not found"):
                await get_balance("9999999999")

    async def test_auth_error_raises(self, mock_client):
        mock_client.get_balance = AsyncMock(side_effect=EnergaAuthError("expired"))
        with patch("energa.mcp_server._client", mock_client):
            with pytest.raises(ValueError, match="Authentication error"):
                await get_balance("1234567890")

    async def test_api_error_raises(self, mock_client):
        mock_client.get_balance = AsyncMock(side_effect=EnergaAPIError("server error", 500))
        with patch("energa.mcp_server._client", mock_client):
            with pytest.raises(ValueError, match="500"):
                await get_balance("1234567890")


# ── tool: get_invoices ────────────────────────────────────────────────────────

class TestGetInvoices:
    async def test_returns_json_array(self, mock_client):
        with patch("energa.mcp_server._client", mock_client):
            result = await get_invoices("1234567890")
        data = json.loads(result)
        assert len(data) == 1
        assert data[0]["invoice_number"] == "FV/2025/01/001"

    async def test_passes_dates_to_client(self, mock_client):
        with patch("energa.mcp_server._client", mock_client):
            await get_invoices("1234567890", date_from="2025-01-01", date_to="2025-06-30")
        mock_client.get_invoices.assert_awaited_once_with(
            "1234567890",
            date_from=date(2025, 1, 1),
            date_to=date(2025, 6, 30),
            page=0,
            size=10,
        )

    async def test_none_dates_passed_through(self, mock_client):
        with patch("energa.mcp_server._client", mock_client):
            await get_invoices("1234567890")
        mock_client.get_invoices.assert_awaited_once_with(
            "1234567890", date_from=None, date_to=None, page=0, size=10
        )

    async def test_invalid_date_raises(self, mock_client):
        with patch("energa.mcp_server._client", mock_client):
            with pytest.raises(ValueError, match="Invalid date"):
                await get_invoices("1234567890", date_from="not-a-date")

    async def test_downloadable_flag_preserved(self, mock_client):
        with patch("energa.mcp_server._client", mock_client):
            result = await get_invoices("1234567890")
        assert json.loads(result)[0]["downloadable"] is True


# ── tool: download_invoice ────────────────────────────────────────────────────

class TestDownloadInvoice:
    async def test_saves_file_and_returns_path(self, mock_client):
        with patch("energa.mcp_server._client", mock_client):
            result = await download_invoice("1234567890", "351461623")
        data = json.loads(result)
        assert os.path.exists(data["path"])
        assert data["size_bytes"] == len(b"%PDF-1.4 fake content")
        assert data["dms_id"] == "351461623"
        # cleanup
        os.unlink(data["path"])

    async def test_file_contains_pdf_bytes(self, mock_client):
        with patch("energa.mcp_server._client", mock_client):
            result = await download_invoice("1234567890", "351461623")
        path = json.loads(result)["path"]
        assert open(path, "rb").read() == b"%PDF-1.4 fake content"
        os.unlink(path)

    async def test_forbidden_raises_value_error(self, mock_client):
        mock_client.download_invoice = AsyncMock(
            side_effect=EnergaForbiddenError("denied")
        )
        with patch("energa.mcp_server._client", mock_client):
            with pytest.raises(ValueError, match="denied access"):
                await download_invoice("1234567890", "351461623")

    async def test_not_found_raises_value_error(self, mock_client):
        mock_client.download_invoice = AsyncMock(
            side_effect=EnergaNotFoundError("not found")
        )
        with patch("energa.mcp_server._client", mock_client):
            with pytest.raises(ValueError, match="not found"):
                await download_invoice("1234567890", "351461623")

    async def test_auth_error_raises(self, mock_client):
        mock_client.download_invoice = AsyncMock(
            side_effect=EnergaAuthError("expired")
        )
        with patch("energa.mcp_server._client", mock_client):
            with pytest.raises(ValueError, match="Authentication error"):
                await download_invoice("1234567890", "351461623")
