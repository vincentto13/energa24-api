"""Unit tests for energa.models dataclasses."""
from __future__ import annotations

from datetime import date

from energa.models import Account, Address, Balance, Client, Invoice, PPE


class TestAddress:
    def test_str_with_apartment(self):
        addr = Address("Lipowa", "12", "80-001", "Gdańsk", apartment_number="3")
        assert str(addr) == "Lipowa 12/3, 80-001 Gdańsk"

    def test_str_without_apartment(self):
        addr = Address("Lipowa", "12", "80-001", "Gdańsk")
        assert str(addr) == "Lipowa 12, 80-001 Gdańsk"


class TestPPE:
    def test_defaults(self):
        ppe = PPE(ppe_number="PL001")
        assert ppe.alias is None
        assert ppe.address is None


class TestAccount:
    def test_defaults(self):
        acc = Account("ACC-1", "CLI-1", "ELECTRICITY", "FULL")
        assert acc.ppes == []
        assert acc.alias is None


class TestClient:
    def test_defaults(self):
        cli = Client("CLI-1", "Jan Kowalski", "INDIVIDUAL")
        assert cli.accounts == []


class TestBalance:
    def test_fields(self):
        bal = Balance("ACC-1", -10.5, "UNPAID", False)
        assert bal.balance == -10.5
        assert bal.max_limit_reached is False


class TestInvoice:
    def test_defaults(self):
        inv = Invoice(
            document_id="D1",
            invoice_number="FV/001",
            title="Faktura",
            issue_date=date(2025, 1, 1),
            amount=100.0,
            status="PAID",
            dms_id="123",
            downloadable=True,
        )
        assert inv.payment_date is None
        assert inv.accrued_interest == 0.0
