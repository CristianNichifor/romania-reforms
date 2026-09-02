"""Turn a scanned study into the same cache entry a text PDF produces.

Some chambers publish photographs. `EXPERTIZE_TECUCI_01_03_2026.pdf` is 17 MB and 43 pages
with not one extractable character, and behind it is a quarter of Galați county — the city and
eighteen communes — in two perfectly ordinary tables. Argeș, Vâlcea and Brăila are the same.

**This is a source-preparation step, not part of the pipeline.** It runs by hand, on a machine
with tesseract and the Romanian language data, and it writes `cache/<name>.json.gz` — the same
file `extract_cache.py` writes for a document that carries its own text. From that point on
nothing downstream knows the difference, and CI reads the committed cache entry like any other.
Putting OCR in the pipeline would mean CI needed tesseract, a 2 MB language pack and a 17 MB
download to reproduce a file that never changes, and would make a byte-comparison depend on the
version of an OCR engine.

**What it does not do is guess.** Tesseract gets the tables right and the row numbering wrong —
`(_6 |: UDA a | 40` is Cudalbi — so this writes down what it read, noise and all, and leaves the
reading of it to the dialect, which can check names against the county roster. A cleanup pass
here would be a second place where the county's prices are decided, and an invisible one.

Usage:
    uv run python simulators/impozit-teren/scripts/ocr_cache.py sources/studies/FILE.pdf
    uv run python simulators/impozit-teren/scripts/ocr_cache.py FILE.pdf --dpi 400
"""

from __future__ import annotations

import argparse
import csv
import gzip
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_cache import OCR, ROOT  # noqa: E402

LANGUAGE = "ron"
# 300 dpi loses digits: at that size tesseract read Tecuci's vine price as 80.800, which is
# 30.800 on the page, and truncated three other rows to two columns. The cost of 400 is time.
DPI = 400
POINTS_PER_INCH = 72.0
# Tesseract's own confidence, on its own scale. Below this the word is usually a table rule
# read as punctuation, and carrying it costs more than dropping it.
MIN_CONFIDENCE = 30.0
# Both segmentation modes, on every page, keeping whichever tesseract is more sure of.
#
# Mode 6 reads the page as one upright block and takes a landscape table at face value, which
# turns three hundred words into punctuation. Mode 1 detects orientation and fixes those — and
# on this study it also decided the extravilan table was upside down and read `30.800` as
# `008'0£`. Neither mode is right for every page and there is no way to know in advance which
# page is which, so both run and the mean confidence decides. A page read the wrong way up
# scores far below the same page read the right way up, which is the whole signal needed.
MODES = (6, 1)


SEARCH = (
    Path("/usr/share/tessdata"),
    Path("/usr/share/tesseract-ocr/tessdata"),
    Path.home() / ".local/share/tessdata",
    Path(__file__).resolve().parent.parent / "tessdata",
)


def find(name: str) -> Path | None:
    return next((where / name for where in SEARCH if (where / name).exists()), None)


def tessdata(workspace: Path) -> Path | None:
    """A tessdata directory holding both the language data and tesseract's own configs.

    These are usually the same directory and here they are not: the Romanian pack is fetched
    into the repository while `configs/tsv` — the recipe that makes tesseract emit word
    coordinates rather than a wall of text — ships with the distribution's tesseract. Neither
    `TESSDATA_PREFIX` nor `--tessdata-dir` will take one from each, so this assembles a
    directory that has both and throws it away afterwards.
    """
    language = find(f"{LANGUAGE}.traineddata")
    configs = find("configs")
    if language is None or configs is None:
        return None
    combined = workspace / "tessdata"
    combined.mkdir()
    (combined / language.name).symlink_to(language.resolve())
    (combined / "configs").symlink_to(configs.resolve())
    # Page-segmentation mode 1 detects orientation, and to do that it needs the orientation
    # model beside the language one. Several pages of this study are landscape; without it they
    # read as three hundred words of punctuation and are silently empty.
    orientation = find("osd.traineddata")
    if orientation is not None:
        (combined / orientation.name).symlink_to(orientation.resolve())
    return combined


def render(pdf: Path, into: Path, dpi: int) -> list[Path]:
    subprocess.run(
        ["pdftoppm", "-r", str(dpi), "-gray", "-png", str(pdf), str(into / "page")],
        check=True,
    )
    return sorted(into.glob("page-*.png"))


def read_page(image: Path, dpi: int, environment: dict) -> dict:
    """One page, read every way, as the reading tesseract was most confident about."""
    best, best_score = {"text": "", "tables": [], "words": []}, -1.0
    for mode in MODES:
        page, score = read_once(image, dpi, environment, mode)
        if score > best_score:
            best, best_score = page, score
    return best


def read_once(image: Path, dpi: int, environment: dict, mode: int) -> tuple[dict, float]:
    """One page under one segmentation mode, with tesseract's mean confidence in it."""
    finished = subprocess.run(
        ["tesseract", str(image), "stdout", "-l", LANGUAGE, "--psm", str(mode), "tsv"],
        check=True,
        capture_output=True,
        text=True,
        env=environment,
    )
    scale = POINTS_PER_INCH / dpi
    confidences: list[float] = []
    words: list[list] = []
    lines: dict[tuple[int, int, int], list[tuple[int, str]]] = {}

    reader = csv.DictReader(finished.stdout.splitlines(), delimiter="\t", quoting=csv.QUOTE_NONE)
    for row in reader:
        text = (row.get("text") or "").strip()
        if not text:
            continue
        try:
            confidence = float(row["conf"])
            left, top, width = int(row["left"]), int(row["top"]), int(row["width"])
        except (KeyError, TypeError, ValueError):
            continue
        confidences.append(confidence)
        if confidence < MIN_CONFIDENCE:
            continue
        words.append(
            [
                text,
                round(left * scale, 1),
                round((left + width) * scale, 1),
                round(top * scale, 1),
            ]
        )
        key = (int(row["block_num"]), int(row["par_num"]), int(row["line_num"]))
        lines.setdefault(key, []).append((left, text))

    text = "\n".join(
        " ".join(word for _, word in sorted(parts)) for _, parts in sorted(lines.items())
    )
    # Mean confidence over every word tesseract attempted, not only the ones kept: a page read
    # upside down produces a great many things it is not sure about, and dropping those first
    # would hide exactly the evidence that the reading is wrong.
    score = sum(confidences) / len(confidences) if confidences else 0.0
    # No `tables`: a photograph has no ruling lines to find, and an empty list is the honest
    # answer rather than a table reconstructed from guesses about where the columns were.
    return {"text": text, "tables": [], "words": words}, score


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path, help="the scanned study")
    parser.add_argument("--dpi", type=int, default=DPI)
    parser.add_argument("--force", action="store_true", help="overwrite an existing cache entry")
    args = parser.parse_args()

    pdf = args.pdf if args.pdf.exists() else ROOT / args.pdf
    if not pdf.exists():
        print(f"no such file: {args.pdf}", file=sys.stderr)
        return 1
    for tool in ("pdftoppm", "tesseract"):
        if not shutil.which(tool):
            print(f"{tool} is not installed", file=sys.stderr)
            return 1

    out = OCR / f"{pdf.name}.json.gz"
    if out.exists() and not args.force:
        print(f"{out.name} already cached; pass --force to redo it")
        return 0

    with tempfile.TemporaryDirectory() as workspace:
        environment = dict(**__import__("os").environ)
        found = tessdata(Path(workspace))
        if found is None:
            print(
                f"no {LANGUAGE}.traineddata found. Fetch it into "
                "simulators/impozit-teren/tessdata:\n  curl -sLO "
                "https://github.com/tesseract-ocr/tessdata_fast/raw/main/ron.traineddata",
                file=sys.stderr,
            )
            return 1
        environment["TESSDATA_PREFIX"] = str(found)
        images = render(pdf, Path(workspace), args.dpi)
        print(f"{pdf.name}: {len(images)} pages at {args.dpi} dpi, reading with tesseract")
        pages = []
        for number, image in enumerate(images, start=1):
            pages.append(read_page(image, args.dpi, environment))
            print(f"  p{number}: {len(pages[-1]['words'])} words", end="\r", flush=True)

    characters = sum(len(page["text"]) for page in pages)
    if not characters:
        print("\nnothing read; the pages may be blank or the render failed", file=sys.stderr)
        return 1

    out.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(out, "wt", encoding="utf-8") as handle:
        json.dump({"file": pdf.name, "pages": pages}, handle, ensure_ascii=False)
    print(f"\nWrote {out} — {len(pages)} pages, {characters:,} characters")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
