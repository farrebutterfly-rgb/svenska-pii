"""Swedish PII recognizers with check-digit validation. Standard library only.

Every candidate is validated (check digit, calendar date, or surrounding context)
so that dates, invoice numbers and amounts are not reported as personal data.

Hard types (identity and payment numbers) always stop outgoing text.
Soft types (e-mail, phone, street address, postcode, and names supplied by an
external NER model) are masked, but only stop outgoing text when they appear in
quantity, that is when the text looks like a register of people.
"""

from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from typing import Callable, Dict, Iterable, Iterator, List, Optional, Tuple

__all__ = [
    "Traff",
    "Dom",
    "hitta",
    "dom",
    "maska",
    "luhn",
    "resolve_overlaps",
    "HARD_TYPES",
    "SOFT_TYPES",
    "CONTACT_TYPES",
    "ALL_TYPES",
    "SE_PERSONNUMMER",
    "SE_SAMORDNINGSNUMMER",
    "SE_ORGNR",
    "SE_BANKGIRO",
    "SE_PLUSGIRO",
    "SE_IBAN",
    "SE_KONTONUMMER",
    "EMAIL",
    "SE_PHONE",
    "SE_ADDRESS",
    "SE_POSTCODE",
    "PERSON",
]

# Entity names. These are part of the public API and are kept stable.
SE_PERSONNUMMER = "SE_PERSONNUMMER"
SE_SAMORDNINGSNUMMER = "SE_SAMORDNINGSNUMMER"
SE_ORGNR = "SE_ORGNR"
SE_BANKGIRO = "SE_BANKGIRO"
SE_PLUSGIRO = "SE_PLUSGIRO"
SE_IBAN = "SE_IBAN"
SE_KONTONUMMER = "SE_KONTONUMMER"
EMAIL = "EMAIL"
SE_PHONE = "SE_PHONE"
SE_ADDRESS = "SE_ADDRESS"
SE_POSTCODE = "SE_POSTCODE"
#: Names are not detected by this package (that needs an NLP model), but
#: ``PERSON`` hits from an external recognizer are understood by :func:`dom`.
PERSON = "PERSON"

HARD_TYPES = frozenset(
    {SE_PERSONNUMMER, SE_SAMORDNINGSNUMMER, SE_ORGNR, SE_BANKGIRO, SE_PLUSGIRO, SE_IBAN, SE_KONTONUMMER}
)
SOFT_TYPES = frozenset({PERSON, EMAIL, SE_PHONE, SE_ADDRESS, SE_POSTCODE})
CONTACT_TYPES = frozenset({EMAIL, SE_PHONE, SE_ADDRESS, SE_POSTCODE})
ALL_TYPES = HARD_TYPES | (SOFT_TYPES - {PERSON})

#: A register is contact details in quantity. Names alone never stop text,
#: since name recognition often mistakes tool and product names for people.
REGISTER_CONTACT = 4          # this many contact details is enough
REGISTER_MIXED = (2, 4)       # or at least 2 contact details and 4 names


@dataclass(frozen=True)
class Traff:
    """A single detection ("träff" is Swedish for hit).

    Attributes:
        entity_type: One of the entity names, for example ``SE_PERSONNUMMER``.
        start: Start offset in the scanned text (inclusive).
        end: End offset in the scanned text (exclusive).
        score: Confidence between 0 and 1.
        text: The matched substring.
    """

    entity_type: str
    start: int
    end: int
    score: float
    text: str = ""

    @property
    def is_hard(self) -> bool:
        """True if this entity type always stops outgoing text."""
        return self.entity_type in HARD_TYPES


@dataclass(frozen=True)
class Dom:
    """Verdict for outgoing text ("dom" is Swedish for verdict).

    Attributes:
        stop: True if the text must not leave.
        reason: Counts per entity type that caused the stop (empty if not stopped).
        counts: Counts per entity type for all hits.
    """

    stop: bool
    reason: Dict[str, int] = field(default_factory=dict)
    counts: Dict[str, int] = field(default_factory=dict)


def luhn(digits: str) -> bool:
    """Return True if the digit string passes the Luhn (mod 10) check."""
    total = 0
    for i, c in enumerate(reversed(digits)):
        d = int(c)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _date_ok(yy: str, mm: str, dd: str, century: Optional[str] = None) -> bool:
    """True if yymmdd is a valid calendar date.

    Without an explicit century the year is taken as 19yy. Coordination numbers
    (day + 60) are converted by the caller before this check.
    """
    year = int(century + yy) if century else 1900 + int(yy)
    try:
        datetime.date(year, int(mm), int(dd))
        return True
    except ValueError:
        return False


def _near(text: str, start: int, words: Iterable[str], window: int = 28) -> bool:
    """True if any context word occurs within ``window`` characters before ``start``."""
    area = text[max(0, start - window):start].lower()
    return any(w in area for w in words)


_PNR = re.compile(r"(?<![\d-])(19|20)?(\d{2})(\d{2})(\d{2})([-+]?)(\d{4})(?![\d-])")
_ORG = re.compile(r"(?<![\d-])(16)?(\d{6})-?(\d{4})(?![\d-])")
_BG = re.compile(r"(?<![\d-])(\d{3,4})-(\d{4})(?![\d-])")
_PG = re.compile(r"(?<![\d-])(\d{1,7})-(\d)(?![\d-])")
_IBAN = re.compile(r"\bSE\d{2}(?:\s?\d{4}){5}\b", re.I)
_KONTO = re.compile(r"(?<![\d-])(\d{4}(?:-\d)?)[\s,]+((?:\d[\s-]?){6,11}\d)(?![\d-])")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_PHONE = re.compile(
    r"(?<![\d+])(?:\+46[\s-]?\(?0?\)?|0)(?:7[02369]|8|[1-6]\d)[\s-]?\d{2,3}[\s-]?\d{2}[\s-]?\d{2,3}(?!\d)"
)
_STREET = re.compile(
    r"\b[A-ZÅÄÖ][a-zåäöé]+(?:gatan|vägen|väg|gränd|stigen|backe|backen|torg|torget|plan|allé|leden|stråket|gata)"
    r"\s+\d{1,4}\s?[A-Za-z]?\b"
)
_POSTCODE = re.compile(r"(?<!\d)(\d{3})\s(\d{2})\s+([A-ZÅÄÖ][a-zåäöA-ZÅÄÖ]+)\b")

BANKGIRO_CONTEXT = ("bankgiro", "bg", "bg-nr", "bg nr")
PLUSGIRO_CONTEXT = ("plusgiro", "pg", "pg-nr", "postgiro")
ACCOUNT_CONTEXT = ("konto", "kontonr", "kontonummer", "clearing", "clnr", "clearingnr")

_Raw = Tuple[str, int, int, float]


def _personnummer(text: str) -> Iterator[_Raw]:
    for m in _PNR.finditer(text):
        century, yy, mm, dd, _sep, last = m.groups()
        if not luhn(yy + mm + dd + last):
            continue
        day = int(dd)
        typ = SE_PERSONNUMMER
        if 61 <= day <= 91:
            day -= 60
            typ = SE_SAMORDNINGSNUMMER
        if not (1 <= int(mm) <= 12) or not _date_ok(yy, mm, f"{day:02d}", century):
            continue
        yield typ, m.start(), m.end(), 0.95


def _orgnr(text: str) -> Iterator[_Raw]:
    for m in _ORG.finditer(text):
        _prefix, six, four = m.groups()
        ten = six + four
        if not luhn(ten):
            continue
        if int(ten[2:4]) < 20:  # a month below 20 means personnummer, not orgnr
            continue
        yield SE_ORGNR, m.start(), m.end(), 0.9


def _giro(text: str) -> Iterator[_Raw]:
    for m in _BG.finditer(text):
        s = m.group(1) + m.group(2)
        if luhn(s) and _near(text, m.start(), BANKGIRO_CONTEXT):
            yield SE_BANKGIRO, m.start(), m.end(), 0.9
    for m in _PG.finditer(text):
        s = m.group(1) + m.group(2)
        if len(s) >= 2 and luhn(s) and _near(text, m.start(), PLUSGIRO_CONTEXT):
            yield SE_PLUSGIRO, m.start(), m.end(), 0.9


def _iban(text: str) -> Iterator[_Raw]:
    for m in _IBAN.finditer(text):
        s = re.sub(r"\s", "", m.group(0)).upper()
        n = int("".join(str(int(c, 36)) for c in s[4:] + s[:4]))
        if n % 97 == 1:
            yield SE_IBAN, m.start(), m.end(), 0.98


def _kontonummer(text: str) -> Iterator[_Raw]:
    for m in _KONTO.finditer(text):
        if _near(text, m.start(), ACCOUNT_CONTEXT):
            yield SE_KONTONUMMER, m.start(), m.end(), 0.85


def _soft(text: str) -> Iterator[_Raw]:
    for m in _EMAIL.finditer(text):
        yield EMAIL, m.start(), m.end(), 0.9
    for m in _PHONE.finditer(text):
        yield SE_PHONE, m.start(), m.end(), 0.75
    for m in _STREET.finditer(text):
        yield SE_ADDRESS, m.start(), m.end(), 0.8
    for m in _POSTCODE.finditer(text):
        yield SE_POSTCODE, m.start(), m.end(), 0.7


RULES: Tuple[Callable[[str], Iterator[_Raw]], ...] = (_personnummer, _orgnr, _giro, _iban, _kontonummer, _soft)

#: Which rule produces which entity types. Used by the Presidio integration.
RULE_FOR_ENTITY: Dict[str, Callable[[str], Iterator[_Raw]]] = {
    SE_PERSONNUMMER: _personnummer,
    SE_SAMORDNINGSNUMMER: _personnummer,
    SE_ORGNR: _orgnr,
    SE_BANKGIRO: _giro,
    SE_PLUSGIRO: _giro,
    SE_IBAN: _iban,
    SE_KONTONUMMER: _kontonummer,
    EMAIL: _soft,
    SE_PHONE: _soft,
    SE_ADDRESS: _soft,
    SE_POSTCODE: _soft,
}

_IDENTITY_TYPES = frozenset({SE_PERSONNUMMER, SE_SAMORDNINGSNUMMER, SE_ORGNR})


def _canon(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z@._+-]", "", value).replace("-", "").upper()


def _allowset(allowlist: Optional[Iterable[str]]) -> frozenset:
    out = set()
    for v in allowlist or ():
        c = _canon(v)
        out.add(c)
        if c.isdigit() and len(c) == 12:
            out.add(c[-10:])
    return frozenset(out)


def _allowed(typ: str, matched: str, allow: frozenset) -> bool:
    if not allow:
        return False
    c = _canon(matched)
    if c in allow:
        return True
    return typ in _IDENTITY_TYPES and c.isdigit() and c[-10:] in allow


def _filter_allow(text: str, raw: Iterable[_Raw], allow: frozenset) -> Iterator[_Raw]:
    for typ, a, b, s in raw:
        if not _allowed(typ, text[a:b], allow):
            yield typ, a, b, s


def resolve_overlaps(hits: Iterable[Traff]) -> List[Traff]:
    """Keep non-overlapping hits, preferring hard types, then higher score, then earlier start."""
    ordered = sorted(hits, key=lambda t: (t.entity_type not in HARD_TYPES, -t.score, t.start))
    chosen: List[Traff] = []
    for t in ordered:
        if all(t.end <= v.start or t.start >= v.end for v in chosen):
            chosen.append(t)
    return sorted(chosen, key=lambda t: t.start)


def hitta(text: Optional[str], allowlist: Optional[Iterable[str]] = None) -> List[Traff]:
    """Find Swedish PII in ``text`` ("hitta" is Swedish for find).

    Args:
        text: The text to scan. ``None`` is treated as an empty string.
        allowlist: Optional values that must never be reported, for example
            your own organisation number. Separators are ignored, and a
            12-digit form with century or ``16`` prefix also matches the
            10-digit form.

    Returns:
        Non-overlapping hits sorted by start offset. Overlaps are resolved in
        favour of hard types and higher confidence.
    """
    text = text or ""
    allow = _allowset(allowlist)
    raw: List[Traff] = []
    for rule in RULES:
        for typ, a, b, s in _filter_allow(text, rule(text), allow):
            raw.append(Traff(typ, a, b, s, text[a:b]))
    return resolve_overlaps(raw)


def dom(
    traffar: Iterable[Traff],
    register_contact: int = REGISTER_CONTACT,
    register_mixed: Tuple[int, int] = REGISTER_MIXED,
) -> Dom:
    """Verdict for outgoing text.

    Stops on any hard hit, or when soft hits look like a register: at least
    ``register_contact`` contact details, or at least ``register_mixed[0]``
    contact details together with ``register_mixed[1]`` names (``PERSON``).
    Names alone never stop.

    Args:
        traffar: Hits from :func:`hitta`, optionally merged with ``PERSON``
            hits from an NER model.
        register_contact: Contact-detail threshold for a register.
        register_mixed: (contact details, names) threshold for a register.
    """
    counts: Dict[str, int] = {}
    for t in traffar:
        counts[t.entity_type] = counts.get(t.entity_type, 0) + 1
    hard = {k: v for k, v in counts.items() if k in HARD_TYPES}
    contact = sum(v for k, v in counts.items() if k in CONTACT_TYPES)
    names = counts.get(PERSON, 0)
    register = contact >= register_contact or (contact >= register_mixed[0] and names >= register_mixed[1])
    stop = bool(hard) or register
    if hard:
        reason = hard
    elif stop:
        reason = {k: v for k, v in counts.items() if k in SOFT_TYPES}
    else:
        reason = {}
    return Dom(stop=stop, reason=reason, counts=counts)


def maska(text: str, traffar: Iterable[Traff], fmt: str = "[{type}]") -> str:
    """Replace each hit with a placeholder ("maska" is Swedish for mask).

    The default placeholder is the lower-cased entity type in brackets, for
    example ``[se_personnummer]``. ``fmt`` may use ``{type}`` (lower case) and
    ``{TYPE}`` (as is). Hits are expected not to overlap, as returned by
    :func:`hitta`.
    """
    out: List[str] = []
    pos = 0
    for t in sorted(traffar, key=lambda t: t.start):
        out.append(text[pos:t.start])
        out.append(fmt.format(type=t.entity_type.lower(), TYPE=t.entity_type))
        pos = t.end
    out.append(text[pos:])
    return "".join(out)
