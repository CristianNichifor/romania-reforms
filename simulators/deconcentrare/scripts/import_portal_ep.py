"""Import the MFin portal list of public entities as a complement to the ANFP register.

The ANFP register counts institutions that manage public functions. The Ministry of Finance
portal publishes the fuller "Lista entităților publice" — every public entity with a CIF and
an ordonator principal de credite, dated snapshots. That row-level, attributable export is
exactly what `docs/coverage-gap.md` names as the condition for building the complement: it
carries the county-replicated services ANFP misses (OCPI, poliție, ambulanță, ISU, DGASPC,
inspectorate școlare, OSPA) while keeping its own limits (no headcounts; families like APM,
ANPC and GNM county offices remain absent).

Two modes:

    uv run python scripts/import_portal_ep.py               # default: read the committed csv.gz
    uv run --with xlrd python scripts/import_portal_ep.py --convert <xls> [--xls-sha256 <hex>]
                                                            # hand-run once per snapshot: convert
                                                            # the portal XLS into the committed gz

The committed artifact is `sources/lista-ep-portal-2026.csv.gz`: a lossless-for-consumer
conversion of the snapshot (the columns the simulator consumes; the address column is
dropped). The original XLS is not committed — 3.9 MB against 3.6 MB of tracked-tree
headroom — so its SHA-256 is recorded in the payload instead, and the conversion is pinned
by the gz's own checksum.
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import json
import sys
from pathlib import Path

from build_deconcentrare import fold, load_county_codes, strip_county

ROOT = Path(__file__).resolve().parents[1]
SOURCE_GZ = ROOT / "sources" / "lista-ep-portal-2026.csv.gz"
XLS_SHA = ROOT / "sources" / "lista-ep-portal-2026.xls.sha256"
OUT = ROOT / "data" / "portal-ep-2026.json"

COLUMNS = (
    "judet",
    "cif",
    "denumire",
    "uat",
    "cif_ordonator_1",
    "denumire_ordonator_1",
    "denumire_ordonator_2",
)

MUNICIPAL = ("MUNICIPAL", "MUNICIPIULUI", "SECTOR")

# code -> (name, tier, prefixes, contains, excludes). Prefixes match the folded,
# county-stripped name from the left; `contains`/`excludes` match anywhere. Codes of ANFP
# families are reused verbatim so the build can merge the two sources per family.
PORTAL_FAMILIES: list[tuple[str, str, str, list[str], list[str], list[str]]] = [
    (
        "politie-frontiera",
        "Poliția de Frontieră — inspectorate teritoriale",
        "regional-de-facto",
        ["INSPECTORATUL TERITORIAL AL POLITIEI"],
        [],
        [],
    ),
    (
        "politie",
        "Poliția județeană",
        "regional",
        [
            "INSPECTORATUL DE POLITIE",
            "INSPECTORATUL JUDETEAN DE POLITIE",
            "INSPECTORATUL JUD.POLITIE",
            "M.A.I. INSPECTORATUL DE POLITIE",
        ],
        [],
        [],
    ),
    (
        "jandarmerie",
        "Jandarmeria județeană",
        "regional",
        [],
        ["JANDARMI", "JUDETEAN"],
        [],
    ),
    (
        "prefectura",
        "Instituția prefectului",
        "special",
        ["INSTITUTIA PREFECTULUI"],
        [],
        [],
    ),
    (
        "ambulanta",
        "Serviciul de ambulanță județean",
        "regional",
        [],
        ["AMBULANTA"],
        [],
    ),
    (
        "isu",
        "Inspectoratul pentru Situații de Urgență",
        "regional",
        ["INSPECTORATUL PENTRU SITUATII DE URGENTA", "INSPECTORAUL PTR SITUATII"],
        [],
        [],
    ),
    (
        "scolar",
        "Inspectoratul școlar județean",
        "regional",
        ["INSPECTORATUL SCOLAR"],
        [],
        [],
    ),
    (
        "ocpi",
        "Oficiul de Cadastru și Publicitate Imobiliară",
        "regional",
        ["OFICIUL DE CADASTRU SI PUBLICITATE", "OFICUL DE CADASTRU SI PUBLICITATE"],
        [],
        [],
    ),
    (
        "dgaspc",
        "DGASPC — asistență socială și protecția copilului",
        "regional",
        [
            "DIRECTIA GENERALA DE ASISTENTA SOCIALA SI PROTECTIA COPILULUI",
            "DIRECTIA DE ASISTENTA SOCIALA SI PROTECTIA COPILULUI",
        ],
        [],
        ["SECTOR"],
    ),
    (
        "ospa",
        "Oficiul de Studii Pedologice și Agrochimice",
        "regional",
        ["OFICIUL DE STUDII PEDOLOGICE"],
        [],
        [],
    ),
    (
        "dsv",
        "Direcția Sanitar-Veterinară și pentru Siguranța Alimentelor",
        "regional",
        ["DIRECTIA SANITARA VETERINARA"],
        [],
        [],
    ),
    ("garda-forestiera", "Garda Forestieră", "regional-de-facto", ["GARDA FORESTIERA"], [], []),
    (
        "dgfp",
        "Direcția Generală Regională a Finanțelor Publice",
        "regional-de-facto",
        ["DIRECTIA GENERALA REGIONALA A FINANTELOR PUBLICE"],
        [],
        [],
    ),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def classify(folded: str) -> str | None:
    """Portal family code, the municipal sentinel, or None.

    Families match first: a county service whose name happens to carry „municipiu" (the
    Bucharest ambulance service, the city prefect) is still the deconcentrated service. A
    family's own `excludes` (the sector DGASPC) drops the row into the municipal bucket.
    """
    for code, _name, _tier, prefixes, contains, excludes in PORTAL_FAMILIES:
        if excludes and any(token in folded for token in excludes):
            continue
        if any(folded.startswith(prefix) for prefix in prefixes):
            return code
        if contains and all(token in folded for token in contains):
            return code
    if any(token in folded for token in MUNICIPAL):
        return "MUNICIPAL"
    return None


def read_rows() -> list[dict]:
    rows: list[dict] = []
    with gzip.open(SOURCE_GZ, "rt", encoding="utf-8") as handle:
        for record in csv.DictReader(handle):
            rows.append({key: (record.get(key) or "").strip() for key in COLUMNS})
    return rows


def convert(xls: Path, xls_sha256: str | None) -> None:
    """Hand-run once per snapshot: XLS -> the committed csv.gz. Requires xlrd."""
    import xlrd  # noqa: PLC0415

    workbook = xlrd.open_workbook(xls)
    sheet = workbook.sheet_by_name("Sheet1")
    header = tuple(str(sheet.cell_value(0, c)).strip() for c in range(sheet.ncols))
    wanted = (
        "Judet",
        "CIF Entitate Publica",
        "Denumire Entitate Publica",
        "Denumire UAT pe raza careia isi desfasoara activitatea",
        "CIF Ordonator  principal  de credite (1)",
        "Denumire ordonator  principal de credite (1)",
        "Denumire ordonator  principal de credite (2)",
    )
    if not all(name in header for name in wanted):
        raise SystemExit(f"missing expected columns; found: {header!r}")
    index = {name: header.index(name) for name in wanted}
    import io  # noqa: PLC0415

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(COLUMNS), lineterminator="\n")
    writer.writeheader()
    for r in range(1, sheet.nrows):
        writer.writerow(
            {
                "judet": str(sheet.cell_value(r, index["Judet"])).strip(),
                "cif": str(sheet.cell_value(r, index["CIF Entitate Publica"])).strip(),
                "denumire": str(sheet.cell_value(r, index["Denumire Entitate Publica"])).strip(),
                "uat": str(
                    sheet.cell_value(
                        r, index["Denumire UAT pe raza careia isi desfasoara activitatea"]
                    )
                ).strip(),
                "cif_ordonator_1": str(
                    sheet.cell_value(r, index["CIF Ordonator  principal  de credite (1)"])
                ).strip(),
                "denumire_ordonator_1": str(
                    sheet.cell_value(r, index["Denumire ordonator  principal de credite (1)"])
                ).strip(),
                "denumire_ordonator_2": str(
                    sheet.cell_value(r, index["Denumire ordonator  principal de credite (2)"])
                ).strip(),
            }
        )
    # mtime=0: the gz is a committed artifact and must be byte-reproducible.
    with gzip.GzipFile(filename=SOURCE_GZ, mode="wb", mtime=0) as handle:
        handle.write(buffer.getvalue().encode("utf-8"))
    print(
        f"{sheet.nrows - 1} rows -> {SOURCE_GZ} "
        f"({SOURCE_GZ.stat().st_size // 1024} KB)"
        + (f"; xls sha256 {xls_sha256}" if xls_sha256 else "")
    )
    if xls_sha256:
        XLS_SHA.write_text(xls_sha256 + "\n", encoding="utf-8")
        print(f"-> {XLS_SHA}")
    else:
        print("note: pass --xls-sha256 to record the original file's fingerprint")


def main() -> None:
    if "--convert" in sys.argv:
        args = sys.argv[sys.argv.index("--convert") + 1 :]
        if not args:
            raise SystemExit("usage: import_portal_ep.py --convert <xls> [--xls-sha256 <hex>]")
        xls = Path(args[0])
        xls_sha256 = None
        if "--xls-sha256" in args:
            xls_sha256 = args[args.index("--xls-sha256") + 1]
        if not xls.exists():
            raise SystemExit(f"missing source {xls}")
        convert(xls, xls_sha256)
        return

    if not SOURCE_GZ.exists():
        raise SystemExit(f"missing source {SOURCE_GZ}; run --convert on the portal XLS first")
    county_codes = load_county_codes()
    counties = sorted(county_codes, key=len, reverse=True)
    meta = {code: (name, tier) for code, name, tier, _p, _c, _e in PORTAL_FAMILIES}

    municipal: list[str] = []
    unmatched: list[str] = []
    offices: list[dict] = []
    for row in read_rows():
        name = row["denumire"]
        folded = fold(strip_county(name, counties))
        code = classify(folded)
        county = county_codes.get(fold(row["judet"]))
        if code == "MUNICIPAL":
            municipal.append(name)
            continue
        if code is None:
            unmatched.append(name)
            continue
        family_name, tier = meta[code]
        offices.append(
            {
                "cui": row["cif"],
                "name": name,
                "county": county,
                "locality": row["uat"],
                "ordonator": row["denumire_ordonator_1"] or row["denumire_ordonator_2"],
                "family": code,
                "familyName": family_name,
                "tier": tier,
            }
        )

    by_family: dict[str, int] = {}
    for office in offices:
        by_family[office["family"]] = by_family.get(office["family"], 0) + 1

    payload = {
        "$schema": "../schema/portal-ep.schema.json",
        "id": "portal-ep-2026",
        "title": "Entitățile publice din portalul MFin, snapshot 2026-07-01, pe familii",
        "publisher": "Cristian Nichifor",
        "period": "2026-07-01",
        "provenance": {
            "source": "mfin-portal-entitati-publice",
            "locator": "portal.mfinante.gov.ro, „Lista entităților publice”, export XLS "
            "01.07.2026; coloanele Judet / CIF Entitate Publica / Denumire Entitate Publica / "
            "UAT / ordonator principal de credite",
            "confidence": "derived",
            "note": "Rândurile sunt copiate din sursă; familia și nivelul sunt clasificate aici "
            "printr-un tabel explicit de prefixe, nu de sursă. Fișierul XLS original nu este "
            "reținut în repository (limita de dimensiune) — amprenta lui este mai jos, iar "
            "conversia commit-uită este sources/lista-ep-portal-2026.csv.gz.",
        },
        "sourceChecksum": {"sha256": sha256(SOURCE_GZ), "file": SOURCE_GZ.name},
        "originalXls": {
            "file": "lista_ep_portal_01072026.xls",
            "sha256": XLS_SHA.read_text(encoding="utf-8").strip() if XLS_SHA.exists() else None,
            "note": "Amprenta fișierului original de pe portal, păstrată în "
            "sources/lista-ep-portal-2026.xls.sha256; fișierul XLS în sine nu este reținut "
            "în repository (limita de dimensiune), dar amprenta îl face verificabil dacă "
            "snapshot-ul este re-obținut de pe portal.",
        },
        "summary": {
            "total": len(offices) + len(municipal) + len(unmatched),
            "matched": len(offices),
            "municipalExcluded": len(municipal),
            "unmatched": len(unmatched),
            "byFamily": by_family,
        },
        "municipalNames": sorted(municipal),
        "unmatchedNames": sorted(unmatched),
        "offices": offices,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(
        f"{len(offices)} matched of {payload['summary']['total']} rows -> {OUT} "
        f"({OUT.stat().st_size // 1024} KB)"
    )
    print(json.dumps(by_family, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
