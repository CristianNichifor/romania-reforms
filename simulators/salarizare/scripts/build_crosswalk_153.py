"""Match the posts in the law in force onto the posts in the draft.

    uv run python scripts/build_crosswalk_153.py

Writes data/crosswalks/ro-153-2017--ro-draft-2026-07-16.json.

Art. 37 abrogates 153/2017 outright and Art. 32 requires everyone to be reassigned onto a
new post — but the draft publishes no mapping. Each *ordonator de credite* decides, so the
same former title can land differently in two institutions. This file is therefore a
reconstruction, never a statement of anyone's rights, and `authority` says so.

What makes it hard is that the two laws name jobs differently on purpose:

  * 153/2017 keeps every qualifier inside the title — "Profesor studii superioare de lungă
    durată grad didactic I" is one string. The draft moved qualifiers into dimensions, so
    the same job is "Profesor" carrying a `grad` of "gradul I". Matching the strings
    directly therefore fails on exactly the posts that did not change.
  * Both laws merge several former titles into one row with punctuation.

So matching runs twice, and refuses more than it accepts:

  1. **Exact.** Identical normalised title within the same occupational family. Strong
     enough to name a relation and a confidence of `derived`.
  2. **Stem.** The same title with its qualifiers stripped, for posts pass 1 missed —
     and only 1:1, only for stems long enough to be a job. Confidence `assumed`.

A third pass was tried and removed. Where a stem matched several posts on each side, the
study level looked like it should decide which is which — "Consilier" with an S row and an
M row on both sides is two unambiguous pairs rather than one ambiguous group. It resolved
**none** of the seven candidate groups: the levels do not line up one-to-one on the
remaining collisions. Coverage past this point needs reading duties rather than titles,
which is editorial judgement and not something a script should fake.

Everything else is left unmatched and counted. It is tempting to call an unmatched former
post `abolished`, and it would roughly double the apparent coverage, but the evidence does
not support it: a post with no same-named counterpart is usually one this script could not
resolve, not one the draft deleted. Guessing there would be worse than saying nothing,
which is the whole reason a crosswalk carries a confidence field.
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OLD = ROOT / "data/regimes/ro-153-2017.json"
NEW = ROOT / "data/regimes/ro-draft-2026-07-16.json"
OUT = ROOT / "data/crosswalks/ro-153-2017--ro-draft-2026-07-16.json"

# Qualifiers the draft moved out of the title and into a dimension. Stripping them is what
# lets "Profesor studii superioare de lungă durată grad didactic I" meet "Profesor".
QUALIFIER = re.compile(
    r"\b(studii superioare de (lunga|scurta) durata|studii superioare|studii medii"
    r"|cu studii[a-z ]*|grad(ul)? didactic [ivx]+|grad(ul)? didactic definitiv"
    r"|grad(ul)? [ivx]+|gradul profesional [a-z]+|treapta [ivx]+|clasa [a-z ]+"
    r"|nivel(ul)? [a-z ]+|debutant|definitiv|principal|asistent|superior|specialist"
    r"|stagiar|practicant)\b"
)

# A stem shorter than this, or one that is only digits, is not a job title. Without the
# guard a stem of "1" matched six former posts onto five new ones, and a fragment
# "penitenciare" matched twelve onto two — links that look like findings and are noise.
MIN_STEM = 6

# How many posts one link may join. An *exact* title match is allowed to be wide: both
# laws print the same title once per employer, so "Director" legitimately joins twelve
# former posts to eight new ones, and that spread is the finding rather than a failure.
# A *stem* match has weaker evidence and stays one-to-one. Capping both at four cost 34
# defensible links and a third of the coverage.
MAX_EXACT = 20
MAX_STEM = 1

# A coefficient move smaller than this is the same post at a slightly different number;
# larger, and the draft has regraded it.
REGRADE_THRESHOLD = 0.02


def base(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", text)).strip()


def stem(text: str) -> str:
    return re.sub(r"\s+", " ", QUALIFIER.sub(" ", base(text))).strip()


def titles_of(position: dict) -> list[str]:
    names = [t["name"] for t in (position.get("titles") or [])]
    return names or [position["name"]]


def variants(position: dict) -> list[str]:
    """Every name a position answers to, including the ones its row merged together."""
    out: list[str] = []
    for title in titles_of(position):
        parts = re.split(r"[;/]", title) if (";" in title or "/" in title) else [title]
        out.extend(p.strip() for p in parts if p.strip())
    return out


def entry_value(position: dict) -> float | None:
    values = [v["value"] for v in position["variants"] if isinstance(v.get("value"), (int, float))]
    return min(values) if values else None


def index(positions: list[dict], key) -> dict[tuple, list[dict]]:
    out: dict[tuple, list[dict]] = defaultdict(list)
    for position in positions:
        for name in {key(v) for v in variants(position)}:
            if name:
                out[(name, position.get("family"))].append(position)
    return out


def main() -> None:
    old = json.loads(OLD.read_text(encoding="utf-8"))
    new = json.loads(NEW.read_text(encoding="utf-8"))
    old_positions, new_positions = old["positions"], new["positions"]
    print(f"153/2017 {len(old_positions)} posts  ->  draft {len(new_positions)} posts\n")

    links: list[dict] = []
    used_old: set[str] = set()
    used_new: set[str] = set()
    stats = Counter()

    def emit(olds: list[dict], news: list[dict], confidence: str, evidence: list[str],
             limit: int) -> None:
        if any(p["code"] in used_old for p in olds) or any(p["code"] in used_new for p in news):
            stats["refused_already_linked"] += 1
            return
        if len(olds) > limit or len(news) > limit:
            stats["refused_too_many"] += 1
            return

        if len(olds) > 1 and len(news) > 1:
            # Many-to-many: describe what happened to the count rather than pick a label
            # at random. Twelve former posts under eight new ones is a consolidation.
            relation = "merge" if len(olds) >= len(news) else "split"
            stats["many_to_many"] += 1
        elif len(olds) > 1:
            relation = "merge"
        elif len(news) > 1:
            relation = "split"
        else:
            before, after = entry_value(olds[0]), entry_value(news[0])
            moved = (
                before is not None
                and after is not None
                and before > 0
                and abs(after - before) / before > REGRADE_THRESHOLD
            )
            if moved:
                relation = "regrade"
            elif base(olds[0]["name"]) == base(news[0]["name"]):
                relation = "identity"
            else:
                relation = "rename"

        note = None
        if len(olds) == 1 and len(news) == 1:
            before, after = entry_value(olds[0]), entry_value(news[0])
            if before and after:
                note = (
                    f"Coeficient {before:.2f} -> {after:.2f} "
                    f"({(after / before - 1) * 100:+.1f}%). Coeficientii nu sunt direct comparabili: "
                    f"referinta e 2500 lei in 153/2017 si 4100 lei in proiect."
                )

        links.append({
            "id": f"{olds[0]['code']}--{news[0]['code']}",
            "relation": relation,
            # Endpoints carry the title as well as the code, so a link stays readable
            # when the regime it points into is not loaded.
            "from": [{"positionCode": p["code"], "title": p["name"][:120]} for p in olds],
            "to": [{"positionCode": p["code"], "title": p["name"][:120]} for p in news],
            "confidence": confidence,
            "evidence": evidence,
            **({"note": note} if note else {}),
            "provenance": {
                "source": "reconstructie",
                "locator": "Comparatie de denumiri intre anexele celor doua legi",
                "confidence": confidence,
                "note": "Niciuna dintre legi nu publica asimilarea. Legatura e reconstruita.",
            },
        })
        used_old.update(p["code"] for p in olds)
        used_new.update(p["code"] for p in news)
        stats[relation] += 1
        stats[f"confidence:{confidence}"] += 1

    # Pass 1 - identical titles inside the same family.
    old_exact, new_exact = index(old_positions, base), index(new_positions, base)
    for key in sorted(set(old_exact) & set(new_exact)):
        if len(key[0]) < MIN_STEM or key[0].isdigit():
            stats["refused_weak_key"] += 1
            continue
        emit(old_exact[key], new_exact[key], "derived",
             ["denumire identica", "aceeasi familie ocupationala"], MAX_EXACT)

    # Pass 2 - the same job with its qualifiers stripped, one to one only.
    remaining_old = [p for p in old_positions if p["code"] not in used_old]
    remaining_new = [p for p in new_positions if p["code"] not in used_new]
    old_stem, new_stem = index(remaining_old, stem), index(remaining_new, stem)
    for key in sorted(set(old_stem) & set(new_stem)):
        if len(key[0]) < MIN_STEM or key[0].isdigit():
            stats["refused_weak_key"] += 1
            continue
        olds, news = old_stem[key], new_stem[key]
        if len(olds) != 1 or len(news) != 1:
            stats["refused_stem_ambiguous"] += 1
            continue
        emit(olds, news, "assumed",
             ["aceeasi denumire dupa eliminarea gradului si a nivelului de studii",
              "aceeasi familie ocupationala"], MAX_STEM)

    unmatched_old = [p for p in old_positions if p["code"] not in used_old]
    unmatched_new = [p for p in new_positions if p["code"] not in used_new]

    document = json.loads(OUT.read_text(encoding="utf-8"))
    document["links"] = links
    document.pop("needs", None)
    document["provenance"]["note"] = (
        document["provenance"]["note"]
        + f" Reconstructia acopera {len(used_old)} din {len(old_positions)} functii din legea "
          f"in vigoare si {len(used_new)} din {len(new_positions)} din proiect. Restul raman "
          "nelegate: o functie fara corespondent cu acelasi nume nu inseamna ca a fost "
          "desfiintata, ci ca scriptul nu a putut-o rezolva, iar 'abolished' ar fi o "
          "afirmatie mai tare decat dovezile."
    )
    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"  links {len(links)}")
    for key in ("identity", "rename", "regrade", "merge", "split"):
        if stats[key]:
            print(f"    {key:10} {stats[key]:5}")
    print(f"  confidence: derived {stats['confidence:derived']}, assumed {stats['confidence:assumed']}")
    print(f"  refused: weak key {stats['refused_weak_key']}, too many {stats['refused_too_many']}, "
          f"stem ambiguous {stats['refused_stem_ambiguous']}, "
          
          f"already linked {stats['refused_already_linked']}")
    print(f"\n  covered: {len(used_old)}/{len(old_positions)} old "
          f"({len(used_old) / len(old_positions) * 100:.0f}%), "
          f"{len(used_new)}/{len(new_positions)} new "
          f"({len(used_new) / len(new_positions) * 100:.0f}%)")
    print(f"  unmatched: {len(unmatched_old)} old, {len(unmatched_new)} new")

    moves = [
        (entry_value(next(p for p in old_positions
                          if p["code"] == link["from"][0]["positionCode"])),
         entry_value(next(p for p in new_positions
                          if p["code"] == link["to"][0]["positionCode"])))
        for link in links
        if link["relation"] in {"identity", "rename", "regrade"}
    ]
    ratios = [a / b for b, a in ((x, y) for x, y in moves if x and y and x > 0)]
    if ratios:
        ratios.sort()
        print(f"\n  coefficient ratio new/old across {len(ratios)} one-to-one links:")
        print(f"    median {ratios[len(ratios) // 2]:.3f}   "
              f"p10 {ratios[len(ratios) // 10]:.3f}   p90 {ratios[len(ratios) * 9 // 10]:.3f}")
    print(f"\nwrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
