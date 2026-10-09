"""Benchmark: Swedish identifiers in ordinary business text.

Compares three setups on the same generated corpus:

  presidio      Presidio's predefined recognizers that work without an NLP model
                (pattern recognizers plus the phone recognizer). Names, places and
                organisations come from spaCy NER and are out of scope here.
  presidio>=0.5 The same, keeping only detections with score 0.5 or higher.
  svenska-pii   svenska_pii.hitta on its own.
  combined      Both, as you get after add_swedish_recognizers() on a default
                Presidio registry.

Positives are sentences that contain one Swedish identifier. A positive counts as
caught when any detection overlaps the identifier. Decoys are sentences with numbers
that look similar but are not personal or account data (invoice and OCR numbers,
dates, amounts, versions, numbers with a wrong check digit or an impossible date).
A decoy counts as a false alarm when any detection overlaps the number.

Personnummer come from Skatteverket's published test numbers (benchmarks/data).
Everything else is generated with a fixed seed, so the run is reproducible.

Usage: python benchmarks/run.py [--seed 2026] [--json results.json]
"""

from __future__ import annotations

import argparse
import json
import os
import random
import string
import sys
import time
from collections import defaultdict
from typing import Callable, Dict, List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from svenska_pii import dom, hitta  # noqa: E402

Span = Tuple[int, int]


# ---------------------------------------------------------------- generators


def luhn_digit(payload: str) -> str:
    s = 0
    for i, c in enumerate(reversed(payload)):
        d = int(c)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        s += d
    return str((10 - s % 10) % 10)


def load_test_pnr() -> List[str]:
    path = os.path.join(HERE, "data", "testpersonnummer.txt")
    with open(path, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]


def fmt_pnr(p12: str, rnd: random.Random) -> str:
    short = p12[2:]
    form = rnd.choice(["10-", "12-", "12", "10"])
    if form == "10-":
        return short[:6] + "-" + short[6:]
    if form == "12-":
        return p12[:8] + "-" + p12[8:]
    if form == "12":
        return p12
    return short


def samordning(p12: str) -> str:
    day = int(p12[6:8]) + 60
    body = p12[2:6] + f"{day:02d}" + p12[8:11]
    full = body + luhn_digit(body)
    return full[:6] + "-" + full[6:]


def orgnr(rnd: random.Random) -> str:
    first = rnd.choice("25789")
    nine = first + str(rnd.randint(0, 9)) + str(rnd.randint(2, 9)) + "".join(rnd.choices(string.digits, k=6))
    ten = nine + luhn_digit(nine)
    form = rnd.choice(["-", "", "16"])
    if form == "-":
        return ten[:6] + "-" + ten[6:]
    if form == "16":
        return "16" + ten
    return ten


def bankgiro(rnd: random.Random) -> str:
    body = "".join(rnd.choices(string.digits, k=rnd.choice([6, 7])))
    body = str(rnd.randint(1, 9)) + body[1:]
    full = body + luhn_digit(body)
    return full[:-4] + "-" + full[-4:]


def plusgiro(rnd: random.Random) -> str:
    body = str(rnd.randint(1, 9)) + "".join(rnd.choices(string.digits, k=rnd.randint(4, 6)))
    return body + "-" + luhn_digit(body)


def iban_se(rnd: random.Random) -> str:
    bank = rnd.choice(["500", "600", "800", "300", "120", "957"])
    bban = bank + "".join(rnd.choices(string.digits, k=17))
    num = int(bban + "2814" + "00")  # S=28, E=14
    check = 98 - num % 97
    iban = f"SE{check:02d}{bban}"
    if rnd.random() < 0.5:
        return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))
    return iban


def ocr(rnd: random.Random) -> str:
    body = str(rnd.randint(1, 9)) + "".join(rnd.choices(string.digits, k=rnd.randint(7, 15)))
    return body + luhn_digit(body)


def wrong_check(p: str) -> str:
    return p[:-1] + str((int(p[-1]) + rnd_global.randint(1, 9)) % 10)


rnd_global = random.Random(0)


POS_TEMPLATES = {
    "SE_PERSONNUMMER": [
        "Kundens personnummer är {x}.",
        "Sökande: {x}, inflyttad 2021.",
        "Ange {x} på blanketten för hemförsäkringen.",
        "Firmatecknare med pnr {x} har skrivit under.",
        "Patienten {x} har tid på torsdag.",
        "Uppgifter om den anställde ({x}) finns i bilagan.",
    ],
    "SE_SAMORDNINGSNUMMER": [
        "Samordningsnummer {x} gäller för konsulten.",
        "Hen saknar personnummer men har {x}.",
        "Ange id {x} vid registreringen.",
    ],
    "SE_ORGNR": [
        "Motpart: Byggbolaget AB, org.nr {x}.",
        "Leverantören ({x}) fakturerar månadsvis.",
        "Organisationsnummer {x} ska stå på fakturan.",
        "Avtalet tecknas med {x} i Solna.",
    ],
    "SE_BANKGIRO": [
        "Betala till bankgiro {x} senast fredag.",
        "Bg {x}, märk betalningen med fakturanumret.",
        "Vårt bankgironummer är {x}.",
    ],
    "SE_PLUSGIRO": [
        "Plusgiro {x} tar emot gåvor.",
        "Betala via pg {x}.",
        "Plusgironummer: {x}",
    ],
    "SE_IBAN": [
        "IBAN {x} till kontot i Stockholm.",
        "Utbetalning till {x}.",
        "Vänligen använd IBAN: {x}",
    ],
}

DECOY_TEMPLATES: List[Tuple[str, Callable[[random.Random], str]]] = [
    ("Fakturanummer {x}, förfaller om 30 dagar.", lambda r: f"{r.randint(2024, 2027)}-{r.randint(1, 9999):04d}"),
    ("Order {x} skickades i går.", lambda r: f"{r.randint(1000, 9999)}-{r.randint(1000, 9999)}"),
    ("Mötet är {x} kl 14.30.", lambda r: f"{r.randint(2025, 2027)}-{r.randint(1, 12):02d}-{r.randint(1, 28):02d}"),
    ("Beloppet är {x} kr inklusive moms.", lambda r: f"{r.randint(1, 999)} {r.randint(0, 999):03d}"),
    ("Ange OCR {x} vid betalning.", ocr),
    ("Referens {x} i ärendet.", ocr),
    ("Artikel {x} är slut i lager.", lambda r: bankgiro(r)),
    ("Version {x} släpptes.", lambda r: plusgiro(r)),
    ("Build {x} gick igenom.", lambda r: f"{r.randint(2025, 2026)}{r.randint(1, 12):02d}{r.randint(1, 28):02d}-{r.randint(1000, 2359)}"),
    ("Kontrollera nummer {x}, det verkar fel.", lambda r: wrong_check(fmt_pnr(r.choice(TEST_PNR), r))),
    ("Löpnummer {x} saknas i registret.", lambda r: f"{r.randint(10, 99)}{r.randint(13, 19)}{r.randint(1, 28):02d}-{r.randint(1000, 9999)}"),
    ("Leverans {x} st till lagret.", lambda r: f"{r.randint(1000, 99999)}"),
    ("Ärende {x} är stängt.", lambda r: f"ABC-{r.randint(100, 999)}-{r.randint(1000, 9999)}"),
    ("Kortet slutar på {x}.", lambda r: f"{r.randint(1000, 9999)}"),
    ("Mät {x} mm i ritningen.", lambda r: f"{r.randint(100, 9999)}x{r.randint(100, 9999)}"),
]

TEST_PNR: List[str] = []


def build_corpus(seed: int, n_pos: Dict[str, int], n_decoy: int):
    rnd = random.Random(seed)
    rnd_global.seed(seed + 1)
    items = []  # (kind, label, text, span)
    gen = {
        "SE_PERSONNUMMER": lambda: fmt_pnr(rnd.choice(TEST_PNR), rnd),
        "SE_SAMORDNINGSNUMMER": lambda: samordning(rnd.choice(TEST_PNR)),
        "SE_ORGNR": lambda: orgnr(rnd),
        "SE_BANKGIRO": lambda: bankgiro(rnd),
        "SE_PLUSGIRO": lambda: plusgiro(rnd),
        "SE_IBAN": lambda: iban_se(rnd),
    }
    for typ, n in n_pos.items():
        for _ in range(n):
            x = gen[typ]()
            tpl = rnd.choice(POS_TEMPLATES[typ])
            a = tpl.index("{x}")
            items.append(("pos", typ, tpl.replace("{x}", x), (a, a + len(x))))
    for _ in range(n_decoy):
        tpl, g = rnd.choice(DECOY_TEMPLATES)
        x = g(rnd)
        a = tpl.index("{x}")
        label = tpl.split(" {x}")[0]
        items.append(("decoy", label, tpl.replace("{x}", x), (a, a + len(x))))
    return items


# ------------------------------------------------------------------ systems


def make_presidio():
    from presidio_analyzer import RecognizerRegistry
    from presidio_analyzer.predefined_recognizers import SpacyRecognizer

    reg = RecognizerRegistry()
    reg.load_predefined_recognizers(languages=["en"])
    recs = [r for r in reg.recognizers if not isinstance(r, SpacyRecognizer)]

    def run(text: str) -> List[Tuple[str, Span, float]]:
        out = []
        for r in recs:
            for res in r.analyze(text, r.supported_entities, None) or []:
                out.append((res.entity_type, (res.start, res.end), res.score))
        return out

    return run


def svenska(text: str) -> List[Tuple[str, Span, float]]:
    return [(h.entity_type, (h.start, h.end), h.score) for h in hitta(text)]


def overlaps(a: Span, b: Span) -> bool:
    return a[0] < b[1] and b[0] < a[1]


# --------------------------------------------------------------------- main


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    TEST_PNR.extend(load_test_pnr())
    n_pos = {
        "SE_PERSONNUMMER": 400,
        "SE_SAMORDNINGSNUMMER": 100,
        "SE_ORGNR": 300,
        "SE_BANKGIRO": 200,
        "SE_PLUSGIRO": 150,
        "SE_IBAN": 200,
    }
    corpus = build_corpus(args.seed, n_pos, 1500)

    presidio = make_presidio()
    systems = {
        "presidio": presidio,
        "presidio>=0.5": lambda t: [d for d in presidio(t) if d[2] >= 0.5],
        "svenska-pii": svenska,
        "combined": lambda t: presidio(t) + svenska(t),
    }

    res: Dict[str, dict] = {}
    for name, fn in systems.items():
        caught = defaultdict(int)
        typed = defaultdict(int)
        total = defaultdict(int)
        alarms = defaultdict(int)
        dtotal = defaultdict(int)
        alarm_types = defaultdict(int)
        t0 = time.perf_counter()
        for kind, label, text, span in corpus:
            dets = [d for d in fn(text) if overlaps(d[1], span)]
            if kind == "pos":
                total[label] += 1
                caught[label] += bool(dets)
                typed[label] += any(d[0] == label for d in dets)
            else:
                dtotal[label] += 1
                if dets:
                    alarms[label] += 1
                    for d in {d[0] for d in dets}:
                        alarm_types[d] += 1
        ms = (time.perf_counter() - t0) * 1000 / len(corpus)
        res[name] = {
            "recall": {k: caught[k] / total[k] for k in total},
            "caught": dict(caught),
            "typed": dict(typed),
            "positives": dict(total),
            "false_alarms": dict(alarms),
            "decoys": dict(dtotal),
            "false_alarm_types": dict(sorted(alarm_types.items(), key=lambda kv: -kv[1])),
            "ms_per_text": ms,
        }

    n_p = sum(n_pos.values())
    n_d = len(corpus) - n_p
    print(f"Corpus: {n_p} positives, {n_d} decoys, seed {args.seed}\n")
    print(f"{'positives caught':24}" + "".join(f"{s:>14}" for s in systems))
    for typ in n_pos:
        print(f"{typ:24}" + "".join(f"{res[s]['recall'][typ]:>13.1%} " for s in systems))
    print(f"{'all positives':24}" + "".join(f"{sum(res[s]['caught'].values()) / n_p:>13.1%} " for s in systems))
    print(f"{'  with the right type':24}" + "".join(f"{sum(res[s]['typed'].values()) / n_p:>13.1%} " for s in systems))
    print()
    labels = sorted({lab for kind, lab, _, _ in corpus if kind == "decoy"})
    print(f"{'decoy':24}" + "".join(f"{s:>14}" for s in systems))
    for lab in labels:
        print(f"{lab[:24]:24}" + "".join(f"{res[s]['false_alarms'].get(lab, 0) / res[s]['decoys'][lab]:>13.1%} " for s in systems))
    print(f"{'decoys flagged':24}" + "".join(f"{sum(res[s]['false_alarms'].values()) / n_d:>13.1%} " for s in systems))
    print(f"{'ms per text':24}" + "".join(f"{res[s]['ms_per_text']:>13.2f} " for s in systems))
    print()
    for s in systems:
        top = list(res[s]["false_alarm_types"].items())[:6]
        print(f"false alarms by type, {s}: {top}")

    stopped = sum(dom(hitta(text)).stop for kind, _, text, _ in corpus if kind == "decoy")
    print(f"\nsvenska-pii verdict: {stopped} of {n_d} decoys ({stopped / n_d:.1%}) would be stopped (hard hit or register)")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump({"seed": args.seed, "positives": n_p, "decoys": n_d, "results": res}, f, indent=2)


if __name__ == "__main__":
    main()
