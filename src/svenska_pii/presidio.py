"""Optional Microsoft Presidio integration.

Install with ``pip install svenska-pii[presidio]``. The recognizers wrap the
same validated rules as :func:`svenska_pii.hitta`, so check digits, dates and
context words apply exactly as in the core API. They do not use NLP artifacts,
so they work without a spaCy model.

Numbers are language independent, so recognizers are registered for both
``sv`` and ``en`` by default.
"""

from __future__ import annotations

from typing import Iterable, List, Optional, Sequence, Type

try:
    from presidio_analyzer import AnalysisExplanation, EntityRecognizer, RecognizerRegistry, RecognizerResult
except ImportError as exc:  # pragma: no cover - exercised only without the extra
    raise ImportError(
        "svenska_pii.presidio requires presidio-analyzer. Install with: pip install svenska-pii[presidio]"
    ) from exc

from . import core

__all__ = [
    "SwedishRecognizer",
    "PersonnummerRecognizer",
    "SamordningsnummerRecognizer",
    "OrgnrRecognizer",
    "BankgiroRecognizer",
    "PlusgiroRecognizer",
    "IbanSeRecognizer",
    "KontonummerRecognizer",
    "SwedishPhoneRecognizer",
    "SwedishAddressRecognizer",
    "SwedishPostcodeRecognizer",
    "HARD_RECOGNIZERS",
    "SOFT_RECOGNIZERS",
    "DEFAULT_LANGUAGES",
    "swedish_recognizers",
    "add_swedish_recognizers",
    "swedish_registry",
]

DEFAULT_LANGUAGES: Sequence[str] = ("sv", "en")


class SwedishRecognizer(EntityRecognizer):
    """Base class: one Presidio recognizer per Swedish entity type.

    Subclasses set ``ENTITY`` and ``CONTEXT``. Detection is delegated to the
    rule in :mod:`svenska_pii.core` that produces that entity.

    Args:
        supported_language: Presidio language code, for example ``"sv"``.
        allowlist: Values that must never be reported (see :func:`svenska_pii.hitta`).
    """

    ENTITY: str = ""
    CONTEXT: Sequence[str] = ()

    def __init__(self, supported_language: str = "sv", allowlist: Optional[Iterable[str]] = None) -> None:
        self._allow = core._allowset(allowlist)
        super().__init__(
            supported_entities=[self.ENTITY],
            name=f"{type(self).__name__}",
            supported_language=supported_language,
            context=list(self.CONTEXT),
        )

    def load(self) -> None:
        """Nothing to load: the rules are pure Python."""

    def analyze(self, text: str, entities: List[str], nlp_artifacts=None) -> List[RecognizerResult]:
        """Return validated hits for this recognizer's entity.

        ``nlp_artifacts`` is accepted for API compatibility and ignored.
        """
        if entities and self.ENTITY not in entities:
            return []
        rule = core.RULE_FOR_ENTITY[self.ENTITY]
        results: List[RecognizerResult] = []
        for typ, start, end, score in core._filter_allow(text, rule(text), self._allow):
            if typ != self.ENTITY:
                continue
            explanation = AnalysisExplanation(
                recognizer=self.name,
                original_score=score,
                textual_explanation=f"{self.ENTITY} validated by svenska_pii",
            )
            results.append(
                RecognizerResult(
                    entity_type=typ,
                    start=start,
                    end=end,
                    score=score,
                    analysis_explanation=explanation,
                    recognition_metadata={
                        RecognizerResult.RECOGNIZER_NAME_KEY: self.name,
                        RecognizerResult.RECOGNIZER_IDENTIFIER_KEY: self.id,
                    },
                )
            )
        return results


class PersonnummerRecognizer(SwedishRecognizer):
    """Swedish personal identity number, Luhn and date validated."""

    ENTITY = core.SE_PERSONNUMMER
    CONTEXT = ("personnummer", "pnr", "född", "personal identity number")


class SamordningsnummerRecognizer(SwedishRecognizer):
    """Swedish coordination number (day + 60), Luhn and date validated."""

    ENTITY = core.SE_SAMORDNINGSNUMMER
    CONTEXT = ("samordningsnummer", "coordination number")


class OrgnrRecognizer(SwedishRecognizer):
    """Swedish organisation number, Luhn validated, third digit pair at least 20."""

    ENTITY = core.SE_ORGNR
    CONTEXT = ("org.nr", "orgnr", "organisationsnummer", "organization number")


class BankgiroRecognizer(SwedishRecognizer):
    """Bankgiro number, Luhn validated, requires a context word before it."""

    ENTITY = core.SE_BANKGIRO
    CONTEXT = core.BANKGIRO_CONTEXT


class PlusgiroRecognizer(SwedishRecognizer):
    """Plusgiro number, Luhn validated, requires a context word before it."""

    ENTITY = core.SE_PLUSGIRO
    CONTEXT = core.PLUSGIRO_CONTEXT


class IbanSeRecognizer(SwedishRecognizer):
    """Swedish IBAN, validated with ISO 7064 mod 97."""

    ENTITY = core.SE_IBAN
    CONTEXT = ("iban",)


class KontonummerRecognizer(SwedishRecognizer):
    """Clearing number plus bank account number, requires a context word before it."""

    ENTITY = core.SE_KONTONUMMER
    CONTEXT = core.ACCOUNT_CONTEXT


class SwedishPhoneRecognizer(SwedishRecognizer):
    """Swedish phone number (soft type)."""

    ENTITY = core.SE_PHONE
    CONTEXT = ("telefon", "tel", "mobil", "ring", "phone")


class SwedishAddressRecognizer(SwedishRecognizer):
    """Swedish street address (soft type)."""

    ENTITY = core.SE_ADDRESS
    CONTEXT = ("adress", "address", "bor på")


class SwedishPostcodeRecognizer(SwedishRecognizer):
    """Swedish postcode followed by a town name (soft type)."""

    ENTITY = core.SE_POSTCODE
    CONTEXT = ("postnummer", "postort", "adress")


HARD_RECOGNIZERS: Sequence[Type[SwedishRecognizer]] = (
    PersonnummerRecognizer,
    SamordningsnummerRecognizer,
    OrgnrRecognizer,
    BankgiroRecognizer,
    PlusgiroRecognizer,
    IbanSeRecognizer,
    KontonummerRecognizer,
)
#: Presidio already ships EMAIL_ADDRESS, so e-mail is not duplicated here.
SOFT_RECOGNIZERS: Sequence[Type[SwedishRecognizer]] = (
    SwedishPhoneRecognizer,
    SwedishAddressRecognizer,
    SwedishPostcodeRecognizer,
)


def swedish_recognizers(
    languages: Sequence[str] = DEFAULT_LANGUAGES,
    include_soft: bool = False,
    allowlist: Optional[Iterable[str]] = None,
) -> List[SwedishRecognizer]:
    """Instantiate the Swedish recognizers, one instance per language."""
    allow = list(allowlist or ())
    classes = list(HARD_RECOGNIZERS) + (list(SOFT_RECOGNIZERS) if include_soft else [])
    return [cls(supported_language=lang, allowlist=allow) for lang in languages for cls in classes]


def add_swedish_recognizers(
    registry: RecognizerRegistry,
    languages: Sequence[str] = DEFAULT_LANGUAGES,
    include_soft: bool = False,
    allowlist: Optional[Iterable[str]] = None,
) -> RecognizerRegistry:
    """Add the Swedish recognizers to an existing Presidio registry and return it."""
    for rec in swedish_recognizers(languages, include_soft, allowlist):
        registry.add_recognizer(rec)
    return registry


def swedish_registry(
    languages: Sequence[str] = DEFAULT_LANGUAGES,
    include_soft: bool = False,
    allowlist: Optional[Iterable[str]] = None,
) -> RecognizerRegistry:
    """A new registry containing only the Swedish recognizers.

    Combine with Presidio's predefined recognizers by calling
    ``registry.load_predefined_recognizers(languages=[...])`` afterwards, which
    needs an NLP engine configured for those languages.
    """
    registry = RecognizerRegistry(supported_languages=list(languages))
    return add_swedish_recognizers(registry, languages, include_soft, allowlist)
