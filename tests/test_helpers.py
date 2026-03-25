"""Unit tests for energa._helpers — all pure functions, no I/O."""
from __future__ import annotations

import base64
import hashlib
from datetime import date

import pytest

from energa._helpers import (
    b64_encode_token,
    decode_jwt_payload,
    generate_pkce,
    parse_balance,
    parse_dashboard,
    parse_invoice,
    parse_invoice_list,
)


# ── PKCE ─────────────────────────────────────────────────────────────────────

class TestGeneratePkce:
    def test_returns_two_strings(self):
        verifier, challenge = generate_pkce()
        assert isinstance(verifier, str)
        assert isinstance(challenge, str)

    def test_no_padding(self):
        verifier, challenge = generate_pkce()
        assert "=" not in verifier
        assert "=" not in challenge

    def test_url_safe_alphabet(self):
        for _ in range(10):
            verifier, challenge = generate_pkce()
            assert "+" not in verifier and "/" not in verifier
            assert "+" not in challenge and "/" not in challenge

    def test_challenge_is_s256_of_verifier(self):
        verifier, challenge = generate_pkce()
        digest = hashlib.sha256(verifier.encode()).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
        assert challenge == expected

    def test_unique_each_call(self):
        v1, _ = generate_pkce()
        v2, _ = generate_pkce()
        assert v1 != v2


# ── JWT ───────────────────────────────────────────────────────────────────────

# Minimal valid JWT: header.payload.signature (signature not verified)
_JWT = (
    "eyJhbGciOiJSUzI1NiJ9"
    ".eyJzdWIiOiJ1c2VyLTEyMyIsImVtYWlsIjoidXNlckBleGFtcGxlLmNvbSJ9"
    ".signature"
)


class TestDecodeJwtPayload:
    def test_decodes_sub(self):
        payload = decode_jwt_payload(_JWT)
        assert payload["sub"] == "user-123"

    def test_decodes_email(self):
        payload = decode_jwt_payload(_JWT)
        assert payload["email"] == "user@example.com"


class TestB64EncodeToken:
    def test_roundtrip(self):
        token = "some.jwt.token"
        encoded = b64_encode_token(token)
        decoded = base64.b64decode(encoded).decode()
        assert decoded == token

    def test_returns_str(self):
        assert isinstance(b64_encode_token("x"), str)


# ── parse_dashboard ───────────────────────────────────────────────────────────

class TestParseDashboard:
    def test_returns_clients(self, dashboard_data):
        clients = parse_dashboard(dashboard_data)
        assert len(clients) == 1

    def test_client_fields(self, dashboard_data):
        client = parse_dashboard(dashboard_data)[0]
        assert client.client_number == "9900000001"
        assert client.name == "JAN KOWALSKI"
        assert client.client_type == "INDIVIDUAL"

    def test_account_fields(self, dashboard_data):
        account = parse_dashboard(dashboard_data)[0].accounts[0]
        assert account.account_number == "1234567890"
        assert account.client_number == "9900000001"
        assert account.account_type == "ELECTRICITY"
        assert account.access == "FULL"

    def test_ppe_fields(self, dashboard_data):
        ppe = parse_dashboard(dashboard_data)[0].accounts[0].ppes[0]
        assert ppe.ppe_number == "PL0000000000000000000000000001"
        assert ppe.alias == "Dom"

    def test_ppe_address(self, dashboard_data):
        addr = parse_dashboard(dashboard_data)[0].accounts[0].ppes[0].address
        assert addr is not None
        assert addr.street == "Lipowa"
        assert addr.city == "Gdańsk"
        assert addr.apartment_number == "3"

    def test_empty_sections(self):
        clients = parse_dashboard({"clients": [], "b2bClients": [], "gasClients": []})
        assert clients == []

    def test_missing_sections(self):
        clients = parse_dashboard({})
        assert clients == []


# ── parse_balance ─────────────────────────────────────────────────────────────

class TestParseBalance:
    def test_fields(self, balance_data):
        balance = parse_balance("1234567890", balance_data)
        assert balance.account_number == "1234567890"
        assert balance.balance == -45.50
        assert balance.status == "UNPAID"
        assert balance.max_limit_reached is False


# ── parse_invoice / parse_invoice_list ───────────────────────────────────────

class TestParseInvoice:
    def _raw(self):
        return {
            "documentId": "DOC-001",
            "invoiceNumber": "FV/2025/01/001",
            "documentTitle": "Faktura VAT",
            "issueDate": "2025-01-15",
            "paymentDate": "2025-02-05",
            "invoiceAmount": 120.30,
            "status": "PAID",
            "dmsId": "351461623",
            "accruedInterest": 0.0,
            "buttonStatus": {"shouldShow": True, "validDocument": True},
        }

    def test_basic_fields(self):
        inv = parse_invoice(self._raw())
        assert inv.document_id == "DOC-001"
        assert inv.invoice_number == "FV/2025/01/001"
        assert inv.amount == 120.30
        assert inv.status == "PAID"
        assert inv.dms_id == "351461623"

    def test_dates(self):
        inv = parse_invoice(self._raw())
        assert inv.issue_date == date(2025, 1, 15)
        assert inv.payment_date == date(2025, 2, 5)

    def test_downloadable_true(self):
        assert parse_invoice(self._raw()).downloadable is True

    def test_downloadable_false_no_dms_id(self):
        raw = self._raw()
        raw["dmsId"] = None
        assert parse_invoice(raw).downloadable is False

    def test_downloadable_false_button_hidden(self):
        raw = self._raw()
        raw["buttonStatus"]["shouldShow"] = False
        assert parse_invoice(raw).downloadable is False

    def test_null_payment_date(self):
        raw = self._raw()
        raw["paymentDate"] = None
        assert parse_invoice(raw).payment_date is None


class TestParseInvoiceList:
    def test_from_dict_with_invoices_key(self, invoices_data):
        items = parse_invoice_list(invoices_data)
        assert len(items) == 2

    def test_from_list(self, invoices_data):
        items = parse_invoice_list(invoices_data["invoices"])
        assert len(items) == 2

    def test_first_downloadable(self, invoices_data):
        items = parse_invoice_list(invoices_data)
        assert items[0].downloadable is True
        assert items[1].downloadable is False

    def test_empty_list(self):
        assert parse_invoice_list([]) == []

    def test_empty_dict(self):
        assert parse_invoice_list({}) == []
