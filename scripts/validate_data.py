"""Validate every simulator's data against its schema.

One gate for the whole repository. A simulator is free to define its own document types,
but they all resolve `provenance.schema.json` from packages/provenance, so the vocabulary
that makes these numbers arguable is defined once and cannot drift between simulators.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / "packages/provenance/schema"


def registry() -> Registry:
    """Make the shared vocabulary resolvable by its bare filename from any simulator."""
    resources = []
    for path in SHARED.glob("*.json"):
        contents = json.loads(path.read_text(encoding="utf-8"))
        resources.append((path.name, Resource.from_contents(contents)))
    return Registry().with_resources(resources)


def main() -> int:
    errors: list[str] = []
    checked = 0

    for data_file in sorted(ROOT.glob("simulators/*/data/*.json")):
        simulator = data_file.parents[1]
        document = json.loads(data_file.read_text(encoding="utf-8"))
        ref = document.get("$schema", "")
        schema_path = (data_file.parent / ref).resolve()
        # `is_file`, not `exists`: a document with no $schema resolves the empty reference to its
        # own data directory, which exists, and the gate then tried to read a directory and died
        # on the traceback instead of naming the file that was missing its schema.
        if not ref or not schema_path.is_file():
            errors.append(f"{data_file.name}: $schema points at {ref!r}, which is not a schema file")
            continue

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        validator = Draft202012Validator(schema, registry=registry())
        found = sorted(validator.iter_errors(document), key=lambda e: list(e.path))
        checked += 1
        if found:
            for error in found[:10]:
                errors.append(f"{data_file.name}: {'/'.join(map(str, error.path))}: {error.message}")
        else:
            count = len(document.get("courts") or document.get("series") or [])
            print(f"  schema ok: {simulator.name}/{data_file.name} ({count} records)")

        # Provenance is the point of the repository, so it is checked as a rule rather
        # than left to each schema to remember.
        for record in document.get("courts") or []:
            if record.get("provenance", {}).get("confidence") == "assumed":
                errors.append(f"{data_file.name}: {record.get('id')} carries assumed provenance")

    if errors:
        print(f"\n{len(errors)} error(s):")
        for error in errors:
            print(f"  {error}")
        return 1
    print(f"\nall data valid ({checked} documents)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
