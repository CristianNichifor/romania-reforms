"""Import what Romania actually paid, split into base salary and supplements.

    uv run python scripts/import_executie.py

Writes data/fiscal/executie-personal.json.

Every comparison of Romanian supplements against Danish ones has so far been a
comparison between a limit and a fact: the Danish side is what people were paid, the
Romanian side is what the draft law permits. That asymmetry was recorded as a blocking
limitation because the national split of base salary versus supplements looked
unpublished — the Ministry of Finance releases the consolidated execution as a PDF-style
workbook, not as a series, and its site is intermittently unreachable.

It is published. Every public entity files its budget execution against the economic
classification, and that classification goes to paragraph depth: 10.01.01 "Salarii de
baza" sits beside 10.01.05 "Sporuri pentru conditii de munca" and 10.01.06 "Alte
sporuri". transparenta.eu has loaded those filings into a queryable database and exposes
them over GraphQL. Summing the reports of every *ordonator principal de credite* gives
the national figure without counting a subordinate institution twice.

So the Romanian side becomes a fact too, and the comparison becomes fact against fact.

Two things this importer will not pretend:

  * The economic classification is an accounting vocabulary, not the law's. "Sporuri" in
    the budget line is not the same set as the supplements Art. 21 caps, and the
    execution reports what was paid under the *current* regime, not under the draft. The
    figure answers "how large is Romania's supplement layer today", which is the
    question worth asking before deciding whether a 20% ceiling binds.
  * Mapping Romanian paragraphs onto the Danish components is a judgement. It is written
    down as data in COMPONENTS below rather than buried in a chart, each mapping carries
    a reason, and the paragraphs are also emitted unmapped so a reader who disagrees can
    re-add them differently.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data/fiscal/executie-personal.json"

API = "https://api.transparenta.eu/graphql"
# The default urllib agent is refused with 403; identify the caller honestly instead.
UA = "public-pay-simulator/1.0 (+https://github.com/CristianNichifor/public-pay-simulator)"

YEARS = ["2021", "2022", "2023", "2024", "2025"]

# Title I is three different things and only the first is pay in the sense the Danish
# earnings tables mean: 10.01 is cash pay, 10.02 is payment in kind, 10.03 is the
# employer's social contributions. Danish "earnings per hour worked" excludes pension, so
# 10.03 must stay out or the Romanian bar would silently include a component Denmark's
# does not. 10.02 comes along because Denmark does count fringe benefits.
PREFIXES = ["10.01", "10.02", "10.03"]

# 10.03 is the employer's own social contributions. It is deliberately kept out of the
# composition — Danish earnings exclude pension, so counting it would compare pay against
# the cost of employment — but the envelope needs it, because Art. 36 alin. (3) sets its
# target against personnel expenditure as the budget defines it, contributions included.
# So it is imported and reported separately rather than folded into either.
CONTRIBUTIONS_PREFIX = "10.03"

QUERY = """
query Aggregated($filter: AnalyticsFilterInput!, $limit: Int, $offset: Int) {
  aggregatedLineItems(filter: $filter, limit: $limit, offset: $offset) {
    nodes { fn_c: functional_code ec_c: economic_code ec_n: economic_name amount }
    pageInfo { totalCount hasNextPage }
  }
}
"""

# The functional chapters worth breaking out: the two the whole comparison is about, plus
# the two uniformed families whose supplement layer is the reason the cap has exemptions.
SCOPES = {
    "national": (None, "Tot sectorul bugetar"),
    "invatamant": ("65", "Învățământ"),
    "sanatate": ("66", "Sănătate"),
    "aparare": ("60", "Apărare"),
    "ordine-publica": ("61", "Ordine publică și siguranță națională"),
    "administratie": ("51", "Autorități publice și acțiuni externe"),
    "asistenta-sociala": ("68", "Asigurări și asistență socială"),
}

# Romanian paragraphs mapped onto the vocabulary Danmarks Statistik uses in LONSOFF, so
# the two compositions can be drawn on the same axis. `reason` is the argument for each
# placement and is carried into the output; nothing here is a fact about the law.
COMPONENTS: dict[str, tuple[str, str]] = {
    "10.01.01": ("basic", "Salariul de bază — exact ce măsoară BASIS în statistica daneză."),
    "10.01.02": ("irregular", "Salariul de merit: performanță, plătită discreționar. Abrogat în 2010, apare doar în anii vechi."),
    "10.01.03": ("basic", "Indemnizația de conducere ține de post, nu de condiții. În Danemarca intră în salariul negociat, deci în bază."),
    "10.01.04": ("seniority", "Sporul de vechime. Danemarca nu îl separă — vechimea urcă treapta din salariul de bază — așa că nu are corespondent și stă singur."),
    "10.01.05": ("conditions", "Sporuri pentru condiții de muncă — echivalentul lui GENE, compensația daneză pentru condiții."),
    "10.01.06": ("conditions", "Alte sporuri: tot compensație pentru cum se prestează munca."),
    "10.01.07": ("overtime", "Ore suplimentare — OVERB."),
    "10.01.08": ("irregular", "Fondul de premii: plată neregulată, ca UREGEL."),
    "10.01.09": ("holiday", "Indemnizația de vacanță — FERIE."),
    "10.01.10": ("overtime", "Fond pentru posturi ocupate prin cumul: muncă peste normă, plătită ca atare."),
    "10.01.11": ("overtime", "Plata cu ora: muncă peste normă, dominantă în învățământ."),
    "10.01.12": ("other", "Indemnizații pentru persoane din afara unității — nu sunt salariați, deci nu au corespondent danez."),
    "10.01.13": ("other", "Drepturi de delegare: decontare de cheltuieli, nu remunerație."),
    "10.01.14": ("other", "Indemnizații de detașare: tot decontare."),
    "10.01.15": ("fringe", "Alocații pentru transport — beneficiu, ca GODE."),
    "10.01.16": ("fringe", "Alocații pentru locuință — beneficiu."),
    "10.01.17": ("fringe", "Indemnizația de hrană: sumă fixă lunară, independentă de muncă. Cel mai aproape de un beneficiu."),
    "10.01.29": ("irregular", "Stimulentul de risc: plată excepțională, pandemică."),
    "10.01.30": ("irregular", "Alte drepturi salariale în bani — reziduul, plăți neregulate."),
    "10.02.01": ("fringe", "Tichete de masă — beneficiu în natură."),
    "10.02.02": ("fringe", "Norme de hrană — beneficiu în natură, greu de comparat: în Danemarca hrana nu e o categorie de plată."),
    "10.02.03": ("fringe", "Uniforme și echipament obligatoriu — beneficiu în natură."),
    "10.02.04": ("fringe", "Locuință de serviciu — beneficiu în natură."),
    "10.02.05": ("fringe", "Transport la și de la locul de muncă — beneficiu în natură."),
    "10.02.06": ("fringe", "Vouchere de vacanță — beneficiu în natură."),
    "10.02.30": ("fringe", "Alte drepturi salariale în natură."),
}


def request(filter_: dict, limit: int, offset: int) -> dict:
    body = json.dumps({
        "query": QUERY,
        "variables": {"filter": filter_, "limit": limit, "offset": offset},
    }).encode()
    request_ = urllib.request.Request(
        API, data=body, headers={"Content-Type": "application/json", "User-Agent": UA}
    )
    with urllib.request.urlopen(request_, timeout=180) as response:  # noqa: S310
        document = json.loads(response.read().decode())
    if document.get("errors"):
        raise SystemExit(f"API refused the query: {json.dumps(document['errors'])[:500]}")
    return document["data"]["aggregatedLineItems"]


def fetch_year(year: str) -> list[dict]:
    """Every (functional, economic) pair for one year, paginated to exhaustion."""
    filter_ = {
        "account_category": "ch",
        # Summing the ordonatori principali is what makes this a national total rather
        # than a total plus its own subordinates counted again.
        "report_type": "PRINCIPAL_AGGREGATED",
        "economic_prefixes": PREFIXES,
        "report_period": {"type": "YEAR", "selection": {"interval": {"start": year, "end": year}}},
    }
    rows: list[dict] = []
    offset, page = 0, 500
    while True:
        chunk = request(filter_, page, offset)
        rows.extend(chunk["nodes"])
        if not chunk["pageInfo"]["hasNextPage"]:
            expected = chunk["pageInfo"]["totalCount"]
            if len(rows) != expected:
                raise SystemExit(f"{year}: read {len(rows)} rows, API counted {expected}")
            return rows
        offset += page


def chapter_of(functional_code: str | None) -> str:
    """'65.04.02' and '65' both belong to chapter 65."""
    return (functional_code or "").split(".")[0]


def main() -> None:
    print(f"reading budget execution from {API}\n")

    # scope -> economic code -> year -> amount
    totals: dict[str, dict[str, dict[str, float]]] = {}
    contributions: dict[str, dict[str, dict[str, float]]] = {}
    names: dict[str, str] = {}
    unmapped: set[str] = set()

    for year in YEARS:
        rows = fetch_year(year)
        for row in rows:
            code = row["ec_c"]
            names.setdefault(code, row["ec_n"])
            is_contribution = code.startswith(CONTRIBUTIONS_PREFIX)
            if not is_contribution and code not in COMPONENTS:
                unmapped.add(f"{code} {row['ec_n']}")
            chapter = chapter_of(row["fn_c"])
            target = contributions if is_contribution else totals
            for scope, (want, _) in SCOPES.items():
                if want is None or want == chapter:
                    target.setdefault(scope, {}).setdefault(code, {}).setdefault(year, 0.0)
                    target[scope][code][year] += row["amount"]
        paid = sum(v[year] for v in totals["national"].values() if year in v)
        owed = sum(v.get(year, 0.0) for v in contributions.get("national", {}).values())
        print(
            f"  {year}  {len(rows):5,} pairs   {paid / 1e9:7,.1f} mld plată"
            f"  + {owed / 1e9:5,.1f} mld contribuții  = {(paid + owed) / 1e9:7,.1f} mld titlul I"
        )

    if unmapped:
        # A new paragraph appearing in the classification must not be silently dropped
        # into a total whose components no longer add up.
        raise SystemExit("economic codes with no component mapping: " + ", ".join(sorted(unmapped)))

    series: list[dict] = []

    for scope, (_, scope_label) in SCOPES.items():
        by_code = totals.get(scope, {})
        if not by_code:
            print(f"  warning: no rows for scope {scope}")
            continue

        year_totals = {
            year: sum(v.get(year, 0.0) for v in by_code.values()) for year in YEARS
        }

        # Each paragraph, as a share of cash pay in that scope, and as an amount.
        for code, by_year in sorted(by_code.items()):
            component, reason = COMPONENTS[code]
            dims = {
                "kind": "paragraph",
                "scope": scope,
                "economicCode": code,
                "component": component,
                "mappingReason": reason,
            }
            shares = [
                {"period": year, "value": round(by_year[year] / year_totals[year], 5)}
                for year in YEARS
                if by_year.get(year) and year_totals[year]
            ]
            amounts = [
                {"period": year, "value": round(by_year[year], 2)}
                for year in YEARS
                if by_year.get(year)
            ]
            if not shares:
                continue
            provenance = {
                "source": "transparenta-eu-executie",
                "locator": (
                    f"Execuție bugetară, ordonatori principali, cheltuieli, "
                    f"clasificația economică {code} ({names[code]}), {scope_label}"
                ),
                "confidence": "derived",
            }
            series.append({
                "id": f"ro-exec-{scope}-{code}-share",
                "label": f"{names[code]} — {scope_label}, pondere",
                "geo": "RO", "unit": "PC_TOT", "dims": dims,
                "observations": shares, "provenance": provenance,
            })
            series.append({
                "id": f"ro-exec-{scope}-{code}-amount",
                "label": f"{names[code]} — {scope_label}, sumă",
                "geo": "RO", "unit": "CP_MNAC", "dims": dims,
                "observations": amounts, "provenance": provenance,
            })

        # The rollup that sits beside the Danish composition.
        rollup: dict[str, dict[str, float]] = {}
        for code, by_year in by_code.items():
            component = COMPONENTS[code][0]
            for year, amount in by_year.items():
                rollup.setdefault(component, {}).setdefault(year, 0.0)
                rollup[component][year] += amount

        for component, by_year in sorted(rollup.items()):
            members = sorted(c for c in by_code if COMPONENTS[c][0] == component)
            series.append({
                "id": f"ro-comp-{scope}-{component}",
                "label": f"{scope_label} — {component}",
                "geo": "RO", "unit": "PC_TOT",
                "dims": {"kind": "composition", "scope": scope, "component": component},
                "observations": [
                    {"period": year, "value": round(by_year[year] / year_totals[year], 5)}
                    for year in YEARS
                    if by_year.get(year) and year_totals[year]
                ],
                "provenance": {
                    "source": "transparenta-eu-executie",
                    "locator": (
                        f"Suma clasificațiilor {', '.join(members)} ÷ total cheltuieli "
                        f"salariale, {scope_label}"
                    ),
                    "confidence": "derived",
                },
            })

        # Employer contributions and the full Title I, for the envelope. Kept as their own
        # series kinds so nothing that reads the composition can pick them up by accident.
        contrib_by_year = {
            year: sum(v.get(year, 0.0) for v in contributions.get(scope, {}).values())
            for year in YEARS
        }
        for kind, id_suffix, label, by_year in (
            ("contributions", "contributii", "contribuțiile angajatorului", contrib_by_year),
            (
                "titleTotal", "titlul-i", "titlul I, cu tot cu contribuții",
                {year: year_totals[year] + contrib_by_year[year] for year in YEARS},
            ),
        ):
            observations = [
                {"period": year, "value": round(by_year[year], 2)}
                for year in YEARS
                if by_year.get(year)
            ]
            if not observations:
                continue
            series.append({
                "id": f"ro-exec-{scope}-{id_suffix}",
                "label": f"{scope_label} — {label}",
                "geo": "RO", "unit": "CP_MNAC",
                "dims": {"kind": kind, "scope": scope},
                "observations": observations,
                "provenance": {
                    "source": "transparenta-eu-executie",
                    "locator": (
                        f"Execuție bugetară, ordonatori principali, "
                        f"{'clasificația 10.03' if kind == 'contributions' else 'titlul 10 în întregime'}, "
                        f"{scope_label}"
                    ),
                    "confidence": "derived",
                },
            })

        last = YEARS[-1]
        share = lambda k: rollup.get(k, {}).get(last, 0.0) / year_totals[last] * 100  # noqa: E731
        print(
            f"\n  {scope_label[:34]:36} bază {share('basic'):5.1f}%  vechime {share('seniority'):4.1f}%"
            f"  condiții {share('conditions'):4.1f}%  ore {share('overtime'):4.1f}%"
            f"  neregulate {share('irregular'):4.1f}%  beneficii {share('fringe'):4.1f}%"
        )

    document = {
        "$schema": "../../schema/fiscal.schema.json",
        "id": "executie-personal",
        "title": "Cheltuielile salariale ale sectorului bugetar românesc, pe clasificație economică",
        "publisher": "Ministerul Finanțelor (execuții bugetare), agregat de transparenta.eu",
        "methodology": (
            "Rapoartele de execuție ale ordonatorilor principali de credite, însumate pe "
            "clasificația economică la nivel de paragraf. Titlul 10.01 (cheltuieli "
            "salariale în bani) și 10.02 (în natură); 10.03, contribuțiile angajatorului, "
            "este exclus fiindcă statistica daneză de câștiguri nu include pensia."
        ),
        "retrieved": YEARS[-1],
        "query": {
            "endpoint": API,
            "field": "aggregatedLineItems",
            "reportType": "PRINCIPAL_AGGREGATED",
            "accountCategory": "ch",
            "economicPrefixes": PREFIXES,
            "years": YEARS,
        },
        "provenance": {
            "source": "transparenta-eu-executie",
            "locator": "transparenta.eu GraphQL, aggregatedLineItems",
            "confidence": "derived",
        },
        "series": series,
        "limitations": [
            {
                "id": "contabilitate-nu-lege",
                "text": (
                    "Clasificația economică este un vocabular contabil, nu al legii. "
                    "Ce intră la 10.01.05 „Sporuri pentru condiții de muncă” nu e "
                    "exact mulțimea de sporuri pe care Art. 21 le plafonează, iar "
                    "execuția arată ce s-a plătit sub regimul actual, nu sub proiect. "
                    "Cifra răspunde la „cât de mare e stratul de sporuri azi”, nu la "
                    "„ce ar produce plafonul de 20%”."
                ),
                "affects": ["structure"],
                "severity": "material",
            },
            {
                "id": "corespondenta-cu-danemarca-e-judecata",
                "text": (
                    "Punerea paragrafelor românești în categoriile daneze (bază, "
                    "condiții, ore suplimentare, neregulate, beneficii) este o "
                    "judecată, nu un fapt. Fiecare încadrare își poartă motivul în "
                    "date, iar paragrafele sunt publicate și separat, ca cine nu e de "
                    "acord să poată reface gruparea. Sporul de vechime stă singur: "
                    "Danemarca nu îl separă, fiindcă vechimea urcă treapta din salariul "
                    "de bază în loc să adauge un procent peste el."
                ),
                "affects": ["structure"],
                "severity": "material",
            },
            {
                "id": "ordonatori-principali",
                "text": (
                    "Totalul însumează raportările ordonatorilor principali de credite, "
                    "ca instituțiile subordonate să nu fie numărate de două ori. "
                    "Acoperirea depinde de ce a încărcat fiecare ordonator; un an "
                    "recent poate fi incomplet."
                ),
                "affects": ["headcount", "gross"],
                "severity": "note",
            },
            {
                "id": "fara-contributii",
                "text": (
                    "10.03, contribuțiile plătite de angajator, nu intră în totalul de "
                    "aici. Este alegerea care face cifra comparabilă cu câștigul danez "
                    "pe oră lucrată, care exclude pensia — dar înseamnă că nu e costul "
                    "total al unui angajat pentru buget."
                ),
                "affects": ["gross"],
                "severity": "note",
            },
        ],
    }

    OUT.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT.relative_to(ROOT)}: {len(series)} series across {len(SCOPES)} scopes")


if __name__ == "__main__":
    main()
