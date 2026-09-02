"""Extract every study once, in parallel, so parsing them stops costing anything.

This is the file that makes the rest affordable. Reading tables out of one county's PDF takes
about thirty seconds, and writing a parser for a chamber takes fifteen or twenty attempts —
so the parser costs ten minutes of waiting and perhaps one minute of thinking. Extraction is
also entirely deterministic: the same PDF yields the same tables every time, and re-running
it after changing a regular expression proves nothing.

So it is done once, for the whole country, and written to a cache. Afterwards a parser reads
the cache in about fifty milliseconds and the loop becomes interactive.

What is stored is everything a reader has been shown to need, and no more:

    text     the flattened page as **pypdf** reads it, which is enough for the chambers
             whose tables have no merged cells. Deliberately not pdfplumber's text: the two
             break lines differently and are not substitutes. pdfplumber renders a rotated
             caption as "J E L C A" where pypdf keeps the value rows intact, and swapping
             one for the other turned Bacău from 85 communes into 10.
    tables   cells, and the geometry around them — the column x-edges and each row's box —
             because a merged cell is only recoverable from where things are printed
    words    each word with its box, which is how a commune label that the cell extractor
             dropped gets read back out of the page

Runs one process per core. The work is CPU-bound inside pdfminer and the documents are
independent, so the country takes about as long as its slowest county rather than the sum.

Usage:
    uv run python simulators/impozit-teren/scripts/extract_cache.py
    uv run python simulators/impozit-teren/scripts/extract_cache.py --only ALBA_2026.pdf
"""

from __future__ import annotations

import argparse
import gzip
import json
import multiprocessing
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STUDIES = ROOT / "sources" / "studies"
CACHE = ROOT / "cache"
# Where `ocr_cache.py` puts a study that had to be read off a photograph. The cache proper is
# derived and thrown away — CI rebuilds it from the PDFs — but an OCR reading cannot be rebuilt
# without tesseract, a language pack and a 17 MB download, and would not come back identical if
# it were. So it is kept as a source, committed, and read from here when the cache has nothing.
OCR = ROOT / "sources" / "ocr"
# The ruling-line strategy. These grids are drawn with real lines; the text strategy invents
# columns out of whitespace and tears every wrapped caption in half.
LINE_TABLE = {"vertical_strategy": "lines", "horizontal_strategy": "lines"}


def extract(path: Path) -> dict:
    import pdfplumber  # noqa: PLC0415  — imported per worker, not per document
    from pypdf import PdfReader  # noqa: PLC0415

    # Both readers over the same document: pypdf for the text the flattened-text dialects
    # were written against, pdfplumber for the geometry the merged-cell dialects need.
    try:
        flat = [(page.extract_text() or "") for page in PdfReader(str(path)).pages]
    except Exception:  # noqa: BLE001
        flat = []

    pages = []
    with pdfplumber.open(str(path)) as pdf:
        for number, page in enumerate(pdf.pages):
            tables = []
            for found in page.find_tables(LINE_TABLE):
                try:
                    cells = [[(c or "").strip() for c in row] for row in found.extract()]
                except Exception:  # noqa: BLE001
                    cells = []
                tables.append(
                    {
                        "bbox": [round(v, 1) for v in found.bbox],
                        "columns": sorted({round(c.bbox[0], 1) for c in found.columns}),
                        "rows": [[round(r.bbox[1], 1), round(r.bbox[3], 1)] for r in found.rows],
                        "cells": cells,
                    }
                )
            pages.append(
                {
                    "text": flat[number] if number < len(flat) else "",
                    "tables": tables,
                    # Compact on purpose: four numbers per word across sixty documents is the
                    # difference between a cache that fits on disk and one that does not.
                    "words": [
                        [w["text"], round(w["x0"], 1), round(w["x1"], 1), round(w["top"], 1)]
                        for w in page.extract_words()
                    ],
                }
            )
    return {"file": path.name, "pages": pages}


def cache_path(name: str) -> Path:
    return CACHE / f"{name}.json.gz"


def build(path: Path) -> tuple[str, float, str]:
    out = cache_path(path.name)
    if out.exists() and out.stat().st_mtime >= path.stat().st_mtime:
        return path.name, 0.0, "cached"
    started = time.time()
    try:
        document = extract(path)
    except Exception as exc:  # noqa: BLE001
        return path.name, time.time() - started, f"failed: {exc}"
    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False)
    return path.name, time.time() - started, "extracted"


def load(name: str) -> dict:
    """Read one study back. This is what every parser should call instead of opening a PDF."""
    path = cache_path(name)
    if not path.exists():
        path = OCR / f"{name}.json.gz"
    if not path.exists():
        raise SystemExit(
            f"missing {path}\n"
            "Run: uv run python simulators/impozit-teren/scripts/extract_cache.py"
        )
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", help="one filename, for iterating on a single chamber")
    parser.add_argument("--workers", type=int, default=max(1, (os.cpu_count() or 4) - 1))
    args = parser.parse_args()

    if not STUDIES.exists():
        raise SystemExit(
            f"missing {STUDIES}\n"
            "Run: uv run python simulators/impozit-teren/scripts/fetch_studies.py"
        )
    files = sorted(STUDIES.glob("*.pdf"))
    if args.only:
        files = [f for f in files if f.name == args.only]
        if not files:
            raise SystemExit(f"no study called {args.only}")

    started = time.time()
    with multiprocessing.Pool(args.workers) as pool:
        results = pool.map(build, files)
    elapsed = time.time() - started

    failed = [(name, status) for name, _, status in results if status.startswith("failed")]
    fresh = [(name, seconds) for name, seconds, status in results if status == "extracted"]
    size = sum(p.stat().st_size for p in CACHE.glob("*.json.gz")) if CACHE.exists() else 0
    print(f"{len(files)} studies, {len(fresh)} extracted, {len(results) - len(fresh)} cached")
    print(f"{elapsed:.1f} s wall on {args.workers} workers, cache {size / 1e6:.0f} MB")
    if fresh:
        slowest = sorted(fresh, key=lambda x: -x[1])[:3]
        print("slowest: " + ", ".join(f"{name} {seconds:.0f}s" for name, seconds in slowest))
    for name, status in failed:
        print(f"  {name}: {status}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
