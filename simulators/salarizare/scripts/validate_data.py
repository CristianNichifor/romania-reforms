"""Validate every data document against its schema.

    uv run --with jsonschema python scripts/validate_data.py

Beyond JSON Schema, this asserts the cross-document invariants a schema cannot express:
coefficients inside their declared grade band, ladder and cap references resolving,
and — the one that matters most — no `assumed` provenance surviving into a published
regime. Exits non-zero on any error so CI blocks the merge.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent


def load(path: Path) -> dict:
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def resolve_series(series, when: str | None = None) -> float:
    """A ValueSeries is a number or a dated step function. Take the first step when
    no date is given; picking the last would quietly report a 2031 grid as today's."""
    if isinstance(series, (int, float)):
        return float(series)
    steps = sorted(series, key=lambda s: s["from"])
    if when is None:
        return float(steps[0]["value"])
    applicable = [s for s in steps if s["from"] <= when]
    return float((applicable or steps)[0]["value"])


def check_regime(doc: dict, path: Path, fiscal: dict[str, dict]) -> list[str]:
    errors: list[str] = []
    grades = {g["id"]: g for g in doc.get("grades", [])}
    ladders = doc.get("ladders", {})
    caps = {c["id"] for c in doc.get("caps", [])}

    for pos in doc.get("positions", []):
        where = f"{path.name}:{pos['code']}"

        ladder = pos.get("ladder")
        if ladder and ladder not in ladders:
            errors.append(f"{where}: unknown ladder {ladder!r}")
        for step in pos.get("ladderPath", []):
            if ladder and step not in {s["id"] for s in ladders[ladder]["steps"]}:
                errors.append(f"{where}: ladderPath references unknown step {step!r}")

        for variant in pos.get("variants", []):
            grade_id = variant.get("gradeId")
            if grade_id and grade_id not in grades:
                errors.append(f"{where}: unknown gradeId {grade_id!r}")
                continue
            if not grade_id or "value" not in variant:
                continue
            # The source assigns the grade; we check it rather than trust it.
            value = resolve_series(variant["value"])
            lo = resolve_series(grades[grade_id]["min"])
            hi = resolve_series(grades[grade_id]["max"])
            if not lo <= value <= hi:
                errors.append(
                    f"{where}: coefficient {value} outside declared grade {grade_id} [{lo}, {hi}]"
                )

        titles = pos.get("titles")
        assim = pos.get("assimilation")
        if titles and assim and assim.get("fanIn") not in (None, len(titles)):
            errors.append(f"{where}: fanIn {assim['fanIn']} but {len(titles)} titles listed")
        if titles and sum(1 for t in titles if t.get("canonical")) > 1:
            errors.append(f"{where}: more than one canonical title")

    for sup in doc.get("supplements", []):
        cap_id = sup.get("capId")
        if cap_id and cap_id not in caps:
            errors.append(f"{path.name}:{sup['id']}: unknown capId {cap_id!r}")
        if sup["countsToCap"] == "partial" and "capSplit" not in sup:
            errors.append(f"{path.name}:{sup['id']}: countsToCap 'partial' requires capSplit")
        for other in sup.get("excludes", []):
            if other not in {s["id"] for s in doc["supplements"]}:
                errors.append(f"{path.name}:{sup['id']}: excludes unknown supplement {other!r}")

    ref_cap = doc.get("reference", {}).get("growthCapId")
    if ref_cap and ref_cap not in caps:
        errors.append(f"{path.name}: reference.growthCapId {ref_cap!r} is not a declared cap")

    # A cap bound to an external statistic is only meaningful if the statistic is here.
    # Art. 9(4) and Art. 36(3) are rules the model would otherwise appear to enforce
    # while silently evaluating nothing.
    for cap in doc.get("caps", []):
        bound = cap.get("boundTo")
        if cap["kind"] in ("growth", "shareOfGdp") and not bound:
            errors.append(f"{path.name}:{cap['id']}: kind {cap['kind']!r} requires boundTo")
            continue
        if not bound:
            continue
        dataset = fiscal.get(bound["dataset"])
        if dataset is None:
            errors.append(f"{path.name}:{cap['id']}: unknown fiscal dataset {bound['dataset']!r}")
            continue
        series = {s["id"]: s for s in dataset["series"]}
        entry = series.get(bound["seriesId"])
        if entry is None:
            errors.append(
                f"{path.name}:{cap['id']}: series {bound['seriesId']!r} "
                f"not in fiscal dataset {bound['dataset']!r}"
            )
            continue
        periods = {o["period"] for o in entry["observations"]}
        baseline = bound.get("baselinePeriod")
        if baseline and baseline not in periods:
            errors.append(
                f"{path.name}:{cap['id']}: baselinePeriod {baseline!r} has no observation "
                f"in {bound['seriesId']!r}"
            )
        if cap["kind"] == "shareOfGdp" and entry["unit"] != "PC_GDP":
            errors.append(
                f"{path.name}:{cap['id']}: kind 'shareOfGdp' bound to a series in "
                f"{entry['unit']!r}, expected PC_GDP"
            )

    if doc.get("status") == "in-force":
        assumed = [
            p["locator"]
            for p in walk_provenance(doc)
            if p.get("confidence") == "assumed"
        ]
        if assumed:
            errors.append(
                f"{path.name}: status 'in-force' but {len(assumed)} assumed provenance entries "
                f"(first: {assumed[0]!r}). Resolve them or downgrade the status."
            )
    return errors


def walk_provenance(node) -> list[dict]:
    found = []
    if isinstance(node, dict):
        if {"source", "locator", "confidence"} <= node.keys():
            found.append(node)
        for value in node.values():
            found.extend(walk_provenance(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(walk_provenance(item))
    return found


def check_crosswalk(doc: dict, path: Path, regimes: dict[str, dict]) -> list[str]:
    errors: list[str] = []
    for side in ("from", "to"):
        if doc[side] not in regimes:
            # A crosswalk may legitimately point at a regime not yet imported.
            print(f"  note: {path.name} references regime {doc[side]!r}, not present yet")

    for i, link in enumerate(doc.get("links", [])):
        where = f"{path.name}:links[{i}]"
        if link["relation"] == "merge" and len(link["from"]) < 2:
            errors.append(f"{where}: relation 'merge' needs at least two 'from' endpoints")
        if link["relation"] == "split" and len(link["to"]) < 2:
            errors.append(f"{where}: relation 'split' needs at least two 'to' endpoints")
        if link["relation"] == "abolished" and link["to"]:
            errors.append(f"{where}: relation 'abolished' must have an empty 'to'")
        if link["relation"] == "new" and link["from"]:
            errors.append(f"{where}: relation 'new' must have an empty 'from'")

        for side in ("from", "to"):
            regime = regimes.get(doc[side])
            if not regime:
                continue
            codes = {p["code"] for p in regime["positions"]}
            for endpoint in link[side]:
                if endpoint["positionCode"] not in codes:
                    errors.append(
                        f"{where}: {side} position {endpoint['positionCode']!r} "
                        f"not in regime {doc[side]!r}"
                    )
    return errors


def main() -> int:
    regime_schema = Draft202012Validator(load(ROOT / "schema/regime.schema.json"))
    crosswalk_schema = Draft202012Validator(load(ROOT / "schema/crosswalk.schema.json"))
    fiscal_schema = Draft202012Validator(load(ROOT / "schema/fiscal.schema.json"))

    errors: list[str] = []
    regimes: dict[str, dict] = {}
    fiscal: dict[str, dict] = {}

    # Fiscal first: regimes reference it, so a broken series must surface as the
    # cause rather than as a dangling cap downstream.
    for path in sorted((ROOT / "data/fiscal").glob("*.json")):
        doc = load(path)
        doc.pop("$schema", None)
        schema_errors = sorted(fiscal_schema.iter_errors(doc), key=lambda e: list(e.path))
        for err in schema_errors:
            errors.append(f"{path.name}: {'/'.join(map(str, err.path))}: {err.message}")
        if not schema_errors:
            fiscal[doc["id"]] = doc
            print(f"  schema ok: {path.name} ({len(doc['series'])} series)")

    for path in sorted((ROOT / "data/regimes").glob("*.json")):
        doc = load(path)
        doc.pop("$schema", None)
        schema_errors = sorted(regime_schema.iter_errors(doc), key=lambda e: list(e.path))
        for err in schema_errors:
            errors.append(f"{path.name}: {'/'.join(map(str, err.path))}: {err.message}")
        if not schema_errors:
            regimes[doc["id"]] = doc
            print(f"  schema ok: {path.name} ({len(doc['positions'])} positions)")

    for doc in regimes.values():
        errors.extend(check_regime(doc, ROOT / "data/regimes" / f"{doc['id']}.json", fiscal))

    for path in sorted((ROOT / "data/crosswalks").glob("*.json")):
        doc = load(path)
        doc.pop("$schema", None)
        schema_errors = sorted(crosswalk_schema.iter_errors(doc), key=lambda e: list(e.path))
        for err in schema_errors:
            errors.append(f"{path.name}: {'/'.join(map(str, err.path))}: {err.message}")
        if not schema_errors:
            print(f"  schema ok: {path.name} ({len(doc['links'])} links)")
            errors.extend(check_crosswalk(doc, path, regimes))

    if errors:
        print(f"\n{len(errors)} error(s):", file=sys.stderr)
        for err in errors:
            print(f"  {err}", file=sys.stderr)
        return 1

    print("\nall data valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
