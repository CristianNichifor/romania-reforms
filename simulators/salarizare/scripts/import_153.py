"""Import the law in force, so the simulator has a "today" to compare against.

    uv run python scripts/import_153.py

Reads sources/legea-153-2017.html (downloaded once from legislatie.just.ro) and writes
data/regimes/ro-153-2017.json.

Until now every comparison this project could draw was between two futures: the ministry's
draft, our patched version of it, and Denmark. The question a reader actually arrives with
— *what changes for me against what I am paid now* — had no answer, because the law in
force was not modelled. It was listed as blocked on "the consolidated annexes", which
turned out to mean nobody had gone and fetched them.

They are published. legislatie.just.ro serves the consolidated text with all annexes as
HTML tables — 176 of them, 124 carrying coefficients — and each row gives the position, the
study level, the 2022 base salary in lei, and the coefficient.

Two things worth knowing about the numbers:

  * **The lei amount is authoritative and the coefficient is derived.** Dividing one by the
    other gives 2500,6 to 2502,7 rather than a constant, because the law prints the
    coefficient multiplied by 100 and rounded to a whole number. The reference is the 2500
    lei minimum wage. Reconstructing the salary from the coefficient is therefore off by a
    few lei, which is a fact about the law's own rounding, recorded as a limitation.
  * **These are the 2022 figures**, the end of a phase-in that began in 2018 — and that
    was suspended and amended almost every year. They are the grid the framework law
    describes, not the payroll of 2026. The same caveat the draft carries about its own
    2031 destination applies here, pointing backwards.
"""

from __future__ import annotations

import gzip
import io
import json
import re
import unicodedata
import urllib.request
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
# Stored compressed: 6,0 MB of markup and 0,47 MB gzipped, in a repository whose tracked tree
# is capped at 60 MB and was within a tenth of it. Same reasoning, and the same on-disk shape,
# as impozit-teren's cod-fiscal-consolidat.html.gz.
SOURCE_FILE = ROOT / "sources/legea-153-2017.html.gz"
FRAME = ROOT / "data/frames/ro-153-2017.frame.json"
OUT = ROOT / "data/regimes/ro-153-2017.json"

URL = "https://legislatie.just.ro/Public/DetaliiDocument/190446"
UA = "public-pay-simulator/1.0 (+https://github.com/CristianNichifor/public-pay-simulator)"

SOURCE = "legea-153-2017"

# The reference the annexes are built on: salary / (coefficient / 100) lands on it.
REFERENCE = 2500

# The annexes carry the same occupational families as the 2026 draft, which is what makes
# the two comparable at all. Annex numbering is identical; only the wording differs.
FAMILY_BY_ANNEX = {
    "I": "I-invatamant",
    "II": "II-sanatate-asistenta-sociala",
    "III": "III-cultura",
    "IV": "IV-diplomatie",
    "V": "V-justitie",
    "VI": "VI-aparare-ordine-securitate",
    "VII": "VII-administratie-culte",
    "VIII": "VIII-administratie",
    "IX": "IX-demnitati",
}

ROMAN = "IX|VIII|VII|VI|IV|V|III|II|I"
ANNEX_HEADING = re.compile(rf"Anexa\s+nr\.\s+({ROMAN})\b", re.IGNORECASE)

# A coefficient column is named exactly that; a lei column says so too. Both headers are
# repeated down three header rows, which is why the match is on "contains".
COEFFICIENT = re.compile(r"coeficient", re.IGNORECASE)
LEI = re.compile(r"salariul de baz|lei", re.IGNORECASE)
STUDIES = re.compile(r"nivelul studiilor", re.IGNORECASE)
FUNCTION = re.compile(r"func[țt]ia|denumirea", re.IGNORECASE)


def download() -> str:
    """Fetch once and keep the file, so a re-import does not depend on the site being up."""
    if SOURCE_FILE.exists():
        with gzip.open(SOURCE_FILE, "rt", encoding="utf-8", errors="replace") as handle:
            return handle.read()
    print(f"downloading {URL} ...")
    request = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=180) as response:  # noqa: S310
        text = response.read().decode("utf-8", errors="replace")
    SOURCE_FILE.parent.mkdir(parents=True, exist_ok=True)
    # mtime pinned, so re-downloading unchanged markup produces an identical file rather than
    # a diff whose only content is the moment it was fetched.
    with gzip.GzipFile(SOURCE_FILE, "wb", compresslevel=9, mtime=0) as handle:
        handle.write(text.encode("utf-8"))
    return text


def slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text)).strip("-")[:44]


def annex_at(html: str, offset: int) -> str | None:
    """The last 'Anexa nr. X' heading before a table — the annex that table belongs to."""
    last = None
    for match in ANNEX_HEADING.finditer(html, 0, offset):
        last = match.group(1).upper()
    return last


def table_offsets(html: str) -> list[int]:
    return [m.start() for m in re.finditer(r"<table", html, re.IGNORECASE)]


def header_rows(table: pd.DataFrame) -> int:
    """How many leading rows repeat the header, which these tables do two or three times."""
    count = 0
    for i in range(min(4, len(table))):
        row = " ".join(str(v) for v in table.iloc[i].tolist())
        if FUNCTION.search(row) or STUDIES.search(row) or COEFFICIENT.search(row):
            count = i + 1
    return count


def classify(table: pd.DataFrame) -> dict[str, object] | None:
    """Which column is the job, and which columns are coefficients.

    Headers cannot be trusted on their own. Merged header cells make the parser repeat
    "Coeficient" across every column of a table, so a header match alone promotes the
    Nr. crt. column and the lei column to coefficients — which produced a grid running
    from 0,01 to 12,00, a 1:833 span, and salaries out by a quarter of a million lei.

    The source contains its own check: each coefficient is printed beside the salary it
    produces, and salary ÷ (coefficient ÷ 100) must come to the 2500 lei reference. So a
    column is a coefficient only if some other column stands in exactly that relation to
    it, on most of the rows. Wrong columns cannot survive that, and the arithmetic is the
    law's own rather than an assumption about layout.
    """
    head = header_rows(table)
    if head == 0 or len(table) <= head:
        return None
    labels: dict[int, str] = {}
    for c in range(table.shape[1]):
        parts = [str(table.iloc[i, c]) for i in range(head)]
        labels[c] = " ".join(p for p in parts if p and p != "nan")

    function_col = next((c for c, t in labels.items() if FUNCTION.search(t)), None)
    if function_col is None:
        return None

    body = range(head, len(table))
    numeric: dict[int, dict[int, float]] = {}
    for c in range(table.shape[1]):
        values = {r: number(table.iloc[r, c]) for r in body}
        kept = {r: v for r, v in values.items() if v is not None and v > 0}
        if kept:
            numeric[c] = kept

    pairs: dict[int, int] = {}
    for coef_col in numeric:
        if not COEFFICIENT.search(labels[coef_col]):
            continue
        best: tuple[int, int] | None = None
        for lei_col, lei_values in numeric.items():
            if lei_col == coef_col:
                continue
            agree = 0
            for r, coefficient in numeric[coef_col].items():
                lei = lei_values.get(r)
                if not lei or coefficient <= 0:
                    continue
                if abs(lei / (coefficient / 100) - REFERENCE) <= REFERENCE * 0.01:
                    agree += 1
            if agree and (best is None or agree > best[1]):
                best = (lei_col, agree)
        # Most of the rows, not merely one: a single coincidental ratio proves nothing.
        # Four fifths, not half: a column that only agrees on half its rows is a column
        # that happens to line up sometimes, and the other half would ship as salaries.
        if best and best[1] >= max(2, int(len(numeric[coef_col]) * 0.8)):
            pairs[coef_col] = best[0]

    if not pairs:
        return None
    studies_col = next((c for c, t in labels.items() if STUDIES.search(t)), None)
    return {
        "head": head,
        "function": function_col,
        "studies": studies_col,
        "coefficients": sorted(pairs),
        "pairs": pairs,
        "labels": labels,
    }


# Romanian prints thousands with a dot and decimals with a comma, and the annexes use both in
# adjacent columns: a coefficient reads "4,07" and the salary beside it reads "26.250". Replacing
# every comma with a dot and parsing turned that salary into 26,25 — a thousandfold error that
# did not become a wrong number, because the law's own check (salary over coefficient equals the
# reference) then failed and the table was dropped in silence. Annex V's magistrates, the only
# table where every salary is five figures, were missing from the regime entirely because of it.
THOUSANDS = re.compile(r"-?\d{1,3}(\.\d{3})+$")


def number(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(" ", "").replace("\xa0", "")
    # Groups of exactly three digits after a dot are separators, never decimals: the annexes
    # print coefficients to two places. The reference check downstream is what proves the
    # reading right — a mis-parse cannot satisfy the law's own arithmetic.
    if THOUSANDS.fullmatch(text):
        text = text.replace(".", "")
    else:
        text = text.replace(",", ".")
    if not re.fullmatch(r"-?\d+(\.\d+)?", text):
        return None
    return float(text)


def main() -> None:
    html = download()
    print(f"read {len(html):,} bytes\n")

    # The markup already in hand, not the file a second time: pandas cannot infer gzip for
    # read_html, and passing it a literal HTML string is deprecated. StringIO is both.
    tables = pd.read_html(io.StringIO(html))
    offsets = table_offsets(html)
    if len(offsets) != len(tables):
        print(f"  warning: {len(offsets)} <table> tags but {len(tables)} parsed tables")

    positions: list[dict] = []
    seen: set[str] = set()
    stats = {"tables": 0, "rows": 0, "skipped_tables": 0, "no_annex": 0,
             "checked": 0, "worst": 0.0, "unconfirmed": 0}

    for index, table in enumerate(tables):
        spec = classify(table)
        if spec is None:
            stats["skipped_tables"] += 1
            continue
        annex = annex_at(html, offsets[index]) if index < len(offsets) else None
        if annex is None:
            stats["no_annex"] += 1
            continue
        stats["tables"] += 1
        family = FAMILY_BY_ANNEX.get(annex, f"unknown-{annex}")

        for r in range(int(spec["head"]), len(table)):
            row = table.iloc[r]
            name = str(row.iloc[int(spec["function"])]).strip()
            if not name or name == "nan" or not re.search(r"[A-Za-zĂÂÎȘȚăâîșț]", name):
                continue

            variants = []
            for c in spec["coefficients"]:  # type: ignore[union-attr]
                value = number(row.iloc[c])
                if value is None or value <= 0:
                    continue
                # Published x100 and rounded; the schema wants the ratio itself.
                coefficient = value / 100

                # Every coefficient is checked against the salary printed beside it, row
                # by row rather than column by column. A column can agree on most rows and
                # still carry a few that are something else entirely, and those few would
                # ship as real salaries. Rows the law's own arithmetic does not confirm are
                # counted and dropped.
                printed = number(row.iloc[spec["pairs"][c]])  # type: ignore[index]
                if printed is None or abs(printed / coefficient - REFERENCE) > REFERENCE * 0.01:
                    stats["unconfirmed"] += 1
                    continue
                dims = {}
                label = str(spec["labels"][c]).strip()  # type: ignore[index]
                # Strip the repeated "Coeficient" so the dimension names the column, not
                # the measure: "Grad I", "Grad II".
                cleaned = re.sub(r"coeficient", "", label, flags=re.IGNORECASE).strip()
                if cleaned and len(spec["coefficients"]) > 1:  # type: ignore[arg-type]
                    dims["treapta"] = re.sub(r"\s+", " ", cleaned)[:40]
                variant = {
                    "value": coefficient,
                    "provenance": {
                        "source": SOURCE,
                        "locator": f"Anexa nr. {annex}, tabelul {index}, randul {r}, coloana {c}",
                        "confidence": "verbatim",
                    },
                }
                if dims:
                    variant["dims"] = dims
                variants.append(variant)

                stats["checked"] += 1
                stats["worst"] = max(stats["worst"], abs(printed / coefficient - REFERENCE))

            if not variants:
                continue

            studies = ""
            if spec["studies"] is not None:
                raw = str(row.iloc[int(spec["studies"])]).strip()  # type: ignore[arg-type]
                if raw and raw != "nan" and len(raw) <= 4:
                    studies = raw

            code = f"153.{annex}.{index}.{r}"
            if code in seen:
                continue
            seen.add(code)
            kind = "management" if re.search(r"director|sef|șef|rector|decan|inspector [sș]colar general|manager|presedinte|președinte", name, re.I) else "execution"
            position = {
                "code": code,
                "name": re.sub(r"\s+", " ", name)[:180],
                "family": family,
                "kind": kind,
                "variants": variants,
                "provenance": {
                    "source": SOURCE,
                    "locator": f"Anexa nr. {annex}, tabelul {index}, randul {r}",
                    "confidence": "verbatim",
                },
            }
            if studies:
                position["studyLevel"] = studies
            if kind == "execution":
                position["ladder"] = "gradatii"
            positions.append(position)
            stats["rows"] += 1

    frame = json.loads(FRAME.read_text(encoding="utf-8"))
    frame.pop("positionOverrides", None)
    regime = {**frame, "positions": positions}
    OUT.write_text(json.dumps(regime, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    values = [v["value"] for p in positions for v in p["variants"]]
    print(f"  tables used {stats['tables']}, skipped {stats['skipped_tables']}, no annex {stats['no_annex']}")
    print(f"  positions {len(positions):,}  variants {len(values):,}")
    print(f"  coefficient range {min(values):.2f} .. {max(values):.2f}  (raport 1:{max(values)/min(values):.2f})")
    print(f"  confirmed against the printed salary: {stats['checked']:,} coefficients, "
          f"worst deviation from {REFERENCE} lei: {stats['worst']:.2f}")
    print(f"  dropped as unconfirmed: {stats['unconfirmed']:,}")
    from collections import Counter
    for family, count in Counter(p["family"] for p in positions).most_common():
        print(f"    {family:34} {count:5,}")
    print(f"\nwrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
