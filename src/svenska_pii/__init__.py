"""svenska_pii: Swedish PII recognizers with check-digit validation.

Core API (standard library only)::

    from svenska_pii import hitta, dom, maska

    hits = hitta(text)          # find
    verdict = dom(hits)         # stop or pass
    safe = maska(text, hits)    # mask

English aliases ``find``, ``verdict`` and ``mask`` are provided as well.
The optional Presidio integration lives in :mod:`svenska_pii.presidio`.
"""

from .core import (
    ALL_TYPES,
    CONTACT_TYPES,
    EMAIL,
    HARD_TYPES,
    PERSON,
    SE_ADDRESS,
    SE_BANKGIRO,
    SE_IBAN,
    SE_KONTONUMMER,
    SE_ORGNR,
    SE_PERSONNUMMER,
    SE_PHONE,
    SE_PLUSGIRO,
    SE_POSTCODE,
    SE_SAMORDNINGSNUMMER,
    SOFT_TYPES,
    Dom,
    Traff,
    dom,
    hitta,
    luhn,
    maska,
    resolve_overlaps,
)

find = hitta
verdict = dom
mask = maska

__version__ = "0.1.0"

__all__ = [
    "ALL_TYPES",
    "CONTACT_TYPES",
    "EMAIL",
    "HARD_TYPES",
    "PERSON",
    "SE_ADDRESS",
    "SE_BANKGIRO",
    "SE_IBAN",
    "SE_KONTONUMMER",
    "SE_ORGNR",
    "SE_PERSONNUMMER",
    "SE_PHONE",
    "SE_PLUSGIRO",
    "SE_POSTCODE",
    "SE_SAMORDNINGSNUMMER",
    "SOFT_TYPES",
    "Dom",
    "Traff",
    "dom",
    "find",
    "hitta",
    "luhn",
    "mask",
    "maska",
    "resolve_overlaps",
    "verdict",
    "__version__",
]
