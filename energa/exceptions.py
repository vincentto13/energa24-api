class EnergaError(Exception):
    """Base exception for all Energa errors."""


class EnergaAuthError(EnergaError):
    """Authentication failed or session expired."""


class EnergaNotFoundError(EnergaError):
    """Requested resource does not exist."""


class EnergaForbiddenError(EnergaError):
    """Access to the resource is denied (e.g. invoice download)."""


class EnergaAPIError(EnergaError):
    """Unexpected API error."""

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code
