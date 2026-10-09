"""Write parity vectors: every test text with its detected entity types and verdict.

Usage: python scripts/make_vectors.py [OUTPUT]   (default: vectors.json)
"""

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "tests"))

from cases import all_texts  # noqa: E402

from svenska_pii import dom, hitta  # noqa: E402


def main() -> None:
    out = sys.argv[1] if len(sys.argv) > 1 else "vectors.json"
    vectors = []
    for text in all_texts():
        hits = hitta(text)
        vectors.append({"text": text, "types": sorted({h.entity_type for h in hits}), "stop": dom(hits).stop})
    with open(out, "w", encoding="utf-8") as f:
        json.dump(vectors, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{len(vectors)} vectors written to {out}")


if __name__ == "__main__":
    main()
