from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMPORTER = ROOT / "packages" / "uat_registry" / "scripts" / "import_uat_registry.py"
REGISTRY_DATA = ROOT / "packages" / "uat_registry" / "data"

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

    registry, report, population_report = import_uat_registry.build_documents(
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
    assert population_report is None
    assert sorted(units) == ["10", "1017", "2309", "29", "9262"]
    assert units["10"]["cui"] == "333"
    assert units["10"]["crosswalkKey"] == "AB"
    assert units["1017"]["cui"] is None
    assert units["1017"]["population"] is None
    assert units["1017"]["populationSource"] is None
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


def test_population_enrichment_populates_counties_and_reports_gaps():
    siruta_rows = import_uat_registry.read_csv(
        b"""SIRUTA;DENLOC;CODP;JUD;SIRSUP;TIP;NIV;MED;REGIUNE;FSJ;NUTS;LAU
10;JUDE\xc5\xa2UL ALBA;0;1;1;40;1;0;7;1;RO121;
1017;MUNICIPIUL ALBA IULIA;0;1;10;1;2;1;7;1;RO121;RO_1017
2309;ALMA\xc5\x9eU MARE;0;1;10;3;2;2;7;1;RO121;RO_2309
29;JUDE\xc5\xa2UL ARAD;0;2;1;40;1;0;4;2;RO421;
9262;MUNICIPIUL ARAD;0;2;29;1;2;1;4;2;RO421;RO_9262
""",
        ";",
        import_uat_registry.SIRUTA_COLUMNS,
    )
    crosswalk_rows = import_uat_registry.read_csv(
        b"""cui,natcode
333,AB
111,1017
222,2309
666,9262
""",
        ",",
        import_uat_registry.CROSSWALK_COLUMNS,
    )
    population_documents = [
        (
            Path("populatie-ab-2024.json"),
            {
                "period": "2024",
                "counties": ["AB"],
                "provenance": {"source": "ins-tempo-pop107d"},
                "summary": {"people": 1000},
                "localities": [
                    {"siruta": "1017", "name": "Alba Iulia", "people": 700},
                    {"siruta": "2309", "name": "Almasu Mare", "people": 300},
                    {"siruta": "999999", "name": "Ghost", "people": 1},
                ],
            },
        )
    ]

    registry, _, population_report = import_uat_registry.build_documents(
        siruta_rows,
        crosswalk_rows,
        year=2026,
        retrieved_date="2026-09-08",
        siruta_locator="siruta-fixture.csv",
        crosswalk_locator="crosswalk-fixture.csv",
        siruta_sha256="a" * 64,
        crosswalk_sha256="b" * 64,
        require_complete_counties=False,
        population_documents=population_documents,
        population_year=2024,
        population_sha256="c" * 64,
    )

    assert population_report is not None
    units = {unit["siruta"]: unit for unit in registry["units"]}
    assert units["10"]["population"] == 1000
    assert units["10"]["populationSource"] == "ins-tempo-pop107d-county-sum"
    assert units["1017"]["population"] == 700
    assert units["1017"]["populationSource"] == "ins-tempo-pop107d-locality"
    assert units["29"]["population"] is None
    assert registry["populationPeriod"] == "2024"
    assert registry["summary"]["withPopulation"] == 3
    assert registry["summary"]["populationSourcePeople"] == 1000
    assert registry["summary"]["populationUnmatchedSourceRows"] == 1

    assert population_report["sourceRowsNotInRegistry"] == [
        {
            "siruta": "999999",
            "name": "Ghost",
            "county": "AB",
            "people": 1,
            "source": "populatie-ab-2024.json",
        }
    ]
    assert population_report["registryRowsWithoutPopulation"] == [
        {
            "siruta": "29",
            "name": "JUDEŢUL ARAD",
            "level": "county",
            "countyCode": "AR",
            "reason": "no-pop107d-locality-row",
        },
        {
            "siruta": "9262",
            "name": "MUNICIPIUL ARAD",
            "level": "municipality",
            "countyCode": "AR",
            "reason": "no-pop107d-locality-row",
        },
    ]


def test_committed_population_report_leaves_only_bucharest_sectors_unpopulated():
    registry = json.loads((REGISTRY_DATA / "uat-registry-2026.json").read_text(encoding="utf-8"))
    report = json.loads(
        (REGISTRY_DATA / "uat-registry-population-report-2024.json").read_text(encoding="utf-8")
    )

    assert registry["summary"]["withPopulation"] == 3223
    assert registry["summary"]["populationSourcePeople"] == 21849217
    assert report["summary"]["sourceRowsNotInRegistry"] == 0
    assert report["summary"]["duplicateSourceSiruta"] == 0
    assert [row["level"] for row in report["registryRowsWithoutPopulation"]] == ["sector"] * 6
