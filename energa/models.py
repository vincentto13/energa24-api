from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Address:
    street: str
    house_number: str
    zip_code: str
    city: str
    apartment_number: str | None = None

    def __str__(self) -> str:
        apt = f"/{self.apartment_number}" if self.apartment_number else ""
        return f"{self.street} {self.house_number}{apt}, {self.zip_code} {self.city}"


@dataclass
class PPE:
    """Point of Power Exchange — a single meter/delivery point."""
    ppe_number: str
    alias: str | None = None
    address: Address | None = None


@dataclass
class Account:
    account_number: str
    client_number: str
    account_type: str           # "ELECTRICITY" | "GAS"
    access: str                 # "FULL" | "READ_ONLY"
    ppes: list[PPE] = field(default_factory=list)
    alias: str | None = None


@dataclass
class Client:
    client_number: str
    name: str
    client_type: str            # "INDIVIDUAL" | "BUSINESS"
    accounts: list[Account] = field(default_factory=list)


@dataclass
class Balance:
    account_number: str
    balance: float
    status: str
    max_limit_reached: bool


@dataclass
class Invoice:
    document_id: str
    invoice_number: str
    title: str
    issue_date: date
    amount: float
    status: str                 # "PAID" | "UNPAID"
    dms_id: str | None
    downloadable: bool
    payment_date: date | None = None
    accrued_interest: float = 0.0
