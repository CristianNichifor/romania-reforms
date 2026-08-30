# Who runs it, who buys it, who pays

The rest of this simulator produces buses, drivers, hours and a bill. None of that is a policy
until three parties can be named: who specifies the service, who operates it, and who pays the
difference between the fares and the cost. This document is that half. It contains no
arithmetic — every number in it is quoted from the model or from a source — because the design
questions here are not settled by computation.

The claim it defends: **this reform needs no new primary legislation.** The authority, the
contract form and the regulator all exist in Romanian law already. What is missing is the
network to put inside them.

## What the model has already decided

Four results constrain the institutional design before any preference enters.

**Routes cross commune boundaries.** 1 708 routes serve 249 centres across 42 counties,
reaching 2 923 of 3 186 UATs. A route from a village to its centre, or from that centre to the
county capital, cannot be specified by either commune at its ends. Whatever body orders this
service is larger than a commune. (Figures throughout are the committed pipeline run under the
default consolidation scenario; the browser recomputes them live against whatever scenario the
reader builds, so its numbers will differ.)

**The service is a fleet, not a set of routes.** 4 057 vehicles and 5 552 drivers, with the
15% spare ratio applied once to the network total rather than route by route. That saving only
exists if one party plans the whole county; thirty communes each buying their own bus buy more
buses.

**Traction is chosen per route.** Electric where a vehicle's daily distance fits the range,
otherwise hybrid or diesel by stop density. Electric buses are tied to a depot, because the
charger is a fixed asset in a fixed place. Whoever owns the depot constrains who can operate.

**Fares cover roughly 46% of operating cost.** The remaining 54% — some 0,95 md lei a year
against an operating cost of 1,75 md — is owed every year, for as long as the service runs.
That is a compensation payment against an obligation, not a grant, and compensation for a
public service obligation is a regulated instrument rather than a budget line anyone can
design freely.

## The law that already exists

**Regulation (EC) 1370/2007** on public passenger transport services by rail and by road is
directly applicable. It defines the public service contract, sets out when a contract may be
directly awarded and when it must be tendered (art. 5), caps the duration of a bus contract at
ten years (art. 4), and sets in its Annex the rules any compensation must satisfy to be
compatible with the internal market. Compensation that ignores the Annex is state aid.

**Legea 92/2007**, retitled by **Legea 328/2018** to *Legea serviciilor publice de transport
persoane în unitățile administrativ-teritoriale*, is the Romanian instrument. It covers county
services as well as local ones, treats them as community utility services, and allows them to
be organised at the level of an administrative-territorial unit **or of an intercommunity
development association (ADI)**. County councils hold the competence for county services;
**ANRSC** is the regulator.

The ADI matters more than it sounds. It is an existing legal vehicle for several UATs plus a
county council to jointly own and direct a service that none of them could specify alone —
which is precisely the shape the model's routes demand. It is used today for water and waste.

## What Denmark actually does

Denmark is the comparison this repository works from, so it is worth being exact rather than
gestural. Under the *Lov om trafikselskaber*, since 2008 Denmark has six regional transport
companies — NT, Midttrafik, Sydtrafik, FynBus, Movia and BAT. They are owned by the
municipalities and regions they serve. They **plan and tender**; they do not drive. Almost all
Danish bus operation is contracted out, with the transport companies acting as professional
procurement bodies on behalf of their owners.

Movia, the largest, is owned by 45 municipalities and two regions, turns over roughly DKK 4
billion, and covers close to half of that from ticket revenue. Its owners order the service
level and the routes; Movia advises them and runs the procurement. It must produce a mobility
plan every four years.

Two structural lessons, both of which survive translation:

- **The authority is larger than the municipality and smaller than the state.** Service level
  is a local political choice, so it is not made in the capital; networks cross boundaries, so
  it is not made in the village.
- **Planning and operating are separated.** The public body decides what runs; private
  operators compete to run it. Neither monopoly operation nor a deregulated market.

Movia is also the check on this model's fare recovery, and the direction matters. Movia
recovers close to half its cost from fares while serving the Copenhagen region. This model
recovers 45,9% from a purely rural network with Bucharest excluded — below Movia, which is the
right side to be on, because rural services recover less than urban ones everywhere. The
comparison is carried in `data/fares.json` as `benchmark.moviaRecovery`. It is a weak test: it
would also be passed by a model that was far too pessimistic, and the load factor remains the
free parameter of the fares layer.

## The design

**1. The buyer is a county transport authority, one per county.** Owned by the county council
together with the UAT centres in it, constituted as an ADI under Legea 92/2007. It plans the
network, sets the service level, owns the fares and the ticketing, tenders the operations and
manages the contracts. Forty-one of them, plus one for Bucharest–Ilfov, which the model already
treats as a single zone. The consolidation reform merges communes and leaves counties intact,
so this unit survives whatever scenario the reader builds.

Not the commune, because routes cross boundaries and a network-wide spare fleet cannot be
bought thirty times. Not the state, because the service level is the political choice being
offered to the reader of this simulator, and centralising it would remove the thing the
simulator exists to let people argue about.

**2. The contract is gross-cost.** The operator is paid per bus-kilometre and per bus-hour and
hands the fare revenue to the authority, which carries the revenue risk. This is exactly what
the model computes: `costs.py` produces cost per paid driver-hour, per bus-km and per
vehicle-year, which is the price structure of a gross-cost contract, not of a net-cost one.

The alternative, net-cost, makes the operator keep the fares and carry the demand risk. On a
network whose purpose is to serve thin markets — a commune of 1 200 people two hours from its
capital — net-cost gives the operator a direct incentive to degrade or abandon exactly the
routes the reform exists to create. It also makes integrated ticketing across operators nearly
impossible, because each one is defending its own revenue.

**3. Operations are competitively tendered, in lots, with staggered expiry.** Lots so that a
county is not held hostage by a single operator and so that mid-sized firms can bid; staggered
expiry so that the whole county does not change hands in one month. Ten years is the ceiling
under Reg. 1370/2007 art. 4, and there is a reason to sit below it — see the next point.

**4. Vehicles and depots are publicly owned and leased to the operator.** Vehicles and depots
together are the largest capital commitment in the model — the annualised vehicle line alone is
0,28 md lei a year against 1,75 md of operating cost, and depots cost more than the buses that
stand in them. A vehicle lasts twelve years; a contract may last ten. An operator asked to buy assets it cannot amortise inside its contract prices that
mismatch as a risk premium, and a bidder that expects to lose the next tender bids high or not
at all. Public ownership of the assets removes the residual-value risk from the bid, shortens
the contract that is viable, and widens the field of bidders — and for electric operation it is
close to unavoidable, because the charging infrastructure is a fixed installation whose value
cannot follow a departing operator.

This is why the model carries depot capital as its own line rather than folding it into a cost
per bus-hour: under this design it is the authority's balance sheet, not the operator's price.

**5. The payer is the state budget.** Deliberately not allocated in the model. Allocating the
42% between the state, counties and communes is a distributional argument that should be had
against a network people have agreed on, not smuggled into its design. The model produces the
total and stops there.

## What this design costs, and does not say

**The authorities themselves are not costed.** Forty-two bodies doing planning, procurement,
contract management and revenue collection is real money and real staff. The nearest line in
`cost.json` is `admin`, 0,19 md lei, which is an operator's dispatch and overhead charged as a
share of direct cost — not an authority's payroll. No line contains the authority. It belongs in the ledger against the administrative saving the
consolidation claims, and it is not there. This is the largest known omission in the
institutional half.

**ANRSC's tariff instrument does not fit.** The methodology in Ordinul ANRSC 272/2007 is built
around lei/km/loc — cost per vehicle-kilometre divided by average seats — which is a net-cost,
per-operator tariff. It is the same figure that could not be converted for the Buzău benchmark
elsewhere in this repository. A gross-cost regime tendered under Reg. 1370/2007 needs a
different regulatory instrument, and producing one is a real legislative task even though the
enabling law exists.

**Rail is left at the interface.** The commuter layer implies an arrangement with the national
operator and with ARF for the regional services, plus the extra track this repository costs at
282 md lei. Who orders a commuter train, and against whose budget, is not designed here.

**Fares are not set.** The model uses a fare per passenger-kilometre taken from two county
council decisions. Whether the network should have a distance tariff, a zonal one, or free
travel for some groups, is a live policy question and the model deliberately takes no position
beyond recording that free travel for pupils and pensioners is not modelled at all.

## Why this is the weakest part of the repository

Everything else here is checked against something: speeds against 552 recorded journeys, depot
cost against a tendered project with a published capacity, demand against Eurostat national
totals, fare recovery against Movia, cost per kilometre against wage-adjusted European
operations. This document is checked against nothing. It is a design
argued from the model's own constraints and from what Denmark demonstrably does, and a
competent transport lawyer would find things in it to correct.

It is included because a cost model without an institutional design is not a policy — it is a
spreadsheet that quietly assumes someone will sort this out. Naming the design makes it
arguable. That is the whole standard of this repository, applied to the part of it that cannot
be computed.
