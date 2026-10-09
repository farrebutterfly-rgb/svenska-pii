# svenska-pii

[![test](https://github.com/farrebutterfly-rgb/svenska-pii/actions/workflows/test.yml/badge.svg)](https://github.com/farrebutterfly-rgb/svenska-pii/actions/workflows/test.yml) [![codeql](https://github.com/farrebutterfly-rgb/svenska-pii/actions/workflows/codeql.yml/badge.svg)](https://github.com/farrebutterfly-rgb/svenska-pii/actions/workflows/codeql.yml) [![supply-chain](https://github.com/farrebutterfly-rgb/svenska-pii/actions/workflows/supply-chain.yml/badge.svg)](https://github.com/farrebutterfly-rgb/svenska-pii/actions/workflows/supply-chain.yml)

Swedish PII recognizers with real check-digit validation. Pure Python, standard library only, with an optional [Microsoft Presidio](https://github.com/microsoft/presidio) integration.

> **Svenska:** `svenska-pii` hittar svenska personuppgifter i text: personnummer, samordningsnummer, organisationsnummer, bankgiro, plusgiro, svenskt IBAN och kontonummer, plus e-post, telefon, gatuadress och postnummer. Varje träff kontrolleras med kontrollsiffra, datum eller sammanhang, så datum, fakturanummer och belopp flaggas inte. `dom()` ger ett beslut för utgående text: stoppa vid hårda typer, eller när kontaktuppgifter förekommer i mängd som i ett register. Bara standardbiblioteket; Presidio är valfritt.

## What it detects

| Entity | What | Validation |
|---|---|---|
| `SE_PERSONNUMMER` | Personal identity number, `YYMMDD-NNNN`, `YYYYMMDDNNNN`, `+` for age 100+ | Luhn and calendar date |
| `SE_SAMORDNINGSNUMMER` | Coordination number (day + 60) | Luhn and calendar date after subtracting 60 |
| `SE_ORGNR` | Organisation number, optional `16` prefix | Luhn, and the month position must be 20 or higher (which separates it from a personnummer) |
| `SE_BANKGIRO` | Bankgiro, `NNN-NNNN` or `NNNN-NNNN` | Luhn and a context word (`bankgiro`, `bg`) |
| `SE_PLUSGIRO` | Plusgiro, `N...N-N` | Luhn and a context word (`plusgiro`, `pg`, `postgiro`) |
| `SE_IBAN` | Swedish IBAN, with or without spaces | ISO 7064 mod 97 |
| `SE_KONTONUMMER` | Clearing number plus account number | Context word (`konto`, `kontonummer`, `clearing`) |
| `EMAIL` | E-mail address | Pattern |
| `SE_PHONE` | Swedish phone number, `07x`, `08`, `+46` | Pattern |
| `SE_ADDRESS` | Street address such as `Storgatan 12` | Pattern (Swedish street suffixes) |
| `SE_POSTCODE` | Postcode followed by a town, `111 22 Stockholm` | Pattern |

The first seven are **hard** types. The last four are **soft** types.

## Why check-digit validation matters

A ten-digit pattern alone catches far too much: dates, invoice numbers, build numbers, order numbers and amounts. A detector that cries wolf gets switched off. Every hard type here is validated before it is reported:

```text
Fakturanummer 2026-001, förfaller 2026-10-30.      -> nothing
Beloppet är 34 720 kr och tillskottet 36 000 kr.   -> nothing
Commit 1234-5678 i repot, build 20260930-1422.     -> nothing
Nummer 850230-2386 finns inte.                     -> nothing (30 February is not a date)
Kundens personnummer är 850312-2387.               -> SE_PERSONNUMMER
```

Bankgiro, plusgiro and account numbers are short enough to collide with ordinary numbers even after a Luhn check, so they also require a context word in the 28 characters before the number.

## Install

```bash
pip install svenska-pii              # core, no dependencies
pip install "svenska-pii[presidio]"  # with the Presidio recognizers
```

## Usage

### Core API

```python
from svenska_pii import hitta, dom, maska

text = "Kundens personnummer är 850312-2387, mejla anna@exempel.se"

hits = hitta(text)
# [Traff(entity_type='SE_PERSONNUMMER', start=24, end=35, score=0.95, text='850312-2387'),
#  Traff(entity_type='EMAIL', start=43, end=58, score=0.9, text='anna@exempel.se')]

verdict = dom(hits)
# Dom(stop=True, reason={'SE_PERSONNUMMER': 1}, counts={'SE_PERSONNUMMER': 1, 'EMAIL': 1})

maska(text, hits)
# 'Kundens personnummer är [se_personnummer], mejla [email]'
```

The function names are Swedish (`hitta` = find, `dom` = verdict, `maska` = mask). English aliases `find`, `verdict` and `mask` are exported too.

Never report your own numbers with `allowlist`:

```python
hitta("Vårt org.nr 559000-1235", allowlist=["5590001235"])   # []
```

Separators are ignored, and a 12-digit form (with century or `16` prefix) matches its 10-digit form.

### Presidio

```python
from presidio_analyzer import AnalyzerEngine
from svenska_pii.presidio import swedish_registry, add_swedish_recognizers, PersonnummerRecognizer

# Use a recognizer directly, no NLP model needed
rec = PersonnummerRecognizer(supported_language="sv")
rec.analyze("pnr 850312-2387", entities=["SE_PERSONNUMMER"], nlp_artifacts=None)

# Or add all Swedish recognizers to an existing registry
analyzer = AnalyzerEngine()
add_swedish_recognizers(analyzer.registry, languages=["en"])
analyzer.analyze("Org.nr 556677-8899", language="en")

# Or start from a registry with only the Swedish recognizers
registry = swedish_registry(languages=["sv", "en"], include_soft=False)
```

Recognizers are registered for `sv` and `en` by default, since numbers do not depend on the language of the surrounding text. `include_soft=True` also adds `SE_PHONE`, `SE_ADDRESS` and `SE_POSTCODE` (Presidio already ships an e-mail recognizer). An `AnalyzerEngine` for `sv` needs an NLP engine configured for Swedish; the recognizers themselves do not use NLP artifacts.

## The verdict: hard types and registers

`dom()` decides whether text may leave, for example before it is sent to an external API or written to a log:

* Any **hard** hit stops the text.
* **Soft** hits are masked but only stop the text when it looks like a register: 4 or more contact details (e-mail, phone, address, postcode), or 2 or more contact details together with 4 or more names.
* **Names alone never stop.** Name recognition often mistakes product and tool names for people, so names only count together with contact details.

`dom()` understands `PERSON` hits from any NER model, so you can merge Presidio or spaCy name hits with `hitta()` output before calling it. Thresholds are parameters: `dom(hits, register_contact=4, register_mixed=(2, 4))`.

## Benchmark

`benchmarks/run.py` builds a corpus of 2,850 short Swedish business sentences: 1,350 with one identifier and 1,500 decoys with numbers that look similar but are not personal or account data (invoice and OCR numbers, dates, amounts, version and build numbers, numbers with a wrong check digit or an impossible date). It runs four setups on the same corpus:

* **presidio**: Presidio's predefined recognizers that work without an NLP model (pattern recognizers and the phone recognizer).
* **presidio>=0.5**: the same, keeping only detections with score 0.5 or higher.
* **svenska-pii**: `hitta()` on its own.
* **combined**: both, which is what you get after `add_swedish_recognizers()` on a default registry.

A positive counts as caught when any detection overlaps the identifier. A decoy counts as a false alarm when any detection overlaps its number.

| Positives caught | presidio | presidio>=0.5 | svenska-pii | combined |
|---|---:|---:|---:|---:|
| Personnummer | 100.0% | 5.2% | 100.0% | 100.0% |
| Samordningsnummer | 100.0% | 15.0% | 100.0% | 100.0% |
| Organisationsnummer | 100.0% | 6.3% | 100.0% | 100.0% |
| Bankgiro | 1.0% | 0.0% | 100.0% | 100.0% |
| Plusgiro | 72.7% | 0.0% | 100.0% | 100.0% |
| IBAN | 73.5% | 73.5% | 100.0% | 100.0% |
| **All, any type** | 78.4% | 15.0% | 100.0% | 100.0% |
| **All, right type** | 0.0% | 0.0% | 100.0% | 100.0% |
| **Decoys flagged** | 43.9% | 11.5% | 2.5% | 43.9% |

How to read it:

* **Presidio's high recall without a threshold is accidental.** Swedish numbers are caught as `US_DRIVER_LICENSE`, `US_BANK_NUMBER` or `PHONE_NUMBER`, so the same rules also flag 43.9% of the decoys, among them every date and build number. With a 0.5 threshold most of that noise disappears, and so do the Swedish identifiers. No setup without Swedish recognizers labels a Swedish identifier with its right type.
* **svenska-pii's 2.5% false alarms are real ambiguities**: a 10-digit OCR or reference number that happens to pass the Luhn check and has the shape of an organisation number, a build stamp like `20250410-1854` that is also a valid personnummer, and a number with a wrong check digit that still matches the phone pattern. The verdict from `dom()` stops 1.9% of the decoys, because phone hits are soft and do not stop on their own.
* **combined inherits Presidio's false alarms.** If you add the Swedish recognizers to a default registry, remove the US recognizers or raise their threshold for Swedish text.
* **The 100% figures measure coverage, not independent accuracy.** The corpus templates and the rules have the same author, so treat this as a regression benchmark for the formats listed above. Real documents contain formats this corpus does not, for example account numbers without context words, which svenska-pii does not report.

Personnummer in the corpus come from Skatteverket's published test numbers (`benchmarks/data/testpersonnummer.txt`, open data, CC0), which are never assigned to real people. Samordningsnummer have no published test list and are built from test number bases with 60 added to the day. Everything else is generated with a fixed seed, so the run is reproducible:

```bash
.venv/bin/python benchmarks/run.py --json benchmarks/results.json
```

## Limitations

* **Names** are not detected. That needs an NLP model (for example spaCy `sv_core_news_lg` through Presidio). Pass the resulting `PERSON` hits to `dom()`.
* **Context-dependent types** (bankgiro, plusgiro, account numbers) are only found when a context word precedes them. A bare account number in a table is not reported.
* **Soft types** are pattern based. Unusual address formats and foreign phone numbers are missed; some number sequences may look like phone numbers.
* **Century inference**: without an explicit century, a personnummer date is checked against 19YY. This only matters for 29 February in years such as 2000 written without century.
* Detection is not anonymisation. Use the verdict as a gate, not as a guarantee.

## Development and tests

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[presidio,dev]"
.venv/bin/python -m pytest
```

The Presidio tests call the recognizers directly with `nlp_artifacts=None`, so no spaCy model download is needed. They are skipped if `presidio-analyzer` is not installed. All numbers in the tests are computed with correct check digits. Personnummer come from Skatteverket's published test numbers, which are never assigned to real people.

`scripts/make_vectors.py` writes a JSON file of test texts with their detected types and verdict, for parity testing against ports in other languages:

```bash
.venv/bin/python scripts/make_vectors.py vectors.json
```

## License

MIT, copyright HolgerAI AB.
