"""Shared test cases. Every number is computed with a correct check digit (unless the case
is about a wrong one). Personnummer are taken from Skatteverket's published test numbers
(testpersonnummer), which are never assigned to real people. Samordningsnummer have no
published test list; they are built from a test number base with 60 added to the day. Used by the tests and by scripts/make_vectors.py."""

from __future__ import annotations


def check_digit(payload: str) -> str:
    """Last digit that makes the Luhn sum come out even."""
    s = 0
    for i, c in enumerate(reversed(payload)):
        d = int(c)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        s += d
    return str((10 - s % 10) % 10)


def pnr(yymmdd: str, three: str, sep: str = "-") -> str:
    return yymmdd + sep + three + check_digit(yymmdd + three)


def org(nine: str) -> str:
    return nine[:6] + "-" + nine[6:] + check_digit(nine)


def bg(six: str) -> str:
    return six[:3] + "-" + six[3:] + check_digit(six)


def pg(body: str) -> str:
    return body + "-" + check_digit(body)


def wrong(number: str) -> str:
    return number[:-1] + str((int(number[-1]) + 1) % 10)


P1, P2 = pnr("850312", "238"), pnr("910701", "238")
S1 = pnr("850372", "238")  # samordningsnummer, day 12 + 60
O1 = org("556677889")
FEL_PNR = wrong(P1)
B1 = bg("567123")
PG1 = pg("4567890")
O_OWN = org("559000123")  # stands in for "your own" orgnr in allowlist tests
IBAN_SPACED = "SE45 5000 0000 0583 9825 7466"
IBAN_COMPACT = IBAN_SPACED.replace(" ", "")

# Ported from the reference test bank (client-name case removed).
POSITIVA = [
    (f"Kundens personnummer är {P1}.", {"SE_PERSONNUMMER"}),
    (f"pnr 19{P2.replace('-', '')} enligt avtalet", {"SE_PERSONNUMMER"}),
    (f"Samordningsnummer {S1} gäller.", {"SE_SAMORDNINGSNUMMER"}),
    (f"Motpart: Byggbolaget AB, org.nr {O1}", {"SE_ORGNR"}),
    (f"Betala till bankgiro {B1} senast fredag", {"SE_BANKGIRO"}),
    (f"IBAN {IBAN_SPACED} till kontot", {"SE_IBAN"}),
    ("Clearing och kontonummer 8327-9, 123 456 789-0 hos Swedbank", {"SE_KONTONUMMER"}),
    ("Ring 070-123 45 67 eller mejla anna.svensson@exempel.se", {"SE_PHONE", "EMAIL"}),
    ("Adress: Storgatan 12, 111 22 Stockholm", {"SE_ADDRESS", "SE_POSTCODE"}),
]

NEGATIVA = [
    "Fakturanummer 2026-001, förfaller 2026-10-30.",
    "Beloppet är 34 720 kr och tillskottet 36 000 kr.",
    f"Felaktigt nummer {FEL_PNR} ska inte räknas.",
    "Mötet är 2026-10-12 kl 14.30 i rum 305.",
    "PCT-avgift 34720 kr, ärende ABC-IP-004, version 1.2.3.",
    "Commit 1234-5678 i repot, build 20260930-1422.",
    "Projektstatus: Block A klart, C.1 till C.4 körda.",
]

# Reference negative that relied on a hardcoded whitelist, now an allowlist case.
ALLOWLIST_TEXT = f"Exempelbolaget AB, org.nr {O_OWN}, Solna."
ALLOWLIST = [O_OWN]

ORGNUMMER = [
    org(x)
    for x in (
        "556012345", "556398761", "802415679", "716411234", "556677123",
        "559001234", "969712345", "212000014", "556123987", "556999111",
    )
]
ORG_SENTENCES = [f"Leverantören, org.nr {n}, fakturerar." for n in ORGNUMMER]

REGISTER = "\n".join(f"Namn {i}: kontakt{i}@exempel.se, 070-{100 + i} {10 + i} {20 + i}" for i in range(4))

EDGE_POSITIVA = [
    # century prefix, with and without separator
    (f"Personnummer 19{P1}.", {"SE_PERSONNUMMER"}),
    (f"Född 19{P1.replace('-', '')} i Malmö.", {"SE_PERSONNUMMER"}),
    # '+' separator for people aged 100 or more
    (f"Hundraåringen har nummer {P1.replace('-', '+')}.", {"SE_PERSONNUMMER"}),
    # ten digits without separator
    (f"pnr {P1.replace('-', '')}", {"SE_PERSONNUMMER"}),
    # leap day with explicit century
    (f"Född 20{pnr('000229', '239')}.", {"SE_PERSONNUMMER"}),
    # samordningsnummer with century and day 91 (31 + 60)
    (f"Samordningsnummer 19{pnr('850391', '238')}", {"SE_SAMORDNINGSNUMMER"}),
    # orgnr without hyphen and with the 16 prefix
    (f"Orgnr {O1.replace('-', '')}", {"SE_ORGNR"}),
    (f"Organisationsnummer 16{O1.replace('-', '')}", {"SE_ORGNR"}),
    # IBAN without spaces and in lower case
    (f"IBAN {IBAN_COMPACT}", {"SE_IBAN"}),
    (f"iban {IBAN_COMPACT.lower()}", {"SE_IBAN"}),
    # plusgiro with context
    (f"Plusgiro {PG1}", {"SE_PLUSGIRO"}),
    # phone in international form
    ("Mobil +46 70 123 45 67", {"SE_PHONE"}),
    # pnr and orgnr in the same sentence are kept apart
    (f"Firmatecknare {P1} för bolaget {O1}.", {"SE_PERSONNUMMER", "SE_ORGNR"}),
]

EDGE_NEGATIVA = [
    # invalid date 850230 with a correct check digit
    f"Nummer {pnr('850230', '238')} finns inte.",
    # month 13
    f"Nummer {pnr('851301', '238')} finns inte.",
    # samordningsnummer day 92 is not a date
    f"Nummer {pnr('850392', '238')} finns inte.",
    # wrong check digit on orgnr, coordination number and bankgiro
    f"Org.nr {wrong(O1)} är fel.",
    f"Samordningsnummer {wrong(S1)} är fel.",
    f"Bankgiro {wrong(B1)} är fel.",
    # IBAN with a broken checksum
    f"IBAN {IBAN_SPACED[:-1]}5",
    # bankgiro, plusgiro and account numbers need context words
    f"Koden {B1} öppnar dörren.",
    f"Version {PG1} släpptes.",
    "Serie 8327-9, 123 456 789-0 i lagret.",
    # a date followed by a short number
    "Leverans 2026-10-30 1422 st.",
    # amounts and large numbers
    f"Omsättningen var 1 234 567 kr, löpnummer {wrong(P1.replace('-', ''))}.",
]

MASK_TEXT = f"Pnr {P1}, e-post anna@exempel.se, bankgiro {B1}."
MASK_EXPECTED = "Pnr [se_personnummer], e-post [email], bankgiro [se_bankgiro]."

THREE_CONTACTS = "Kontakt: a@exempel.se, b@exempel.se, 070-123 45 67."
FOUR_CONTACTS = "Kontakt: a@exempel.se, b@exempel.se, 070-123 45 67, 08-123 45 67."


def all_texts() -> list[str]:
    """Every text used by the tests, for vector generation."""
    texts: list[str] = []
    texts += [t for t, _ in POSITIVA]
    texts += NEGATIVA
    texts += [t for t, _ in EDGE_POSITIVA]
    texts += EDGE_NEGATIVA
    texts += ORG_SENTENCES
    texts += [REGISTER, ALLOWLIST_TEXT, MASK_TEXT, THREE_CONTACTS, FOUR_CONTACTS]
    seen: set[str] = set()
    out = []
    for t in texts:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out
