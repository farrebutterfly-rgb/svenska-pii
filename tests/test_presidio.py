import pytest

presidio_analyzer = pytest.importorskip(
    "presidio_analyzer",
    reason="presidio-analyzer is not installed; install with: pip install -e '.[presidio]'",
)

from svenska_pii import hitta  # noqa: E402
from svenska_pii.presidio import (  # noqa: E402
    HARD_RECOGNIZERS,
    BankgiroRecognizer,
    IbanSeRecognizer,
    KontonummerRecognizer,
    OrgnrRecognizer,
    PersonnummerRecognizer,
    PlusgiroRecognizer,
    SamordningsnummerRecognizer,
    SwedishPhoneRecognizer,
    add_swedish_recognizers,
    swedish_recognizers,
    swedish_registry,
)

import cases as c  # noqa: E402

CASES = [
    (PersonnummerRecognizer, f"Kundens personnummer är {c.P1}.", c.P1),
    (PersonnummerRecognizer, f"Hundraåringen {c.P1.replace('-', '+')}.", c.P1.replace("-", "+")),
    (SamordningsnummerRecognizer, f"Samordningsnummer {c.S1} gäller.", c.S1),
    (OrgnrRecognizer, f"Motpart: Byggbolaget AB, org.nr {c.O1}", c.O1),
    (BankgiroRecognizer, f"Betala till bankgiro {c.B1} senast fredag", c.B1),
    (PlusgiroRecognizer, f"Plusgiro {c.PG1}", c.PG1),
    (IbanSeRecognizer, f"IBAN {c.IBAN_SPACED} till kontot", c.IBAN_SPACED),
    (IbanSeRecognizer, f"IBAN {c.IBAN_COMPACT}", c.IBAN_COMPACT),
    (KontonummerRecognizer, "Clearing och kontonummer 8327-9, 123 456 789-0 hos Swedbank", "8327-9, 123 456 789-0"),
]


@pytest.mark.parametrize("cls,text,expected", CASES, ids=[f"{k.__name__}:{e}" for k, _, e in CASES])
@pytest.mark.parametrize("lang", ["sv", "en"])
def test_recognizer_finds(cls, text, expected, lang):
    rec = cls(supported_language=lang)
    res = rec.analyze(text, [cls.ENTITY], nlp_artifacts=None)
    assert len(res) == 1
    r = res[0]
    assert r.entity_type == cls.ENTITY
    assert text[r.start:r.end] == expected
    assert 0 < r.score <= 1
    assert rec.supported_language == lang


@pytest.mark.parametrize("text", c.NEGATIVA + c.EDGE_NEGATIVA)
def test_recognizers_quiet_on_negatives(text):
    for cls in HARD_RECOGNIZERS:
        rec = cls()
        assert rec.analyze(text, [cls.ENTITY], nlp_artifacts=None) == [], (cls.__name__, text)


def test_pnr_recognizer_ignores_samordningsnummer_and_vice_versa():
    assert PersonnummerRecognizer().analyze(c.S1, ["SE_PERSONNUMMER"], None) == []
    assert SamordningsnummerRecognizer().analyze(c.P1, ["SE_SAMORDNINGSNUMMER"], None) == []


def test_entity_filter():
    assert PersonnummerRecognizer().analyze(c.P1, ["SE_ORGNR"], None) == []


def test_allowlist_in_recognizer():
    rec = OrgnrRecognizer(allowlist=c.ALLOWLIST)
    assert rec.analyze(c.ALLOWLIST_TEXT, ["SE_ORGNR"], None) == []


def test_soft_recognizer():
    res = SwedishPhoneRecognizer().analyze("Ring 070-123 45 67", ["SE_PHONE"], None)
    assert [r.entity_type for r in res] == ["SE_PHONE"]


@pytest.mark.parametrize("text,expected", c.POSITIVA + c.EDGE_POSITIVA)
def test_parity_with_core_for_hard_types(text, expected):
    recs = swedish_recognizers(languages=["sv"])
    found = set()
    for rec in recs:
        found |= {r.entity_type for r in rec.analyze(text, rec.supported_entities, None)}
    core_hard = {h.entity_type for h in hitta(text) if h.is_hard}
    assert core_hard <= found


def test_swedish_registry_languages():
    reg = swedish_registry()
    for lang in ("sv", "en"):
        recs = reg.get_recognizers(language=lang, all_fields=True)
        assert len(recs) == len(HARD_RECOGNIZERS)
        assert {e for r in recs for e in r.supported_entities} == {k.ENTITY for k in HARD_RECOGNIZERS}


def test_swedish_registry_soft():
    reg = swedish_registry(languages=["sv"], include_soft=True)
    ents = {e for r in reg.get_recognizers(language="sv", all_fields=True) for e in r.supported_entities}
    assert {"SE_PHONE", "SE_ADDRESS", "SE_POSTCODE"} <= ents


def test_add_to_existing_registry():
    reg = presidio_analyzer.RecognizerRegistry(supported_languages=["sv"])
    out = add_swedish_recognizers(reg, languages=["sv"])
    assert out is reg
    assert len(reg.get_recognizers(language="sv", all_fields=True)) == len(HARD_RECOGNIZERS)


def test_registry_lookup_by_entity():
    reg = swedish_registry(languages=["sv"])
    recs = reg.get_recognizers(language="sv", entities=["SE_PERSONNUMMER"])
    assert [type(r).__name__ for r in recs] == ["PersonnummerRecognizer"]
