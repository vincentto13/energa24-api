"""Internal helpers: PKCE, JWT, response parsing."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from datetime import date

from .models import Account, Address, Balance, Client, Invoice, PPE


# ── PKCE ─────────────────────────────────────────────────────────────────────

def generate_pkce() -> tuple[str, str]:
    """Return (code_verifier, code_challenge) using S256."""
    code_verifier = base64.urlsafe_b64encode(os.urandom(64)).rstrip(b"=").decode()
    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
    return code_verifier, code_challenge


# ── JWT ───────────────────────────────────────────────────────────────────────

def decode_jwt_payload(token: str) -> dict:
    part = token.split(".")[1]
    part += "=" * (4 - len(part) % 4)
    return json.loads(base64.b64decode(part))


def b64_encode_token(token: str) -> str:
    """Base64-encode a JWT string (used for kcToken cookie)."""
    return base64.b64encode(token.encode()).decode()


# ── Response parsers ─────────────────────────────────────────────────────────

def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def _parse_address(data: dict) -> Address:
    return Address(
        street=data.get("streetName", ""),
        house_number=data.get("houseNumber", ""),
        zip_code=data.get("zipCode", ""),
        city=data.get("cityName", ""),
        apartment_number=data.get("apartmentNumber"),
    )


def _parse_ppe(data: dict) -> PPE:
    addr = data.get("meterAddress")
    return PPE(
        ppe_number=data["ppeNumber"],
        alias=data.get("alias"),
        address=_parse_address(addr) if addr else None,
    )


def _parse_account(data: dict) -> Account:
    return Account(
        account_number=data["accountNumber"],
        client_number=data["clientNumber"],
        account_type=data.get("accountType", ""),
        access=data.get("access", ""),
        alias=data.get("alias"),
        ppes=[_parse_ppe(p) for p in data.get("ppes", [])],
    )


def _parse_client(data: dict) -> Client:
    return Client(
        client_number=data["clientNumber"],
        name=data.get("clientName", ""),
        client_type=data.get("clientType", ""),
        accounts=[_parse_account(a) for a in data.get("invoiceProfile", [])],
    )


def parse_dashboard(data: dict) -> list[Client]:
    clients = []
    for section in ("clients", "b2bClients", "gasClients"):
        for raw in data.get(section, []):
            clients.append(_parse_client(raw))
    return clients


def parse_balance(account_number: str, data: dict) -> Balance:
    return Balance(
        account_number=account_number,
        balance=data["balance"],
        status=data["status"],
        max_limit_reached=data["maxLimitReached"],
    )


def parse_invoice(data: dict) -> Invoice:
    btn = data.get("buttonStatus", {})
    downloadable = (
        bool(data.get("dmsId"))
        and btn.get("shouldShow", False)
        and btn.get("validDocument", False)
    )
    return Invoice(
        document_id=data["documentId"],
        invoice_number=data["invoiceNumber"],
        title=data.get("documentTitle", ""),
        issue_date=_parse_date(data.get("issueDate")),
        amount=data.get("invoiceAmount", 0.0),
        status=data.get("status", ""),
        dms_id=data.get("dmsId"),
        downloadable=downloadable,
        payment_date=_parse_date(data.get("paymentDate")),
        accrued_interest=data.get("accruedInterest", 0.0),
    )


def parse_invoice_list(data: list | dict) -> list[Invoice]:
    items = data if isinstance(data, list) else (
        data.get("invoices") or data.get("content") or []
    )
    return [parse_invoice(i) for i in items]
