"""What the transport authorities themselves cost.

`INSTITUTIONS.md` proposes forty-two county transport authorities — the body that plans the
network, sets the service level, owns the fares and tenders the operations. Until this module
existed, no line in `cost.json` contained them, and the ledger compared a transport cost that
was missing its own institution against an administrative saving. That understated the
transport side of the central comparison by an unquantified amount, which is the one way this
repository's headline could mislead.

**Built bottom-up, checked against Movia.** The authority is costed from what it is — a staff
of planners, procurement and revenue people, plus the systems they run — rather than as a
share of something else. A share would have been easier and would have hidden the only number
worth arguing about, which is how many people a county authority needs.

The check is Denmark's, and it is a real one. Movia's 2025 accounts separate the operator
payments it makes from the cost of being Movia: 3 464,7 m DKK to operators for bus, against
226,6 m of bus support plus bus's 84,4% share of 371,6 m of common expenses — 540,3 m, or
**15,6% of operator cost**. If this model lands near that, two unrelated methods agree; if it
lands far below, either a Romanian authority is genuinely leaner or the staffing is too thin.
The gap is reported, never closed by moving the staff count.

**Why the two should not match exactly.** Movia runs Rejsekort, the DOT cooperation, customer
centres and marketing across 45 municipalities and two regions. A county authority starting
from nothing is a smaller thing. Landing below Movia is expected; landing at half of it would
say the staffing is optimistic.

**One boundary is knowingly blurred.** `adminOverheadShare` bills the operator 12% for
dispatch, administration, ticket sales and revenue protection. Under the gross-cost design in
`INSTITUTIONS.md` the last two belong to the authority, so they are counted twice — once in
the operator's overhead and once here. The overlap inflates the total, which is the safe
direction for a cost that is being compared against a saving, and it is declared rather than
quietly netted off: splitting the 12% would need a basis this repository does not have.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

MONTHS_PER_YEAR: Final[int] = 12


@dataclass(frozen=True)
class Authority:
    """A year of authority cost, kept in the two parts it is built from."""

    count: int
    staff_each: int
    salaries_ron: float
    non_staff_ron: float

    @property
    def total_ron(self) -> float:
        return self.salaries_ron + self.non_staff_ron

    @property
    def per_authority_ron(self) -> float:
        return self.total_ron / self.count if self.count else 0.0

    @property
    def staff_total(self) -> int:
        return self.count * self.staff_each


def authority_cost(
    count: int,
    staff_each: int,
    gross_monthly_ron: float,
    employer_rate: float,
    non_staff_share: float,
) -> Authority:
    """Salaries first, then everything that is not a salary.

    `non_staff_share` is the share of the authority's whole budget that is *not* payroll —
    ticketing and IT systems, premises, information, audit. It is applied as a share of the
    total rather than as a markup on salaries, because that is how Movia reports it and how
    a budget is actually written: a fixed markup would make the systems bill scale with
    headcount, which it does not.
    """
    if not 0.0 <= non_staff_share < 1.0:
        raise ValueError(f"non_staff_share must be in [0, 1), got {non_staff_share}")
    if count < 0 or staff_each < 0:
        raise ValueError("count and staff_each must not be negative")

    salaries = count * staff_each * gross_monthly_ron * (1 + employer_rate) * MONTHS_PER_YEAR
    total = salaries / (1 - non_staff_share)
    return Authority(
        count=count,
        staff_each=staff_each,
        salaries_ron=salaries,
        non_staff_ron=total - salaries,
    )


def share_of_operator_cost(authority: Authority, operator_ron: float) -> float:
    """The figure that compares directly with Movia's 15,6%."""
    return authority.total_ron / operator_ron if operator_ron else 0.0
