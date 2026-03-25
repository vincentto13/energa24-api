"""Unit tests for energa.exceptions hierarchy."""
from __future__ import annotations

import pytest

from energa.exceptions import (
    EnergaAPIError,
    EnergaAuthError,
    EnergaError,
    EnergaForbiddenError,
    EnergaNotFoundError,
)


def test_hierarchy():
    assert issubclass(EnergaAuthError, EnergaError)
    assert issubclass(EnergaForbiddenError, EnergaError)
    assert issubclass(EnergaNotFoundError, EnergaError)
    assert issubclass(EnergaAPIError, EnergaError)


def test_api_error_stores_status_code():
    err = EnergaAPIError("server error", 500)
    assert err.status_code == 500
    assert "server error" in str(err)


def test_all_catchable_as_base():
    for cls in (EnergaAuthError, EnergaForbiddenError, EnergaNotFoundError):
        with pytest.raises(EnergaError):
            raise cls("test")


