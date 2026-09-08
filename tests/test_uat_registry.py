from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPORTER = ROOT / "packages" / "uat_registry" / "scripts" / "import_uat_registry.py"

spec = importlib.util.spec_from_file_location("import_uat_registry", IMPORTER)
assert spec and spec.loader
import_uat_registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(import_uat_registry)


def test_registry_filters_uat_rows_and_maps_county_code_crosswalk_rows():
    siruta_rows = import_uat_registry.read_csv(
        b"""SIRUTA;DENLOC;CODP;JUD;SIRSUP;TIP;NIV;MED;REGIUNE;FSJ;NUTS;LAU
10;JUDE\xc5\xa2UL ALBA;0;1;1;40;1;0;7;1;RO121;
1017;MUNICIPIUL ALBA IULIA;0;1;10;1;2;1;7;1;RO121;RO_1017
1026;ALBA IULIA;510005;1;1017;9;3;1;7;1;RO121;
2309;ALMA\xc5\x9eU MARE;0;1;10;3;2;2;7;1;RO121;RO_2309
29;JUDE\xc5\xa2UL ARAD;0;2;1;40;1;0;4;2;RO421;
9262;MUNICIPIUL ARAD;0;2;29;1;2;1;4;2;RO421;RO_9262
""",
        ";",
        import_uat_registry.SIRUTA_COLUMNS,
    )
    crosswalk_rows = import_uat_registry.read_csv(
        b"""cui,natcode
111,1017
222,1017
333,AB
444,1026
555,999999
666,9262
666,2309
""",
        ",",
        import_uat_registry.CROSSWALK_COLUMNS,
    )

    registry, report = import_uat_registry.build_documents(
        siruta_rows,
        crosswalk_rows,
        year=2026,
        retrieved_date="2026-09-08",
        siruta_locator="siruta-fixture.csv",
        crosswalk_locator="crosswalk-fixture.csv",
        siruta_sha256="a" * 64,
        crosswalk_sha256="b" * 64,
        require_complete_counties=False,
    )

    units = {unit["siruta"]: unit for unit in registry["units"]}
    assert sorted(units) == ["10", "1017", "2309", "29", "9262"]
    assert units["10"]["cui"] == "333"
    assert units["10"]["crosswalkKey"] == "AB"
    assert units["1017"]["cui"] is None
    assert units["1017"]["level"] == "municipality"
    assert units["1017"]["shortName"] == "ALBA IULIA"
    assert units["2309"]["cui"] is None
    assert registry["summary"]["crosswalkMatchedBy"] == {"siruta": 4, "countyCode": 1}

    assert report["matchedCountyCodeRows"] == [
        {"countyCode": "AB", "siruta": "10", "name": "JUDEŢUL ALBA", "cui": "333"}
    ]
    assert report["duplicateSiruta"] == [{"siruta": "1017", "cuis": ["111", "222"]}]
    assert report["duplicateCui"] == [{"cui": "666", "natcodes": ["2309", "9262"]}]
    assert report["nonUatSirutaRows"] == [
        {
            "cui": "444",
            "siruta": "1026",
            "name": "ALBA IULIA",
            "sirutaType": 9,
            "sirutaLevel": 3,
        }
    ]
    assert report["unmatchedCrosswalkRows"] == [
        {"cui": "555", "natcode": "999999", "reason": "siruta-not-found"}
    ]
