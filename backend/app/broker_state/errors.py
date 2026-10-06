"""Broker account read-path error codes and exceptions."""

from __future__ import annotations


AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
RATE_LIMITED = "RATE_LIMITED"
BROKER_UNAVAILABLE = "BROKER_UNAVAILABLE"
NETWORK_TIMEOUT = "NETWORK_TIMEOUT"
MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
PAPER_ACCOUNT_NOT_VERIFIED = "PAPER_ACCOUNT_NOT_VERIFIED"
LIVE_BROKER_ACCESS_FORBIDDEN = "LIVE_BROKER_ACCESS_FORBIDDEN"
ACCOUNT_UNAVAILABLE = "ACCOUNT_UNAVAILABLE"
ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"


class BrokerStateError(Exception):
    """Read-path failure with a stable reason code."""

    def __init__(self, message: str, *, code: str) -> None:
        self.message = message
        self.code = code
        super().__init__(message)
