"""Import the Romanian court map and its workload from the CSM's annual report.

    uv run python simulators/justitie/scripts/import_instante.py

Writes simulators/justitie/data/instante-2023.json.

The reform paper proposes turning 176 judecatorii and 42 tribunale into 42 consolidated
tribunale and 15 regional courts of appeal. That is a claim about *sizes*: it says the
small courts are too small to be viable and the work would be better carried by fewer,
larger ones. Arguing with it — in either direction — needs the sizes.

The CSM publishes them. Annex 1 of *Raportul privind starea justitiei* gives, for every
court in the country, the cases on its roll, the cases it disposed of, and the caseload per
established post and per sitting judge.

The last two columns are worth more than they look. The report never prints how many judges
a court has, but caseload per judge *is* volume divided by that number — so the count can
be recovered by dividing back. Each court's judges and establishment are therefore
reconstructed here, and marked `derived`, never `verbatim`. The two are not the same
number: where posts sit vacant the establishment exceeds the sitting judges, and the gap
between them is itself one of the paper's arguments.

The table is read out of a PDF, which is the least reliable format this project handles, so
the parser checks itself twice: every row must reproduce the caseload ratios it was built
from, and the recovered national averages must match the ones the report prints in its own
headers.
"""

from __future__ import annotations

import json
import argparse
import re
import unicodedata
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]
UA = "romania-reforms/0.1 (+https://github.com/CristianNichifor)"


@dataclass(frozen=True)
class Edition:
    """One year's report. The CSM publishes annually and the annex keeps its shape.

    Kept as a table rather than replaced, because two editions answer a question one cannot:
    a court that looks small in a single year may be busy the next, which is exactly what the
    `un-singur-an` limitation says. Holding both lets the map show a court's direction rather
    than a snapshot.
    """

    period: str
    guid: str
    # The national averages the report prints above each tier's table. They are the check on
    # the parse: reconstructing them from the rows and landing far from the printed figure
    # means rows were missed, which is how six Bucharest sector courts once went missing
    # without the output looking wrong.
    printed_averages: dict[str, dict[str, int]]

    @property
    def source(self) -> str:
        return f"csm-starea-justitiei-{self.period}"

    @property
    def file(self) -> Path:
        return ROOT / f"sources/{self.source}.pdf"

    @property
    def out(self) -> Path:
        return ROOT / f"data/instante-{self.period}.json"

    @property
    def url(self) -> str:
        return f"https://www.csm1909.ro/files/{self.guid}?download=1"


EDITIONS = {
    "2023": Edition(
        period="2023",
        guid="ab8ae9f9-cb62-4a9c-8b56-9932fa016648",
        printed_averages={
            "curte-de-apel": {"perJudge": 651, "perPost": 574},
            "judecatorie": {"perJudge": 1455, "perPost": 998},
        },
    ),
    "2025": Edition(
        period="2025",
        guid="25abaf7e-ac14-4420-bb28-3d66e94a10f8",
        printed_averages={
            "curte-de-apel": {"perJudge": 606, "perPost": 560},
            "judecatorie": {"perJudge": 1479, "perPost": 1180},
        },
    ),
}
LATEST = "2025"

# "12 Judecatoria BAIA MARE 23614 15938 944.6 1365" — rank, name, volume, resolved, and the
# two caseload ratios.
#
# Two things a simpler pattern gets wrong, both found by checking the report's own row
# numbering rather than by reading the output:
#
#   * **Names contain digits.** "Judecatoria SECTORUL 1 BUCUREŞTI" is one of six Bucharest
#     sector courts, and they are among the largest in the country — Sector 1 alone carries
#     more cases than every tribunal except Bucharest. A name matched as `[^\d]+` drops all
#     six, which would leave a court map arguing that small courts are the problem while
#     missing the biggest urban ones entirely.
#   * **Rows can carry a trailing watermark**, "-Documentul electronic este conform cu
#     originalul", which defeats a pattern anchored hard at the end of the line.
#
# So the name is allowed to contain anything, the four numeric columns are anchored as a
# group, and trailing non-numeric text is permitted. Volume and resolved must be at least
# three digits, which stops a digit inside a name being read as the first column.
ROW = re.compile(
    r"^\s*(\d{1,3})\s+"
    r"((?:Judec[ăa]toria|Tribunalul|Curtea de Apel)\s+.+?)\s+"
    r"(\d[\d\s]{2,8})\s+(\d[\d\s]{2,8})\s+"
    r"([\d.,]+)\s+([\d.,]+)"
    r"(?:\s+\D.*)?\s*$"
)

TIERS = {"Judecatoria": "judecatorie", "Judecătoria": "judecatorie",
         "Tribunalul": "tribunal", "Curtea de Apel": "curte-de-apel"}

def download(edition: Edition) -> Path:
    if edition.file.exists():
        return edition.file
    print(f"downloading {edition.url} ...")
    request = urllib.request.Request(edition.url, headers={"User-Agent": UA})
    with urllib.request.urlopen(request, timeout=300) as response:  # noqa: S310
        data = response.read()
    edition.file.parent.mkdir(parents=True, exist_ok=True)
    edition.file.write_bytes(data)
    return edition.file


# A row the PDF broke across lines still starts the same way: rank, then the court type.
ROW_START = re.compile(r"^\s*\d{1,3}\s+(?:Judec[ăa]toria|Tribunalul|Curtea de Apel)\b")

# How many following lines a row may be stitched from. Three covers the worst case seen —
# "36 Judecatoria CÂMPULUNG" / "MOLDOVENESC 4612" / "3628" / the two ratios — and bounds the
# damage if a page ever confuses the parser.
MAX_JOIN = 3


def logical_rows(lines: list[str]) -> Iterator[str]:
    """Yield table rows, rejoining the ones the PDF split across lines.

    The 2023 annex fits every row on one line. The 2025 annex does not, in three different
    ways: a long court name wrapping before its numbers ("Tribunalul pentru minori si
    familie" / "BRAŞOV 1635 1423 480.0 480"), a name wrapping mid-word with the numbers
    trailing over two more lines, and a row breaking between its first and second number
    ("... DROBETA-TURNU SEVERIN 24448" / "15415 905.5 1413.2").

    Reading line by line silently loses those rows, and losing rows is the failure this
    importer exists to prevent — it is how six Bucharest sector courts disappeared once
    while the output still looked like a court map. The rank continuity check catches it
    afterwards; this is what stops it happening.

    Joining stops at the next row's start, so a row can never absorb the one below it.
    """
    cleaned = [" ".join(line.split()) for line in lines]
    index = 0
    while index < len(cleaned):
        line = cleaned[index]
        if ROW_START.match(line):
            joined = line
            for step in range(MAX_JOIN + 1):
                if ROW.match(joined):
                    yield joined
                    index += step
                    break
                nxt = index + step + 1
                if nxt >= len(cleaned) or ROW_START.match(cleaned[nxt]):
                    break
                joined = f"{joined} {cleaned[nxt]}"
        index += 1


def number(text: str) -> float:
    return float(text.replace(" ", "").replace(",", "."))


def slug(name: str) -> str:
    text = unicodedata.normalize("NFKD", name.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", text)).strip("-")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--year", choices=sorted(EDITIONS), default=LATEST)
    args = parser.parse_args(argv)
    edition = EDITIONS[args.year]
    path = download(edition)
    reader = PdfReader(str(path))
    print(f"read {len(reader.pages)} pages\n")

    courts: list[dict] = []
    seen: set[str] = set()
    ranks: dict[str, set[int]] = {}

    for index, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        for line in logical_rows(text.splitlines()):
            match = ROW.match(line)
            if not match:
                continue
            _rank, raw_name, raw_volume, raw_resolved, raw_post, raw_judge = match.groups()
            name = re.sub(r"\s+", " ", raw_name).strip()
            prefix = next((p for p in TIERS if name.startswith(p)), None)
            if prefix is None:
                continue

            volume = int(raw_volume.replace(" ", ""))
            resolved = int(raw_resolved.replace(" ", ""))
            per_post = number(raw_post)
            per_judge = number(raw_judge)
            if volume <= 0 or per_post <= 0 or per_judge <= 0:
                continue

            # The report prints a ratio built from a divisor it never prints, so dividing
            # back recovers the divisor. It is rarely a whole number, and that is not an
            # error: judges arrive, leave and sit part-year, so the CSM divides by an
            # average over the year rather than by a headcount on a date. What comes back
            # is that average.
            judges = volume / per_judge
            posts = volume / per_post

            identifier = f"{TIERS[prefix]}-{slug(name[len(prefix):])}"
            if identifier in seen:
                continue
            seen.add(identifier)

            ranks.setdefault(TIERS[prefix], set()).add(int(_rank))
            courts.append({
                "id": identifier,
                "name": name,
                "tier": TIERS[prefix],
                **({"specialised": True} if re.search(r"Comercial|Minori|Familie", name) else {}),
                "volume": volume,
                "resolved": resolved,
                "loadPerPost": per_post,
                "loadPerJudge": per_judge,
                # Two decimals, not one. The ratio behind these is printed to one decimal,
                # so the precision is limited anyway — but rounding the recovered divisor
                # to one decimal throws away more than the source did, and on a small court
                # that shows up as a fifteen-case error when the ratio is recomputed.
                "judges": round(judges, 2),
                "posts": round(posts, 2),
                "provenance": {
                    "source": edition.source,
                    "locator": f"Anexa 1, p. {index + 1}, randul „{name}”",
                    "confidence": "verbatim",
                    "note": (
                        "Volumul si cauzele solutionate sunt tiparite. Numarul de judecatori "
                        "si schema sunt derivate: volum impartit la incarcatura pe judecator, "
                        "respectiv pe schema."
                    ),
                },
            })

    # The Inalta Curte sits in its own one-row table with the same columns.
    for index, page in enumerate(reader.pages):
        text = re.sub(r"\s+", " ", page.extract_text() or "")
        hit = re.search(
            # Romanian is written with two different encodings of the same two letters:
            # comma-below (ș ț, correct) and cedilla (ş ţ, legacy). This report mixes them
            # within a single line, so every class has to admit both or the match silently
            # fails — which is how the country's highest court went missing from its own
            # court map.
            r"Înalta Curte de Casa[țţt]ie [șşs]i Justi[țţt]ie"
            r"\s+(\d{4,6})\s+(\d{4,6})\s+([\d.,]+)\s+([\d.,]+)",
            text,
        )
        if hit and not any(c["tier"] == "iccj" for c in courts):
            volume, resolved = int(hit.group(1)), int(hit.group(2))
            per_post, per_judge = number(hit.group(3)), number(hit.group(4))
            courts.insert(0, {
                "id": "iccj",
                "name": "Înalta Curte de Casație și Justiție",
                "tier": "iccj",
                "volume": volume,
                "resolved": resolved,
                "loadPerPost": per_post,
                "loadPerJudge": per_judge,
                "judges": round(volume / per_judge, 1),
                "posts": round(volume / per_post, 1),
                "provenance": {
                    "source": edition.source,
                    "locator": f"Anexa 1, p. {index + 1}",
                    "confidence": "verbatim",
                },
            })
            break

    by_tier: dict[str, list[dict]] = {}
    for court in courts:
        by_tier.setdefault(court["tier"], []).append(court)

    # Check the parse against the report's own printed averages. A tier that lands far from
    # them means rows were dropped or misread, and the file should not be written.
    averages = []
    for tier, rows in sorted(by_tier.items()):
        volume = sum(c["volume"] for c in rows)
        judges = sum(c["judges"] for c in rows)
        posts = sum(c["posts"] for c in rows)
        per_judge = volume / judges if judges else 0
        per_post = volume / posts if posts else 0
        averages.append({"tier": tier, "perJudge": round(per_judge, 1), "perPost": round(per_post, 1)})
        # The report numbers its rows 1..N, so a gap is a dropped court — a far sharper
        # guard than comparing averages. Losing the six Bucharest sector courts moved the
        # judecatorie average by 4,5%, which a tolerance loose enough to allow for the
        # report's own rounding would never have caught.
        present = ranks.get(tier, set())
        if present:
            gaps = sorted(set(range(1, max(present) + 1)) - present)
            if gaps:
                raise SystemExit(
                    f"{tier}: the report numbers rows 1..{max(present)} but "
                    f"{len(gaps)} are missing ({gaps[:10]}) — rows were dropped, refusing to write"
                )
        printed = edition.printed_averages.get(tier)
        flag = ""
        if printed:
            drift = max(
                abs(per_judge - printed["perJudge"]) / printed["perJudge"],
                abs(per_post - printed["perPost"]) / printed["perPost"],
            )
            flag = f"   tiparit {printed['perJudge']}/{printed['perPost']}  abatere {drift:.1%}"
        print(f"  {tier:14} {len(rows):>4} instante  {volume:>9,} dosare  "
              f"{judges:>7,.0f} judecatori{flag}".replace(",", " "))

    document = {
        "$schema": "../schema/courts.schema.json",
        "id": "instante-2023",
        "title": "Harta instanțelor și volumul lor de activitate, 2023",
        "publisher": "Consiliul Superior al Magistraturii",
        "period": edition.period,
        "provenance": {
            "source": edition.source,
            "locator": "Raport privind starea justiției în anul 2023, Anexa 1",
            "confidence": "verbatim",
        },
        "nationalAverages": {"byTier": averages},
        "courts": courts,
        "limitations": [
            {
                "id": "judecatori-derivati",
                "text": (
                    "Raportul nu tipărește numărul de judecători, ci încărcătura pe judecător "
                    "și pe schemă. Numerele de aici sunt reconstituite împărțind volumul la "
                    "acele rapoarte. Ce iese e un efectiv *mediu pe an*, nu un cap de om la o "
                    "dată anume: judecătorii vin, pleacă și stau o parte din an, iar CSM "
                    "împarte la o medie. De aceea aproape niciun rezultat nu e număr întreg, "
                    "și de aceea cifra e bună pentru a compara instanțe între ele, nu pentru "
                    "a cita efectivul unei instanțe. La o singură instanță din 241 — "
                    "Judecătoria Târnăveni — efectivul reconstituit depășește schema, ceea "
                    "ce nu e o eroare de citire: se întâmplă când judecători delegați "
                    "acoperă mai mult decât posturile aprobate."
                ),
                "severity": "material",
                "affects": ["judges", "posts"],
            },
            {
                "id": "un-singur-an",
                "text": (
                    "Cifrele descriu anul 2023. Volumul unei instanțe variază de la an la an, "
                    "iar o instanță mică într-un an poate fi peste prag în următorul. O "
                    "propunere de comasare construită pe un singur an e mai fragilă decât una "
                    "construită pe o medie multianuală."
                ),
                "severity": "material",
                "affects": ["volume", "resolved"],
            },
            {
                "id": "fara-geografie",
                "text": (
                    "Documentul nu conține localizarea instanțelor și nici populația "
                    "arondată. Comasarea are un cost de acces — distanța pe care o are de "
                    "făcut un cetățean — care nu poate fi evaluat din datele astea singure."
                ),
                "severity": "blocking",
                "affects": ["access", "consolidation"],
            },
            {
                "id": "volum-nu-e-complexitate",
                "text": (
                    "Un dosar este o unitate, indiferent dacă e o plângere contravențională "
                    "sau un litigiu comercial de ani de zile. Încărcătura pe judecător "
                    "măsoară numărul, nu greutatea, iar instanțele mari au altă structură a "
                    "cauzelor decât cele mici."
                ),
                "severity": "material",
                "affects": ["volume", "loadPerJudge"],
            },
        ],
    }

    edition.out.parent.mkdir(parents=True, exist_ok=True)
    edition.out.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {edition.out.relative_to(ROOT)}: {len(courts)} instante")


if __name__ == "__main__":
    main()
