"""Market Memory persistence errors."""

from __future__ import annotations


class MarketMemoryError(Exception):
    def __init__(self, message: str, *, code: str = "market_memory_error") -> None:
        super().__init__(message)
        self.code = code


class EvidenceConflictError(MarketMemoryError):
    """Same evidence_id with different payload — refuse silent overwrite."""

    def __init__(self, message: str = "evidence conflict") -> None:
        super().__init__(message, code="evidence_conflict")


class EvidenceImmutabilityError(MarketMemoryError):
    def __init__(self, message: str = "historical evidence is immutable") -> None:
        super().__init__(message, code="immutable_evidence")
