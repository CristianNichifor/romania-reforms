# Romania Reforms

Simulators for Romanian public-policy reforms. Each one takes a published proposal, models
what it actually says, and lets the reader argue with it — deterministic, explainable,
running entirely in the browser.

> **Instruments for public debate, not calculators of entitlement.**
> They compute what a document says, not what anyone receives. No figure here is a right
> and no scenario is a recommendation.

## The rule the whole repository runs on

Every number carries the document and the article, page or cell it came from. Where the
data does not reach, the page says so instead of filling the gap with a plausible guess.
That is the only thing all the simulators have in common, and it is the thing worth
sharing.

`packages/provenance` holds that vocabulary — `provenance` with a confidence of
`verbatim | derived | assumed`, and `limitation` with a severity and the outputs it
affects. One definition, resolved by every simulator's schema, so a caveat means the same
thing in all of them.

## What gets shared, and what does not

**Shared:** the vocabulary above, and the clients for sources more than one simulator
needs — budget execution, INS Tempo, Eurostat, Danmarks Statistik, the SIRUTA registry.
A second copy of an importer is a second thing to drift.

**Not shared:** the engines. A pay engine and a court-consolidation engine have nothing in
common but the ethos, and forcing them into one abstraction would cost more than it saves.

**Not merged:** the URLs. Each simulator stays independently deployable and linkable,
because what makes these useful is that a scenario is a link you can paste into an
argument. This repository is an index, not a monolith.

## Simulators

| | | |
| --- | --- | --- |
| **justitie** | The judicial reform | migrated to the 2025 report |
| **salarizare** | Public-sector pay | migrated |
| **administrativ** | Consolidation of the 3 186 UATs | migrated |
| **impozit-teren** | Taxing land on its value | 25 counties read, 17 estimated, nothing excluded; 17 readers |

Both live simulators now live here, with their history, on project paths under one Pages
site: `/romania-reforms/salarizare/` and `/romania-reforms/administrativ/`. Their old
repositories become one-page redirects that carry `location.hash` across, so a scenario
someone has already pasted into an argument still opens the scenario.

**The code moved; the abstraction has not.** They are three apps in one repository, not
three consumers of a shared UI package. `packages/provenance` is shared because a second
simulator genuinely needed the same vocabulary; there is no `packages/ui` because
`justitie` has no interface yet, and extracting one from a single real consumer is how
shared packages end up wrong. That extraction waits for `justitie` to need it.

### justitie

Models the reform paper's proposal to turn **176 judecătorii and 42 tribunale into 42
consolidated tribunale and 15 regional courts of appeal**, plus its chapters on judicial
pay, service pensions, and the comparison with Denmark.

The baseline is in. `simulators/justitie/scripts/import_instante.py` reads Annex 1 of the
CSM's *Raport privind starea justiției* — **241 courts**, with the cases each carried, the
cases it disposed of, and the caseload per post and per judge:

| | courts | cases | judges |
| --- | --- | --- | --- |
| Înalta Curte | 1 | 21 995 | 23 |
| Curți de apel | 15 | 205 720 | 314 |
| Tribunale | 50 | 678 688 | 728 |
| Judecătorii | 175 | 2 307 236 | 1 586 |

The report never prints judge counts, but it prints caseload *per judge* — so dividing
back recovers the divisor. That divisor is an average over the year rather than a headcount
on a date, which is why it is almost never a whole number, and why it is marked `derived`
and good for comparing courts rather than for citing one.

Reading tables out of a PDF is the least reliable thing this repository does, so the
importer checks itself against the report's own row numbering. That guard earned its place
immediately: a first version silently dropped eight courts, including all six **Bucharest
sector courts** — among the largest in the country, Sector 1 alone carrying more cases than
every tribunal but Bucharest. A court map arguing that small courts are the problem while
missing the biggest urban ones would have been worse than no map. The tolerance check on
averages had passed at 4,5%; the rank-continuity check caught it outright, and with the
rows restored the reconstructed average matches the printed one to 0,0%.

### impozit-teren

Romania taxes land on **surface area** times a coefficient from the Fiscal Code — rank of
locality, zone letter, and nothing about what the land is worth. This models the other
option: taxing land on its value, and what that would move.

The value exists and the state already leans on it. Each Chamber of Public Notaries publishes
an annual *studiu de piață* setting minimum orientative values, used as the floor for notary
fees and transfer tax. It is the only valuation of Romanian land that is official, national,
published, and granular below the commune — Bacău's study prices land **village by village**,
in EUR/m², split by use category, with towns priced by zone letter instead.

`scripts/import_ghid.py` reads it. Fourteen counties are in — and it takes **ten readers** to
do it, because the layout is not a chamber's property. CNP Alba Iulia alone needs three: Alba
prints merged cells and rotated captions, Sibiu prints its captions sideways, Hunedoara scatters
its land across twenty tables of different shapes. CNP Ploiești needs two. Constanța's tables
collapse into single cells, so it is read as text; Vrancea organises the county by *where in it
you are* — the ring around Focșani, the hills, the plain, the mountains — with a different
column layout per band.

| județ | an | reader | sate | comune | localități zonate | pagini | acoperire |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Alba | 2026 | `alba` | 622 | 67 | 10 | 107 | 98,7% |
| Bacău | 2026 | `bacau` | 528 | 85 | 9 | 129 | 100% |
| Buzău | 2025 | `matrice` | 78 | 77 | 5 | 179 | 94,2% |
| Constanța | 2026 | `constanta` | 87 | 58 | 10 | 524 | 91,4% |
| Dâmbovița | 2025 | `matrice` | 135 | 81 | 7 | 220 | 97,8% |
| Harghita | 2026 | `targumures` | 56 | 56 | 9 | 228 | 97,0% |
| Hunedoara | 2026 | `hunedoara` | 185 | 54 | 11 | 91 | 94,2% |
| Iași | 2026 | `iasi` | 391 | 89 | 4 | 207 | 94,9% |
| Mureș | 2026 | `targumures` | 92 | 92 | 10 | 318 | 100% |
| Neamț | 2026 | `bacau` | 664 | 80 | 5 | 108 | 100% |
| Prahova | 2025 | `ploiesti` | 83 | 83 | 13 | 392 | 92,3% |
| Sibiu | 2026 | `sibiu` | 153 | 52 | 11 | 70 | 96,9% |
| Tulcea | 2026 | `constanta` | 67 | 47 | 2 | 524 | 94,1% |
| Vrancea | 2025 | `vrancea` | 270 | 68 | 5 | 22 | 100% |

**Four counties are 2025 documents, and the year is not a preference.** Every study of both
editions was surveyed to see which one prices land locality by locality, and for twelve of the
fourteen the two years score identically — same publisher, same template, nothing gained by
reaching back. The exceptions run in both directions. Buzău exists **only** as 2025: the
Ploiești chamber published no 2026 land study, and without the older edition the county is not
available at all. Hunedoara is the reverse — its 2025 volume is two PDFs of 51 and 41 pages
containing zero extractable characters, a scan, so only 2026 can be read. Vrancea is both at
once: a readable 2025 study and a 2026 scan. That is why the year travels with the data instead
of being assumed in common.

**Coverage is reported with the gaps named, not as a pass mark.** A reader is refused below
90%, and refused outright if it invents or duplicates a locality — but a county that reaches
97% ships with the three communes it missed listed by name, because "97%" and "97%, and here
is which ones" are different claims. The reader is judged on its values as well: the dearest
price in the county and the ratio of town prices to commune prices. Satu Mare matched 93,8% of
the county's names and priced its county seat at 10 EUR/m², a twentieth of reality; coverage
was fine and the parse had locked onto the wrong table. It was rejected and is not here.

**The residual method these grids were expected to need turned out to be unnecessary.** The
first plan recovered land value from property prices minus depreciated building cost, on the
assumption that the studies carried a construction-cost table. They do not — "costuri de
construcție" appears in them only in prose. They print land outright, which is better, and
the check that found this cost an afternoon rather than a rewrite.

The parse is measured against the **INS land register**, not against another page of the same
document: every locality the register lists for the county must come out of the study's tables,
and every locality the tables yield must be one the register lists. The schema refuses to
validate a file where either direction fails. An earlier version checked against the study's
own organisation page, which exists in the two documents from CNP Bacău and in none of the
fifteen tried from four other chambers. That gate earned itself immediately and repeatedly — a number pattern treating a space as
a thousands separator read Bacău's `256 123 48 35` as one number and silently dropped the
**curți construcții** row of the county's largest city, which is the single row a land tax
mostly lands on. Row counts looked fine throughout.

Two things the documents do that no template survives: commune names wrap **mid-word** —
`CLEJ` / `A`, `ONCEST` / `I`, and Valea Seacă split four ways with its last letter sharing a
line with the first village — and the same study spells the same place two ways, printing
`GIRLENI` for Gârleni but `BARSANESTI` for Bârsănești. Names are therefore resolved against
the roster rather than parsed, and a fragment is only absorbed if absorbing it turns an
unrecognised name into a recognised one.

**The other half is how much land there is.** A price per square metre is not a tax base
without a count of them. INS matrix `AGR101B` has hectares per locality by the same cadastral
categories the notaries price; `import_fond_funciar.py` reads it and `build_valoare_teren.py`
multiplies the two together.

| județ | localități | suprafață | curți-construcții | valoarea terenului, low → high |
| --- | --- | --- | --- | --- |
| Alba | 77 | 620 957 ha | 12 633 ha (2,0%) | 3,0 → 4,9 mld EUR |
| Bacău | 93 | 662 052 ha | 21 719 ha (3,3%) | 2,8 → 9,7 mld EUR |
| Buzău | 82 | 575 781 ha | 15 523 ha (2,7%) | 2,9 → 7,1 mld EUR |
| Constanța | 67 | 690 489 ha | 29 521 ha (4,3%) | 6,3 → 17,8 mld EUR |
| Dâmbovița | 87 | 397 362 ha | 16 285 ha (4,1%) | 2,4 → 4,9 mld EUR |
| Harghita | 65 | 650 616 ha | 12 424 ha (1,9%) | 2,7 → 3,1 mld EUR |
| Hunedoara | 65 | 683 098 ha | 16 029 ha (2,3%) | 1,1 → 2,4 mld EUR |
| Iași | 93 | 520 550 ha | 18 481 ha (3,6%) | 12,0 → 29,3 mld EUR |
| Mureș | 102 | 671 388 ha | 19 921 ha (3,0%) | 4,4 → 7,4 mld EUR |
| Neamț | 83 | 589 614 ha | 15 224 ha (2,6%) | 3,5 → 9,4 mld EUR |
| Prahova | 96 | 434 314 ha | 20 248 ha (4,7%) | 5,1 → 6,3 mld EUR |
| Sibiu | 62 | 537 817 ha | 15 218 ha (2,8%) | 5,1 → 11,9 mld EUR |
| Tulcea | 48 | 828 146 ha | 10 179 ha (1,2%) | 2,5 → 3,5 mld EUR |
| Vrancea | 73 | 485 703 ha | 10 545 ha (2,2%) | 1,4 → 3,0 mld EUR |

**Matching a locality is not the same as pricing its land, and the datasets now say which.**
`pricedHa` counts the hectares that actually received a price; `priceableHa` is the matched
localities' surface less forest, which no county prices and which already carries its own
limitation. Where the first is under 90% of the second the file says so as a `material`
limitation, because unpriced hectares enter the total at zero — they understate the county's
land value and inflate every ratio computed against it. Hunedoara prices agricultural land for
its eleven circumscription seats and nobody else, so it reaches **19%**; Tulcea, most of whose
surface is delta, reaches **50%**. Both are facts about the documents, and without the field
both read as findings about the counties.

**The answer is a band, and the band is the finding.** The grid publishes one price per
village and one per town zone, and neither villages nor zones have published areas to weight
them by — so every commune is valued at its cheapest published price, its dearest, and the
unweighted mean, and all three travel together. A single confident number here would be a
fiction. Two assumptions carry the arithmetic and both are `blocking`: that curți-construcții
is the intravilan (the register does not record the split, and intravilan land is priced up to
250× higher), and the absent weighting above.

Two defects worth recording because neither threw and both validated. INS repeats a dimension
label only when it changes and writes `-` underneath, so read literally the table credited
every category of every commune to the one named on the first row — putting Bacău county at
**4 319 hectares instead of 662 052**. And matching commune names on one spelling of â lost 16
of 176 communes, each of which then had no land value rather than a visibly missing one. Both
are now tested against numbers from outside the pipeline: the counties' real surface areas.

**Both taxes, on the same hectares.** `import_cod_fiscal.py` reads article 465 of Legea
227/2015 — five tables — from the consolidated text on the legislative portal, and
`build_impozit.py` levies it on the same land the value was computed from. Statutory against
statutory: comparing a modelled tax with what councils actually collect would attribute
arrears, exemptions and collection rates to the change of rule.

**And then in the unit the argument is actually about.** A land value tax is a claim on what
land *earns*, not on what it is worth, so `build_renta.py` capitalises the stock into a flow
and restates both taxes against it. "0,33% of land value" is not a sentence anyone can weigh;
"takes 7% of what the land earns" is.

| județ | acoperire | evaluat | valoare | rentă | azi ia din rentă | cotă neutră |
| --- | --- | --- | --- | --- | --- | --- |
| Iași | 94,9% | 88% | 104,9 mld | 5,25 mld/an | **1,7%** | 0,085% |
| Constanța | 95,7% | 88% | 55,0 mld | 2,75 mld/an | **5,9%** | 0,296% |
| Sibiu | 96,9% | 94% | 43,7 mld | 2,18 mld/an | **3,8%** | 0,192% |
| Neamț | 100% | 100% | 30,7 mld | 1,53 mld/an | **4,1%** | 0,207% |
| Prahova | 92,3% | 91% | 29,8 mld | 1,49 mld/an | **4,3%** | 0,217% |
| Mureș | 100% | 93% | 29,5 mld | 1,47 mld/an | **6,2%** | 0,308% |
| Bacău | 100% | 100% | 28,2 mld | 1,41 mld/an | **6,7%** | 0,334% |
| Buzău | 94,2% | 85% | 25,5 mld | 1,27 mld/an | **6,1%** | 0,306% |
| Alba | 98,7% | 72% | 20,3 mld | 1,01 mld/an | **7,1%** | 0,355% |
| Dâmbovița | 97,8% | 84% | 18,1 mld | 0,90 mld/an | **6,8%** | 0,342% |
| Tulcea | 94,1% | 50% | 15,8 mld | 0,79 mld/an | **8,2%** | 0,409% |
| Harghita | 97,0% | 96% | 15,2 mld | 0,76 mld/an | **7,4%** | 0,369% |
| Vrancea | 100% | 85% | 10,9 mld | 0,54 mld/an | **9,4%** | 0,468% |
| Hunedoara | 94,2% | 19% | 9,2 mld | 0,46 mld/an | **18,0%** | 0,900% |

*acoperire* is the share of the county's localities that were priced at all; *evaluat* is the
share of their non-forest hectares that received a price. The second is why Hunedoara's 18%
is not a finding about Hunedoara.

Together: **437 mld lei of land, earning 21,8 mld a year, taxed at 1,12 mld — 5,1% of the
rent.** Thirty-five per cent of the country by area. The whole of today's land tax on these
fourteen counties is equivalent to a land value tax of **0,26%**. Restricted to the six
counties where over 90% of priceable hectares carry a price, the figure is the same 5,1%,
which is the reason for quoting it at all.

**The tax on area is regressive in land value, and fourteen counties make it hard to argue
with.** Rank them by what a hectare is worth and the burden falls as the price rises —
Spearman's rho between value per hectare and share of rent taken is **−0,95**. Iași's land
runs at 202 000 lei a hectare and pays **1,7%** of its rent; Tulcea's at 19 000 and pays
**8,2%**; Vrancea's at 22 000 and pays **9,4%**. A tax indexed on hectares and a coefficient
table cannot see that a hectare of Iași is worth ten of Tulcea, so the lighter burden falls on
the more valuable land. Nothing in article 465 intends this; it is what taxing area instead of
value does.

**And the floor turns out to be roughly the market — for farmland.** The standing objection to
all of this is that the notaries' grid is a minimum, not a price anyone paid. For one kind of
land there are now two market references against it, and both are official.

Legea 17/2014 gives pre-emption rights over extravilan agricultural land and requires the
seller's offer — plot, area, price — to be published on the ministry's portal, which makes a
national per-commune register of what farmland is *asked* for. Verifi aggregates it under
CC BY 4.0, keyed by SIRUTA. Separately, INS runs an annual survey of what farmland actually
*sold* for and reports it to Eurostat as `apri_lprc`, by NUTS2 region, back to 2011.
`import_pret_cerut.py` and `import_teren_agricol_ins.py` read the two;
`build_multiplu_piata.py` divides both by the grid.

| | grilă RON/ha | preț cerut | preț plătit | → cerut | → plătit |
| --- | --- | --- | --- | --- | --- |
| Prahova | 12 094 | 30 350 | 40 937 | 2,51× | 3,38× |
| Bacău | 14 198 | 30 233 | 37 693 | 2,13× | 2,65× |
| Vrancea | 17 879 | 30 447 | 45 446 | 1,70× | 2,54× |
| Tulcea | 23 663 | 30 003 | 45 446 | 1,27× | 1,92× |
| Alba | 33 000 | 40 788 | 40 992 | 1,24× | 1,24× |
| Neamț | 32 602 | 35 714 | 37 693 | 1,09× | 1,16× |
| Harghita | 23 000 | 20 206 | 40 992 | 0,88× | 1,78× |
| Iași | 39 438 | 28 840 | 37 693 | **0,73×** | **0,96×** |
| Sibiu | 31 500 | 23 000 | 40 992 | **0,73×** | 1,30× |

Median **1,24×** against asking prices — **1,06×** on the 73 communes where both sources price
the same SIRUTA, which is the like-for-like number — and **1,71×** against INS transactions. So
the notaries' floor for farmland sits at roughly 60–80% of the market, not a fraction of it.

**The two references disagree, and in the awkward direction.** Transactions come out *above*
asking prices, which is backwards. Most of that is what each number is: INS reports a mean over
a right-skewed distribution where the barometer reports a median, INS is regional where the
barometer is per county, and the survey year is 2024 against offers collected in 2026. It also
weakens the "grid above market" reading — against asking prices three counties are below parity,
against transactions only Iași, and only just. The two multiples are published separately and
the file says not to average them.

**The bigger find was on the other side of the survey.** INS publishes farmland *rents* in the
same exercise (`apri_lrnt`), so rent ÷ price is a **measured land yield** — the parameter that
turns a stock of land value into a flow of land rent, and therefore sets what share of the rent
any tax is said to take. Arable land in Romania measures **1,4–1,6%** across eight regions and
six years; nationally in 2024, 706 lei of rent on 43 280 lei of price, **1,63%**. The simulator
had been assuming 3–7%.

**So the yield is now two yields, because the land is two assets.** Farmland takes the measured
band of its own NUTS2 region, drawn from that region's year-to-year movement since 2019. The
land under buildings keeps the assumed 3–7%, anchored on the observed gross residential yield
and set below it because a building depreciates out of its own rent and land does not. Nobody
publishes a yield for building land anywhere in Romania, and applying the farmland figure to it
would have been the easy mistake — three times lower, and a measurement of a different asset.

The rate that takes the whole rent is therefore no longer the parameter read back at you. It is
the blend of the two, weighted by how much of each county is farmland, and it differs between
counties as it should — 2,8% in Harghita, 4,3% in Hunedoara and Iași. Splitting the yield
raised what today's tax is shown to take, because the denominator shrank:

| județ | randament agricol măsurat | cotă care ia toată renta | azi ia din rentă |
| --- | --- | --- | --- |
| Iași | 1,82% | 4,24% | 2,0% |
| Sibiu | 1,47% | 3,85% | 5,0% |
| Bacău | 1,82% | 4,23% | 7,9% |
| Alba | 1,47% | 3,33% | 10,7% |
| Tulcea | 1,71% | 3,13% | 13,1% |
| Hunedoara | 1,41% | 4,28% | 21,0% |

The browser does the same arithmetic on the same split, and the parity test now checks the rent
county by county against the file Python wrote — which it could not meaningfully do before,
when both sides multiplied one total by one number.

**The other half of the yield is now bounded too, and it is not measurable.** Farmland's return
is surveyed; the land under houses has no published rent anywhere in Romania. All 115 notary
volumes were searched — the studies price land and never rent it, and every match is prose.
Municipal concession fees would be a genuine land rent, but they are negotiated contract by
contract and the decisions leave the figure blank. So `build_randament_construit.py` solves for
it instead, from an identity whose other terms are observable:

    a property earns   y_net = r + δ·(1 − λ)      →      r = y_net − δ·(1 − λ)

`y_net` from the observed gross residential yield (Global Property Guide, **5,87%** Q3 2026)
less operating costs. `δ` from **HG nr. 2139/2004**, the fixed-asset catalogue, class 1.6.1 —
residential buildings, 40 to 60 years. And `λ`, the land share of property value, computed from
the notaries' own grids: Hunedoara, Mureș and Harghita price the land and the building
separately for the same locality, and say so — Mureș prints *"Valoarea caselor de locuit
individuale nu includ terenul aferent"*. Without that sentence the calculation would be
circular, so it is quoted rather than assumed.

**The land share is the surprise: about 6%** of property value at a plot four times the floor
area, across 332 locality pairs — an order of magnitude below the 20–50% usual in western
European cities, and matching ANEVAR's own finding that land is 7,6% of the portfolios its
members value. Romanian construction costs what construction costs; Romanian land, outside the
cities that have no grid, does not.

| | low | central | high |
| --- | --- | --- | --- |
| randament net proprietate | 4,11% | 4,40% | 4,70% |
| amortizare clădire (HG 2139/2004) | 1,67% | 2,00% | 2,50% |
| pondere teren | 4,7% | 6,2% | 9,0% |
| **⇒ randament teren construit** | **1,73%** | **2,53%** | **3,18%** |
| presupus azi | 3,00% | 5,00% | 7,00% |

The derived ceiling is about the assumed floor. Put beside the measured farmland yield of
1,4–1,6%, both halves of Romanian land now point at **1,5–3%** where the simulator assumes
3–7% — which would roughly double every "takes X% of the rent" figure it reports.

**The low-bias worry was real, and it does not change the answer.** The land share was first
measured on three poor counties — Hunedoara, Mureș, Harghita — because they were the only ones
pricing land and buildings on the same page. Iași does too, in a separate annex headed by town
and zone, and Iași has the most valuable land of the fourteen: **600 euro a square metre** in
zone A against 1 800 for the house standing on it.

Adding it splits the sample in a way that pooling had hidden:

| | pondere teren | ⇒ randament teren |
| --- | --- | --- |
| urban | 16,6% | **2,73%** |
| rural | 5,7% | **2,52%** |
| presupus azi | | 3,00–7,00% |

Urban land really is worth several times more of its property than rural land is, and 97% of
the sampled rows are villages — so a single median over rows was answering a question nobody
asked. But the correction is 2,53% → 2,73%, and the assumed band still starts at 3%. The bias
was worth measuring and it does not rescue the assumption.

**It is a bound, not a measurement, and the band is still not changed on it.**
**Forest now earns its own yield instead of borrowing farmland's.** It was the last big
category resting on a placeholder — 11% of the land value, credited with whatever arable
earned, because nobody leases woodland by the year and there is no rent to survey. There is
still no rent, but there is timber, and both halves of it are published:

    rentă/ha = recolta anuală pe hectar × prețul masei lemnoase pe picior × (1 − costuri)

The harvest comes from **INS matrix AGR306A** per county — 19,41 million m³ in 2025, matching
the figure INS announced, at 2,88 m³ per hectare nationally. The price comes from **Romsilva's
auctions**: 230,40 lei/m³ achieved for standing timber in the first nine months of 2025, against
187,89 lei/m³ at opening. Standing timber is the right price because it is what accrues to the
owner of the land rather than to whoever fells it, and because the harvest series is gross
volume, which is what standing timber is measured in.

| județ | m³/ha/an | valoare lei/ha | rentă lei/ha/an | randament |
| --- | --- | --- | --- | --- |
| Harghita | 6,21 | 32 149 | 1 073 | 3,34% |
| Neamț | 5,89 | 28 921 | 1 018 | 3,52% |
| Bacău | 3,74 | 28 921 | 646 | 2,23% |
| Sibiu | 2,46 | 44 921 | 425 | 0,95% |
| Iași | 3,10 | 63 736 | 535 | 0,84% |

Median **2,27%**, band 1,60–2,57% — against **1,43%** measured for arable. Forest earning more
than farmland is plausible for an illiquid asset with lumpy income and a rotation measured in
decades, and it is now a result rather than an assumption on both sides.

**The denominator had to be the priced hectares, not all of them.** Dividing a county's forest
value by every forest hectare it owns mixes priced land with unpriced: Hunedoara prices forest
for eleven town seats and nobody else, so its forest looked like land worth 2 434 lei a hectare
yielding **15,6%**. Every row now carries what share of its county's forest actually got a
price, and a test refuses a value per hectare outside a plausible range.

What is still a parameter is the owner's cost share — guarding, administration, regeneration,
forest roads — at 15–35%, which is where most of the band's width comes from, and the stumpage
price is a national average applied to every county.

**The two counties rejected on values are in, and both were one bug each.**

*Satu Mare* was refused at 93,8% coverage with its county seat at 55 lei/m², below several of
its own communes. The cause was a row that is not what it looks like: the rural table lists
`SATU MARE · SĂTMAREL · 55`, and the 55 is **Sătmarel's** price — a village on the edge of the
city, priced as the municipality's because the municipality owns it. The city's own grid sits
forty pages earlier under a heading on the *previous* page, and reads 500/380/290/150/80 by
zone. All six towns now come out in the right order and the town-to-commune ratio is 3,4.

*Bihor* was refused because Oradea "moved 1200 → 228 → 42 across fixes" and looked like noise.
It was none of those readings — it was a **dictionary keyed on the village name**. Six zone rows
in Bihor all carry the label ORADEA, and `intravilan_prices` collapsed them to the last one, so
the county's largest city was valued at its cheapest zone. Keying the parts by position instead
gives Oradea a band of 42 → 130 → 228 EUR/m² and takes the county from 7,5 to **12,2 mld EUR**.
That bug was in the shared value builder, not in either reader, and it had been quietly
shaving Bacău and Neamț by about 1% as well.

Sixteen counties now: **1 248 localities, 9,47 M ha, 39,7% of Romania, 110 mld EUR.**

**Călărași recombines two readers already written, and the join is finer than either.** Rural
land is priced by **category**, as in Vaslui, with the assignment in numbered prose. The
extravilan grid is **one arable column and the chamber's coefficients**, as in Ilfov — same
seven multipliers, same chamber. What is new is that the prose works at *village* level and
names each village's parent commune:

    CATEGORIA I
    Sate
    1.Borcea
    2.Bogata-com.Gradistea
    9.Rasa-com.Gradistea 10.Roseti

Borcea is a commune seat; Bogata and Rasa are villages of Grădiștea; two entries share the last
line, which is why this splits on the numbering and not on line breaks. **96,4%** — 5 towns, 50
communes, 151 villages, every commune with an extravilan price.

Three things had to be got right, and each was wrong first:

- **The table of contents repeats every heading verbatim.** A scan keeping the first match of
  each found the index rather than the sections, pointed all three circumscriptions at page 7,
  and priced **nothing** — 0,0%. Contents lines are excluded by their dot leaders.
- **The urban and rural tables share a page and both have a `Valoare minima` row.** Taking the
  first read Călărași's three urban zones as though they were rural categories, so no village
  matched a category at all.
- **Romanian writes the ordinal two ways in the same table** — `Categoria I-a` beside
  `Categoria a II-a`. A pattern without the optional *a* matched the first and not the second,
  pricing every village of the second category at nothing.

The section numbers do not line up either: Călărași uses 3.2.2 for the rural zoning, Oltenița
4.2.2 and Lehliu Gară **5.2.4**, so blocks are grouped by the leading integer of whatever
heading is found. And two agricultural tables sit on the same page — `x.5.2` prices roadside
land at 31 400 EUR/ha and `x.5.3` exclusively-agricultural land at 7 500 — told apart by the
roadside table's `Calea rutiera` column rather than by which is larger.

**The model predicted Călărași at 4,64 mld EUR before it was read. The grid says 4,68 — a ratio
of 1,01.** Three out-of-sample checks now exist and the model has passed all three: Vaslui
1,32×, București understated by 1,35×, Călărași 1,01×, against a stated error of 1,61×.

**Ilfov closes the last hole: nothing is excluded from the national estimate any more.** Its
annexes cover all 40 UATs and the parse reaches **100%** — the second county in the set to do
so with no named gap at all.

Its extravilan grid is **one column and seven published coefficients**. The study prices arable
land per locality and then states outright what everything else is worth: curți-construcții
1,5× arable, vii și livezi 1,1×, pășuni și fânețe 0,8×, amenajări piscicole 1,4×, drumuri
tehnologice 0,7×, neproductiv 0,5×. One number per locality yields the whole grid, and the
ratios are the chamber's, not this repository's. Forest has a table of its own, by species.

**The towns hide their zones across pages.** A commune is four rows on one page, each labelled.
A town is four *pages* — `ANEXA 8.1` to `8.4` for Voluntari — with the zone named once in the
middle and the rows underneath split by landmark instead:

    ZONA CENTRALA   la Est de Autostrada A3 …    167,9   117,5
                    la Vest de Autostrada A3 …   308,2   215,8

So Voluntari has **six** prices across four pages, not four across one, and the dearest is
nearly twice the next. A reader keyed on the row label finds nothing there; one that stops at
the first page of a locality keeps a sixth of the town. The pair is not even on one baseline —
`167,9` and `117,5` are three points apart — so the columns come from the header instead.

**Ilfov is measured, counted, and kept out of the regression.** Its building land is **286 177
EUR/ha**; the model, fitted without it, says **68 872** — a factor of **4,2** against an
out-of-sample error of 1,61. It is not a county the size of its own largest town can explain,
because its market is set by a city that is not in it, which is exactly why it was excluded
from the estimate before its study was found. Leaving it in the fit costs all eighteen
predicted counties: leave-one-out **1,61× → 1,77×**, R² **0,75 → 0,66**.

That criterion is stated in the mechanism rather than chosen from the result, and it was
applied to București too — where it said *keep*, because including the capital improved the fit
instead of degrading it. Same test, opposite answers, and both are in the output file.

**Romania, all 42 counties: 349 mld EUR (192–687), 66% of it read rather than modelled.**

And the extravilan unit trap caught me a second time, in the other direction. Vaslui's annex
prints lei per square metre and needed no conversion; Ilfov's prints EUR per hectare and needed
dividing by ten thousand. The first run valued Ilfov at **20 727 mld EUR** — with 100%
coverage, every name matched, and no warning anywhere. The comment I had written on the Vaslui
fix was three files away.

**The București chamber does publish, and this repository said it did not.** That was a
statement about unnpr.ro's index, not about the chamber. `srv.cnpb.ro` — the chamber's own file
server, with an open directory listing — carries 2026 studies for **all six** of its counties:
București, Ilfov, and one volume for Călărași, Giurgiu, Ialomița and Teleorman. The index has
thirteen chambers because the fourteenth is not in it.

**Getting it needed the certificate fixed, not skipped.** That server sends a valid certificate
— `O=CAMERA NOTARILOR PUBLICI BUCUREȘTI`, issued by DigiCert — and omits the intermediate that
signs it, so no client can build a path. The tempting answer is to turn verification off, and
it is the wrong one: these documents become published numbers, and an unauthenticated fetch
means a proxy could rewrite the price of every square metre in Bucharest with nothing to notice
it. `tls_chain.py` does what a browser does instead — reads the certificate's own **Authority
Information Access** pointer, fetches the intermediate it names, and reconnects **with
verification on**. It hardcodes no CA, so it keeps working when DigiCert rotates that
intermediate, and it does nothing at all for the thirteen chambers whose servers are configured
properly.

**The capital is one locality with 277 subzones**, not a county with 277 localities: SIRUTA
179132, 23 787 hectares, a single row in the land register, priced across 59 cadastral zones
from **34 EUR/m² to 1 320**. There are no ruling lines, so the reader works from word
coordinates — the second one here to do so after Timiș.

Three things in that document are worth knowing:

- **A price row binds to its nearest label, not the one on its own line.** Digits and letters
  sit on different baselines, so `ZONA 25-A2`'s prices print *above* it, while two labels wrap
  onto a second line and push their prices *below*. Both directions, in the same table.
- **Two zones are cut by the Băneasa railway and priced twice** — `ZONA 25-A3 la NORD de` at
  454 EUR/m² and `la SUD de` at **945**. Assume one row per label and half of two zones is
  priced at the other half's figure, with nothing to show for it.
- **The grid is one number and four coefficients.** Every row satisfies `ocupat = 0,70 × liber`,
  `alei = 0,49`, `comercial = 1,10`, `industrial = 0,90`, on all 277. So the chamber does not
  price commercial land by observing commercial land — worth knowing before reading that column
  as a market signal, and useful here because it makes every row self-checking. The reader
  drops any row that fails it; none did.

The column taken is **TEREN OCUPAT DE CONSTRUCTII**, because the hectares being priced are the
register's *Ocupată cu construcții*. TEREN LIBER is 1/0,70 higher and is the right column for a
redevelopment reading.

**București is 50,3 mld EUR — the most valuable county in the set, twice Timiș.** And its band
is 39×, by far the widest here, because 277 subzones span 34 to 1 320 EUR/m² and nothing
publishes the hectares in each. The central figure is the estimate; the ends are bounds, not a
confidence interval. The study carries a street index — ninety pages mapping every street in
the city to its subzone — which is the route to narrowing it, and is not used yet.

**Excluding the capital from the national estimate was right, and now it is checked rather than
argued.** The model, extrapolated to 2,14 M people, says **37,4 mld**; the grid says **50,3**.
It would have understated Romania's most valuable county by a third, outside its own 1,65×
error. Reading it also *improved* the model — leave-one-out from 1,65× to 1,61× and R² from
0,58 to 0,75 — so București now earns a place in the fit it was previously kept out of, and
Ilfov is the only county still excluded.

**Romania without Ilfov: 339 mld EUR, 65% of it read rather than modelled.**

Three assumptions broke on a county with one letter and no villages, all silent, all found by
gates rather than by errors: schema minimums that required every county to have communes and
villages, id patterns of `[a-z]{2}` that rejected `impozit-b-2026`, and — after every upstream
gate had passed — a regex in the app's copy step that matched two-letter county codes and
quietly left the country's most valuable county out of the page.

**The yield was wrong, and this repository already knew.** Land rent is value times yield, so
the yield is the denominator under every capture figure here. Building land — 64% of the value
— was capitalised at an assumed **3–7%**, anchored on the observed residential yield. But
`randament-teren-construit-2026.json` derives the same quantity from an identity whose other
terms are all published, `r = y_net − δ·(1 − λ)`, and gets **1,7–3,2%**. The rent builder even
carried a limitation saying so: *"plafonul deducerii este aproximativ podeaua benzii folosite
aici, deci renta terenului construit este probabil supraestimată"*. Publishing both was the
inconsistency, and it had stood for months.

Four independent routes now put land yields in one place, and none is near 5%:

| | | |
|---|---|---|
| arable | **1,43%** | measured — rent ÷ price, INS via Eurostat |
| pasture, hayfield | **1,61%** | measured — the same survey |
| forest | **2,27%** | derived — harvest × standing price − owner's costs |
| building land | **2,53%** | derived — property yield − depreciation × building share |

The constant is gone. `build_renta.py` now reads the derivation, and the browser reads it from
the data file rather than holding a second copy of the number. **Every capture figure roughly
doubled**: the Fiscal Code takes **9,1%** of Romanian land rent, not 5,4%. Nothing about the
tax or the land moved — only the honesty of the denominator. The rate that would take the whole
rent fell with it, from about 3,7% of value to **2,2%**.

Two tests had to change, and one of them was a finding rather than a chore. Both asserted the
blended yield sat *below* the built-land one — which held only because 5% was the largest
number in any county by construction. At 2,53% it is not: Neamț's forest yields 3,52% and
Vrancea's 5,22%, because a yield is rent over price and those chambers price forest at a sixth
of what Iași does — 10 349 lei the hectare against 63 736. The invariant is now the one that
was always the real one: a weighted mean lies inside the range of its inputs.

**The country, from the half of it that has been read.** Twenty-two counties are priced from
grids and eighteen are not, so the only route to a national figure is to predict the missing
ones and say how wrong that is. The discarded predictors matter more than the kept one, because
both are what a reader would assume was used:

- *Built share of the county*, from the land register — **R² 0,04**. Prahova has the largest
  built share in the country and among the cheapest building land. The share measures villages
  spreading out, not towns being valuable.
- *The NUTS2 region* — under leave-one-out, **worse than having no predictor at all**: 2,64×
  against 2,12×. Nord-Vest holds Cluj and Sălaj; their mean predicts neither.
- *Population of the county's largest town* — **1,65×**, the only thing that beat the mean.
  Adding a second variable made leave-one-out worse every time. So the model is
  `log(EUR/ha) = a + b·log(largest town)` and nothing else, R² 0,58, fitted on 22 counties.

Farmland needs no predictor: its price per hectare varies far less, so each cadastral code is
transferred at its national geometric mean (arable ±1,51×). **The published band is the model's
own leave-one-out error, not a chosen width.**

**Romania without its capital: 288 mld EUR, band 181–461, 60% of it read rather than modelled.**
București and Ilfov are excluded and named — the fit's largest town is Iași at 390 000 people
and Bucharest has 2,14 million, and stretching a log-linear fit five and a half times past its
range is not extrapolation. Since that is the dearest land in the country, the total is a
floor.

**Vaslui was the test the model did not know it was taking.** It was predicted at 5,75 mld EUR
before anyone had read its study. Its grid, parsed afterwards, says **7,61 mld** — inside the
published band of 3,53–9,38, off by 1,32× against a stated error of 1,65×. One county is not a
validation, but it is the only out-of-sample check available and the model passed it.

**Vaslui also prices communes by class, and lists the classes in a sentence.** No commune has a
row of its own. A table prices `CATEGORIA 1 … 4`, and thirty pages later running prose says
which commune is which — `CATEGORIA 1 : Fălciu, Zorleni, Tutova.` That paragraph is the join,
and it is not a table.

**Its heading lies, identically, three times.** Each of the three court circumscriptions ends
with the same sentence: *"localitățile aflate pe raza circumscripției judecătoriei **Vaslui**,
au fost clasificate…"* — under Bârlad and under Huși as well. Attributing a list by what it
says about itself would have merged three circumscriptions and given two-thirds of the county
the wrong prices, with full name coverage and no error anywhere. Lists are attributed by
position instead. Two further bugs: the seat and component-village tables sit on one page under
one pair of captions, so testing the *page* for a caption priced every village at its seat's
rate; and a unit conversion to lei-per-hectare that the value builder does itself produced a
county worth **45 791 mld EUR** — four orders of magnitude, with every name matched, every
price a number, and 98,8% coverage. **VS: 98,8%, one commune missing** — Ivănești is in no
category list in the document.

**The ceiling is 22 counties, not 36, and that is now settled with evidence.** Every remaining
chamber was opened and measured rather than guessed at:

| chamber | counties | why not |
|---|---|---|
| Suceava | SV, BT | 42 land tables for 114 localities — prices circumscription *rural averages*, ceiling **37%** |
| Brașov | BV, CV | 4 land tables for 103 localities, ceiling **4%** |
| Pitești | AG, VL | scanned images: 70 pages, **zero characters** of text |
| Galați | GL, BR | GL has 5 land tables in 142 pages; Brăila is a scan |
| Craiova | DJ, GJ, OT, MH | 23 localities priced out of 359 |
| Timișoara | AR, CS | annexes contain no land at all |
| ~~București~~ | B, IF, CL, GR, IL, TR | **wrong — publishes on `srv.cnpb.ro`; B, IF and CL are read, three remain** |

Those are hard ceilings on what the documents contain, not on what the readers manage. Nothing
above 37% and most far below, against a 90% bar. **The estimate is not a shortcut around the
remaining counties — it is the only thing available for them.**

**The map now shows the whole country, and shows the difference.** Counties with a grid are
painted commune by commune. The rest are painted as one flat county-sized shape, on the same
scale, at half opacity, under a diagonal hatch — because a predicted county's value comes from
one regression coefficient and is known at county resolution and nowhere finer. The mosaic and
the flat shape are the difference in evidence, drawn.

**One rename, because the bug kept coming back.** The national file was briefly called
`valoare-teren-nationala-*.json`, which collided with the glob that finds the per-county
studies in four places — the estimator, the map builder, the forest yield and a test. Since its
`counties` list starts at AB, every one of them would have read the national estimate as Alba.
Filtering four call sites would have left the fifth for whoever writes it next; the prefix was
what was wrong, so it is `valoare-nationala-2026.json` now and the collision cannot recur.

**Timiș is read by geometry, because there is no table to read.** Its land annexes have no
ruling lines, so pdfplumber finds nothing; flattened to text they are worse than nothing,
because four independent `Localitate · Valoare` columns sit side by side and every line
interleaves all four:

    Jimbolia          zona A 38   Cenei 7   Giarmata 40   Albina 25
    zona B 15                     Bobda 6   Cerneteaz 35  Moșnița Veche  zona A 95

Read as a line, `zona B 15 Bobda 6` is one row of something. It is two halves of two different
communes. This is the first reader here to use the **word coordinates** the cache has been
storing all along: four `Localitate` headers at x ≈ 33, 209, 384 and 558 give the column edges,
and a zone row continues the locality above it *within its own column* — which is exactly what a
line-based reader cannot see.

Four bugs, each instructive. Rows had to be **clustered** rather than bucketed, because a
digit's baseline sits a point off a letter's and a fixed bin split the first row of every page
from its own prices. The note identifying the city's private annex is printed under the
per-locality ones too, so testing for it first took the county from 92% to 28%. The two halves
of that annex are told apart by their captions and not by size — Timișoara's extravilan is 8
and its cheapest zone is 50. And Timișoara numbers its zones **from nought**, so the label
itself contains a digit and the value had to be the last token on the row rather than the only
number on it.

Timișoara comes out at 600 down to 50 EUR/m² across six zones and Lugoj at 110/65/25, both
exactly as printed. **Timiș is now the most valuable county in the set at 25,5 mld EUR** — more
than Cluj, on a bigger area with a ring of expensive communes around the city.

**Craiova's four counties are not readable and that is settled.** Dolj, Gorj, Olt and Mehedinți
share one 309-page volume that prices intravilan for **23 localities out of 359** and gives a
single county-wide average per category for everything else. Timișoara's chamber covers Arad
and Caraș-Severin too, and their annexes contain no land at all. Both were checked against the
source rather than inferred from a low score.

Twenty-five counties read: **1 790 localities, 13,7 M ha, 57,3% of Romania, 235 mld EUR.**

**One chamber, four counties, and the same reader for all of them — after four bugs.** CNP Cluj
publishes Bistrița-Năsăud, Maramureș and Sălaj in Cluj's own layout, and the section-header fix
took them from 8%, 18% and 7% to the 90s. Getting the *values* right took four more:

*The intravilan run swallowed the buildings.* In the three sibling counties the construction
columns carry no caption in the header block, so the run from `Teren intravilan` continued to
`Anexe` and put Baia Mare's land at the price of its houses. The documents distinguish them
exactly and in every county: ground is `lei/mp`, a building is `lei/mpSd`. Reading the unit is
what separates them.

*The header block is not eight rows.* Sălaj carries one more blank line than its siblings, which
pushed the unit row out of the window and undid the fix for that county alone. The caption block
now ends where the numbers start.

*"ORAȘE" is not "COMUNE".* Cluj gives each town its own section header; the other three put all
their towns in one `ORAȘE / LOCALITĂȚI` block and their communes in `SATE / COMUNE`. Both rural
headers also contain the word for towns, so the town test had to come second.

*Column 1 is the circumscription.* Eight of Maramureș's eleven towns sit under `BAIA MARE` and
were being priced as Baia Mare. The locality is column 2, minus the `- ZONA n` its seat's own
rows carry.

Twenty counties: **1 518 localities, 11,6 M ha, 48,8% of Romania, 138 mld EUR**, and 89% of that
value on hectares that carry a price.

**Cluj had been looked for in the wrong dimension.** Three attempts had searched along each row
for a locality beside it, and reached 85% of the county's communes and none of its six urban
units. There is no locality beside those rows. Anexa 1 is cut into blocks by a row carrying one
cell and nothing else:

    CLUJ-NAPOCA
    1 · CLUJ-NAPOCA · Andrei Mureşanu  · 14.600 · … · 3.700
    2 ·             · Becaş - Borhanci · 13.600 · … ·   750
    TURDA + CÂMPIA TURZII
    COMUNE / ORAȘE / SATE

Every row until the next such header belongs to the town it names, one header names two towns,
and the last block switches the same table from towns to communes. The rows themselves are
neighbourhoods, which are not localities and never will be — no amount of looking along the row
was going to find Cluj-Napoca.

Reading the sections gives all six urban units and takes the county to **92,6%**. Cluj-Napoca
comes out as a band from **42 to 1 027 EUR/m²** across 79 districts, which is the widest spread
of any locality in the project and is the city's own: Centru against the edge of Baciu.

**A second bug was hiding behind the first.** Column 16 is captioned `Teren extravilan`, and the
row under it says *zona limitrofă cu intravilanul*. The group-detection assigned rather than
set-default, so that sub-caption relabelled the column as intravilan and **every extravilan
price in the county was discarded**. First caption wins now; all 69 communes have arable,
pasture, orchard and forest, and the county's arable at 41 500 lei/ha sits between the market's
two references.

Seventeen counties: **1 323 localities, 10,1 M ha, 42,4% of Romania, 129 mld EUR.**

**A cedilla cost Satu Mare a fifth of its hectares.** Its rural tables head the pasture column
`FÂNEAŢĂ`, with a t-cedilla — U+0163 — and the pattern looking for it was written with the
t-comma of the 1993 orthography, U+021B. The two render identically at any size a person reads
at, and are different characters, so the column matched nothing and was silently never read.
Fixing it, and then taking the two small tables each town publishes beside its zone grid, moved
the county from **41% to 62%** of its hectares priced and its land value from 3,4 to
**4,4 mld EUR**.

The same one-sided class turned up in two more readers and was widened before it could cost
anything. Bihor's forest was a plainer story — read and discarded, as everywhere else, which
left 183 000 hectares at nothing; keeping it took that county from **55% to 82%**.

Sixteen counties, **1 248 localities, 9,47 M ha, 39,7% of Romania, 113 mld EUR**, and 87% of
their value now rests on hectares that actually carry a price.

**The `evaluat` column earned itself.** It exists to say what share of a county's non-forest
hectares actually received a price, and Hunedoara sat at **17%** — the extravilan tables looked
like they covered five town seats and nothing else. They did not. Every one of them carries two
rows that name no locality at all:

    Tipul terenului Amplasament · Teren arabil · Pasuni-fanete · Livezi Vie · …
    Deva zona A                 ·      28      ·      14       ·     9      · …
    Centre de Comuna            ·     1,9      ·      1,2      ·     3      · …
    Sate                        ·     1,5      ·      0,8      ·    2,5     · …

`Centre de Comuna` and `Sate` price every commune in the court's circumscription. The reader
skipped them because they match no name in the register, which is exactly why they were there.
Reading them took Hunedoara from **17% to 98%** and its land value from 1,9 to **3,5 mld EUR**.

**The rest of the gaps are the documents, not the code.** Alba's table leaves the forest column
blank for 32 of its 67 communes; Sibiu's town table has no forest column at all; and Tulcea's
339 000 unpriced hectares are the Danube Delta's water. Each was checked against the source
before being left alone, and each stays visible as a `material` limitation and as an unpainted
commune on the map. Weighted by value, the fourteen counties are now **88% priced**.

**There is a map now, and it is the same arithmetic as the numbers.** Every commune in the
fourteen counties is painted from `evaluate()` — the function that produces the totals and the
table — through maplibre's feature state, so moving the intravilan share or the price band
repaints the country. A pre-rendered choropleth would have frozen at whatever assumptions were
current when it was built and then disagreed, silently, with the figures printed beside it.

The shapes are borrowed rather than fetched: `simulators/administrativ` already validated 3 186
UAT polygons against SIRUTA and refuses to build if one fails to match, and SIRUTA is the key
every row of this simulator already carries. `build_harta.py` filters them to the built
counties, simplifies to about a hundred metres and rounds coordinates to five decimals — 1 128
communes in 2,0 MB. **The join is 1 093 of 1 093**, and 35 shapes are left unpainted because
their county's own study does not price them.

**The map is mostly about what is missing.** Counties with no grid are drawn as an empty border
rather than as a zero, and unpriced communes stay unpainted inside a painted county. Both gaps
are already `material` limitations in the data; on a map they are the first thing you see
instead of a field in a JSON file nobody opens.

**A full land value tax is the yield itself.** Taking the whole of the rent means a rate on
value equal to the return land earns — 3 to 7% on the band used here. Every rate in the debate
should be read against that ceiling: the current tax is at roughly a thirtieth of it.

The yield is a parameter and the largest uncertainty in the file. Nobody publishes a land yield
for Romanian communes, so the 3–7% band is anchored on Romania's observed gross residential
yield — about 6,3% in 2025, 5–6% net — and pulled down because land does not depreciate. It is
a slider on the page, marked `blocking`, and the whole answer scales with it.

**The pipeline is national; the readers are not.** Everything up to the reading of a study
now runs for the whole country:

| stage | time | what it does |
| --- | --- | --- |
| `fetch_studies.py` | 53 s | finds all 62 study PDFs on the union's index and downloads 252 MB, 12 threads |
| `extract_cache.py` | 6 min | pypdf text plus pdfplumber tables, geometry and word boxes, 15 processes |
| `import_fond_funciar.py --all` | 3 s | the land register for **all 42 counties** |
| `survey_dialects.py` | 2 s | profiles every document: currency, decimals, merged-cell rate, column widths |
| `probe_readers.py` | 25 s | runs every reader against every study and reports coverage per county |

Cold, that is under eight minutes for the country. Warm, the whole simulator rebuilds in six
seconds.

**The cache is what changed.** Reading tables out of one county's PDF takes thirty seconds and
is perfectly deterministic, so doing it again after editing a regular expression proves
nothing — yet a reader takes fifteen or twenty attempts to write. Extracting once for the
country and parsing from the result took a chamber from **45 seconds an attempt to under
0,6 seconds**. It also caught a mistake worth recording: the cache first stored pdfplumber's
text, which breaks lines differently from pypdf's and renders a rotated caption as `J E L C A`,
and Bacău silently fell from 85 communes to 10. The cache now keeps the text each reader was
written against.

**The land register validates against the country.** All 42 counties sum to **23 839 071 ha**
against Romania's official 23 839 100 — twenty-nine hectares out in twenty-four million.

**Coverage replaced an all-or-nothing gate.** A county used to be refused whole for a single
locality the study does not price. It is now recorded and named, with a coverage figure, and
the importer still refuses below 90% — because that is a broken parse rather than a short
document. What stays fatal is the opposite failure: a place the parse invented, or counted
twice. Alba lands at **98,7%**, with Abrud named in the data and visible on the page, instead
of Alba not landing at all.

**Five counties of 41 are read, by five readers, and the rest is measured rather than
guessed.** `probe_readers.py` runs every reader against every chamber in 25 seconds:

| | counties |
| --- | --- |
| ready (≥90%) | **5** — Bacău, Neamț, Alba, Iași, Sibiu |
| the study does not publish per-locality land | 16 |
| parsed, then rejected on the values | 2 — Satu Mare, Bihor |
| still to investigate | 15 |

The studies are written by different valuation firms and share no layout — and the split runs
below the chamber, not just between chambers. CNP Iași prices Iași by sorting all 400 villages
into thirteen tiers and publishing one table for the tiers; its own Vaslui study, same chamber
and same year, does something else entirely and returns nothing to that reader.

**More of them than expected simply do not publish the thing.** A per-locality price for
building land is what a land value tax needs, and several chambers never print one:

| chamber | what it publishes instead |
| --- | --- |
| Craiova (DJ, GJ, MH, OT) | one extravilan price per hectare for the whole county |
| Timișoara (TM, AR, CS) | prose by circumscription, no ruled land tables |
| Brașov (BV, CV) | extravilan for 24 of ~170 localities; intravilan only as road segments — `DN 1 până la Ghimbav` — around the two county seats |
| Bucharest (B, IF, CL, GR, IL, TR) | no study at all, in 2026 or in 2025 |

That is sixteen counties where the answer is not a better parser. Two more were parsed to
92–94% of their names and rejected anyway, because the **values** were wrong: Satu Mare priced
its county seat at 10 €/m², and Bihor's Oradea moved from 1 200 to 228 to 42 lei/m² across
three successive fixes. A reader whose answer moves fivefold each time a bug is fixed is
fitting noise, not converging on the document — and no structural check catches that, which is
why the ordering of town prices against commune prices is now checked beside the coverage.

Inside towns the value depends on zone A–D and the zones are defined as **lists of
streets and house-number ranges**, not polygons; there is no published geometry for them, so
urban values are per-town and per-zone but cannot be put on a map below the town. And the
grids are legal floors, not transactions: they sit under market prices by a margin that is
neither published nor constant between counties. They rank places against each other far
better than they measure any of them, and that limitation is carried as `blocking` so it
reaches every figure derived from it.

## Decided: how the migration goes

No custom domain. URLs will be plain GitHub Pages project paths, one Pages site for the
whole repository:

```
cristiannichifor.github.io/romania-reforms/              the index
cristiannichifor.github.io/romania-reforms/justitie/
cristiannichifor.github.io/romania-reforms/salarizare/
cristiannichifor.github.io/romania-reforms/administrativ/
```

That breaks the links people already have, and for `salarizare` that matters more than it
looks: its whole design premise is that a scenario *is* a link, hash and all. So each old
repository stays alive as a one-page redirect that carries `location.hash` across, then
gets archived. Nothing shared before the move stops working.

A domain would remove the problem rather than absorb it, and the stubs are compatible with
adding one later — they would simply point somewhere else. Not needed now.

**Order, each step independently verifiable — after each, both old and new sites work:**

1. Move `salarizare`. Most tests, best understood, proves the layout under real load.
2. Extract `packages/ui` (`money.ts`, the dataviz primitives, the nav shell) only once
   `justitie` has an app that actually wants them — a second real consumer, not a guess.
3. Move `administrativ`, renaming `pipeline/` → `scripts/` and `web/` → `app/` to match.
4. Replace both old repositories with redirect stubs and archive them.

**Build:** both apps already read `VITE_BASE` from the environment instead of hardcoding a
path, so each is built with `VITE_BASE=/romania-reforms/<name>/` and the outputs are
assembled into one Pages artifact with the index. One deploy for the repository means one
broken build can block every simulator, so the assembly step should fail loudly and leave
the previous deployment standing rather than publish a site with a dead tile.

**Packaging:** a `uv` workspace with `members = ["simulators/*", "packages/*"]`, so each
simulator declares only the dependencies it uses — the flat list in the root
`pyproject.toml` is a placeholder for the single simulator that exists today. npm
workspaces over `simulators/*/app` and `packages/ui` on the Node side.

## Layout

```
packages/provenance   the shared vocabulary
scripts/              one validation gate for every simulator's data
simulators/<name>/    schema/ · scripts/ · data/ · sources/ · engine/ · app/
```

## Adding a reform

Five edits, deliberately by hand:

1. `simulators/<name>/` — its own `schema/`, `scripts/`, `data/`, `sources/`, and an app if it
   has one. Its data validated by its own script; the caveat vocabulary from
   `packages/provenance` so a limitation means the same thing across simulators.
2. A job in `.github/workflows/ci.yml`.
3. A build step in `.github/workflows/deploy.yml`, with `VITE_BASE` set to
   `/${{ github.event.repository.name }}/<name>/`.
4. A line in that workflow's assembly step, and its path in the check below it — the check is
   what stops a simulator that failed to build appearing on the landing page as a link to a
   404.
5. A card in `site/index.html`.

**Not a registry, and not a shared build.** Three simulators have three shapes: one React, one
not, one with no interface at all; `app/` in one and `web/` in another; different test
commands and different lockfiles. A config file over three special cases would be the same
mistake as extracting a UI package from a single consumer — it reads as generality and
behaves as a fourth thing to keep in sync. Five explicit edits are cheaper to get right than
one clever one, and the deploy check catches the one that matters if you forget it.

## Running it

```sh
uv run python simulators/justitie/scripts/import_instante.py   # fetches and parses
uv run python scripts/validate_data.py                          # the gate
```

Importers download their sources on first run and keep them, so a re-import does not
depend on a government website being up.
