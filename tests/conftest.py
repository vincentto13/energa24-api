"""Shared pytest fixtures."""
from __future__ import annotations

import json
import pathlib

import pytest

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def load(name: str) -> dict | list:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def dashboard_data() -> dict:
    return load("dashboard.json")


@pytest.fixture
def balance_data() -> dict:
    return load("balance.json")


@pytest.fixture
def invoices_data() -> dict:
    return load("invoices.json")


@pytest.fixture
def token_data() -> dict:
    return load("token_response.json")
