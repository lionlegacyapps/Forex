"""License review — basic compatibility flags only.

Does NOT make legal conclusions. Unclear/incompatible licensing blocks
code copying into the trading codebase.
"""

from __future__ import annotations

import re

from app.strategy_intake.models import LicenseFlag, LicenseKind, LicenseReviewResult

_PERMISSIVE = {
    LicenseKind.MIT,
    LicenseKind.APACHE_2_0,
    LicenseKind.BSD,
}

_COPYLEFT = {
    LicenseKind.GPL,
    LicenseKind.LGPL,
    LicenseKind.MPL,
}


def review_license(raw_license: str | None) -> LicenseReviewResult:
    kind = classify_license(raw_license)
    flags: list[LicenseFlag] = []
    notes: list[str] = [
        "This review provides basic compatibility flags only — not legal advice.",
    ]
    adaptation_allowed = False

    if kind == LicenseKind.NO_LICENSE:
        flags.append(LicenseFlag.NO_LICENSE)
        notes.append("No license declared; do not copy code.")
    elif kind == LicenseKind.UNKNOWN:
        flags.append(LicenseFlag.UNKNOWN_LICENSE)
        notes.append("License unrecognized; do not copy code until clarified.")
    elif kind == LicenseKind.AGPL:
        flags.append(LicenseFlag.AGPL_REVIEW_REQUIRED)
        flags.append(LicenseFlag.COPYLEFT_REVIEW_REQUIRED)
        notes.append("AGPL requires explicit legal/product review before any use.")
    elif kind in _COPYLEFT:
        flags.append(LicenseFlag.COPYLEFT_REVIEW_REQUIRED)
        notes.append("Copyleft license requires review before adaptation.")
    elif kind == LicenseKind.PROPRIETARY_CUSTOM:
        flags.append(LicenseFlag.CUSTOM_REVIEW_REQUIRED)
        notes.append("Custom/proprietary license requires explicit permission.")
    elif kind in _PERMISSIVE:
        flags.append(LicenseFlag.PERMISSIVE_OK)
        adaptation_allowed = True
        notes.append("Permissive license flag — still require security/architecture review.")

    return LicenseReviewResult(
        license_kind=kind,
        raw_license=raw_license,
        flags=flags,
        adaptation_allowed=adaptation_allowed,
        notes=notes,
    )


def classify_license(raw_license: str | None) -> LicenseKind:
    if raw_license is None or not str(raw_license).strip():
        return LicenseKind.NO_LICENSE
    text = str(raw_license).strip().lower()
    if text in {"none", "no license", "unlicensed", "n/a"}:
        return LicenseKind.NO_LICENSE
    if "agpl" in text:
        return LicenseKind.AGPL
    if re.search(r"\bgpl\b", text) or "gnu general public" in text:
        return LicenseKind.GPL
    if "lgpl" in text:
        return LicenseKind.LGPL
    if "mpl" in text or "mozilla public" in text:
        return LicenseKind.MPL
    if "apache" in text:
        return LicenseKind.APACHE_2_0
    if "bsd" in text:
        return LicenseKind.BSD
    if text == "mit" or "mit license" in text:
        return LicenseKind.MIT
    if "proprietary" in text or "custom" in text or "all rights reserved" in text:
        return LicenseKind.PROPRIETARY_CUSTOM
    return LicenseKind.UNKNOWN
