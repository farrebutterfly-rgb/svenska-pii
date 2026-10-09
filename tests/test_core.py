import pytest

import svenska_pii as sp
from svenska_pii import Traff, dom, hitta, luhn, maska

import cases as c

HARDISH_OK_IN_NEGATIVES = {"SE_ADDRESS", "SE_POSTCODE", "PERSON"}


def types(text, **kw):
    return {t.entity_type for t in hitta(text, **kw)}


@pytest.mark.parametrize("text,expected", c.POSITIVA, ids=[t for t, _ in c.POSITIVA])
def test_reference_positives(text, expected):
    got = types(text)
    assert expected <= got, f"missing {expected - got} in {text!r}, got {got}"


@pytest.mark.parametrize("text", c.NEGATIVA)
def test_reference_negatives(text):
    hits = hitta(text)
    assert not dom(hits).stop, hits
    assert all(h.entity_type in HARDISH_OK_IN_NEGATIVES for h in hits), hits


@pytest.mark.parametrize("text", c.ORG_SENTENCES)
def test_reference_orgnr_list(text):
    assert "SE_ORGNR" in types(text)


def test_reference_register_stops():
    d = dom(hitta(c.REGISTER))
    assert d.stop
    assert d.reason == {"EMAIL": 4, "SE_PHONE": 4}


@pytest.mark.parametrize("text,expected", c.EDGE_POSITIVA, ids=[t for t, _ in c.EDGE_POSITIVA])
def test_edge_positives(text, expected):
    assert types(text) == expected


@pytest.mark.parametrize("text", c.EDGE_NEGATIVA)
def test_edge_negatives(text):
    hits = hitta(text)
    assert hits == [], hits
    assert not dom(hits).stop


def test_pnr_is_not_orgnr_and_orgnr_is_not_pnr():
    assert types(f"x {c.P1} x") == {"SE_PERSONNUMMER"}
    assert types(f"x {c.O1} x") == {"SE_ORGNR"}


def test_samordningsnummer_day_plus_60():
    assert types(c.S1) == {"SE_SAMORDNINGSNUMMER"}
    assert c.S1[4:6] == "72"


def test_iban_spans_whole_number():
    text = f"IBAN {c.IBAN_SPACED}."
    (h,) = hitta(text)
    assert h.text == c.IBAN_SPACED
    assert h.score == 0.98


def test_offsets_and_text():
    text = f"Kundens personnummer är {c.P1}."
    (h,) = hitta(text)
    assert text[h.start:h.end] == c.P1 == h.text
    assert h.is_hard


def test_masking():
    hits = hitta(c.MASK_TEXT)
    assert maska(c.MASK_TEXT, hits) == c.MASK_EXPECTED


def test_masking_custom_format():
    text = f"pnr {c.P1}"
    assert maska(text, hitta(text), fmt="<{TYPE}>") == "pnr <SE_PERSONNUMMER>"


def test_masking_no_hits_is_identity():
    assert maska("hej", []) == "hej"


def test_verdict_four_contacts_is_register():
    hits = hitta(c.FOUR_CONTACTS)
    assert len(hits) == 4
    d = dom(hits)
    assert d.stop
    assert sum(d.reason.values()) == 4


def test_verdict_three_contacts_passes():
    d = dom(hitta(c.THREE_CONTACTS))
    assert not d.stop
    assert d.reason == {}
    assert sum(d.counts.values()) == 3


def test_names_alone_never_stop():
    names = [Traff("PERSON", i * 10, i * 10 + 5, 0.85) for i in range(50)]
    assert not dom(names).stop


def test_names_plus_two_contacts_stop():
    names = [Traff("PERSON", i * 10, i * 10 + 5, 0.85) for i in range(4)]
    contacts = [Traff("EMAIL", 100, 110, 0.9), Traff("SE_PHONE", 120, 130, 0.75)]
    d = dom(names + contacts)
    assert d.stop
    assert d.reason == {"PERSON": 4, "EMAIL": 1, "SE_PHONE": 1}


def test_names_plus_one_contact_passes():
    names = [Traff("PERSON", i * 10, i * 10 + 5, 0.85) for i in range(10)]
    assert not dom(names + [Traff("EMAIL", 200, 210, 0.9)]).stop


def test_single_hard_hit_stops():
    d = dom(hitta(f"pnr {c.P1}"))
    assert d.stop and d.reason == {"SE_PERSONNUMMER": 1}


def test_custom_thresholds():
    hits = hitta(c.THREE_CONTACTS)
    assert dom(hits, register_contact=3).stop


def test_allowlist():
    assert types(c.ALLOWLIST_TEXT) == {"SE_ORGNR"}
    assert types(c.ALLOWLIST_TEXT, allowlist=c.ALLOWLIST) == set()
    # separators and the 16 prefix are ignored
    assert types(c.ALLOWLIST_TEXT, allowlist=[c.O_OWN.replace("-", "")]) == set()
    assert types(c.ALLOWLIST_TEXT, allowlist=["16" + c.O_OWN.replace("-", "")]) == set()
    # other numbers are still found
    assert types(f"{c.ALLOWLIST_TEXT} Motpart {c.O1}", allowlist=c.ALLOWLIST) == {"SE_ORGNR"}


def test_allowlist_email():
    text = "Skriv till info@exempel.se"
    assert types(text) == {"EMAIL"}
    assert types(text, allowlist=["INFO@exempel.se"]) == set()


def test_overlap_prefers_hard_types():
    hits = [Traff("SE_PHONE", 0, 10, 0.99), Traff("SE_PERSONNUMMER", 2, 12, 0.5)]
    (kept,) = sp.resolve_overlaps(hits)
    assert kept.entity_type == "SE_PERSONNUMMER"


def test_empty_and_none():
    assert hitta("") == []
    assert hitta(None) == []


def test_luhn():
    assert luhn("5566778899") is (c.check_digit("556677889") == "9")
    assert luhn("0")
    assert not luhn("1")


def test_english_aliases():
    assert sp.find is sp.hitta and sp.verdict is sp.dom and sp.mask is sp.maska


def test_entity_names_stable():
    assert sp.HARD_TYPES == {
        "SE_PERSONNUMMER", "SE_SAMORDNINGSNUMMER", "SE_ORGNR", "SE_BANKGIRO",
        "SE_PLUSGIRO", "SE_IBAN", "SE_KONTONUMMER",
    }
    assert sp.ALL_TYPES - sp.HARD_TYPES == {"EMAIL", "SE_PHONE", "SE_ADDRESS", "SE_POSTCODE"}
