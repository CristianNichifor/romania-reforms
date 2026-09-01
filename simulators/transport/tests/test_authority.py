"""Tests for the authority cost.

This line exists because the ledger was comparing a transport cost that was missing its own
institution against an administrative saving that was complete. The tests guard the two
properties that make it honest: it is built from people rather than from a percentage, and
the non-salary share behaves like a budget rather than like a markup on headcount.
"""

from __future__ import annotations

import pytest

from scripts.authority import authority_cost, share_of_operator_cost

WAGE = 9_564.0
RATE = 0.0225


def test_salaries_are_the_staff_times_the_employer_cost_of_one():
    authority = authority_cost(
        count=2, staff_each=10, gross_monthly_ron=WAGE, employer_rate=RATE, non_staff_share=0.0
    )
    assert authority.salaries_ron == pytest.approx(2 * 10 * WAGE * (1 + RATE) * 12)
    assert authority.non_staff_ron == 0.0
    assert authority.staff_total == 20


def test_the_non_salary_part_is_a_share_of_the_budget_not_a_markup_on_pay():
    """The distinction is load-bearing. At a 45% non-staff share the salaries are 55% of the
    total, so the total is salaries / 0,55 — not salaries × 1,45, which would be 1,45/1,82 of
    the right answer and would make the ticketing bill grow with headcount. Movia's support
    costs are dominated by Rejsekort and IT, which do not scale with how many planners it
    employs."""
    authority = authority_cost(
        count=1, staff_each=10, gross_monthly_ron=WAGE, employer_rate=RATE, non_staff_share=0.45
    )
    assert authority.non_staff_ron / authority.total_ron == pytest.approx(0.45)
    assert authority.salaries_ron / authority.total_ron == pytest.approx(0.55)
    markup = authority.salaries_ron * 1.45
    assert authority.total_ron > markup, "a markup would understate the budget"


def test_doubling_the_staff_doubles_the_whole_budget():
    """It is a per-head model, so this must hold — and it is what makes the staff count the
    one figure worth arguing about."""
    small = authority_cost(
        count=1, staff_each=11, gross_monthly_ron=WAGE, employer_rate=RATE, non_staff_share=0.45
    )
    large = authority_cost(
        count=1, staff_each=22, gross_monthly_ron=WAGE, employer_rate=RATE, non_staff_share=0.45
    )
    assert large.total_ron == pytest.approx(2 * small.total_ron)


def test_an_authority_with_nobody_in_it_costs_nothing():
    """Guards the division: a zero-staff authority must not inherit a systems budget."""
    empty = authority_cost(
        count=42, staff_each=0, gross_monthly_ron=WAGE, employer_rate=RATE, non_staff_share=0.45
    )
    assert empty.total_ron == 0.0


def test_a_non_staff_share_of_one_is_refused():
    """It would divide by zero and report an infinite authority, which would sail through any
    check that only asks whether the number is positive."""
    for bad in (1.0, 1.5, -0.1):
        with pytest.raises(ValueError, match="non_staff_share"):
            authority_cost(
                count=1,
                staff_each=1,
                gross_monthly_ron=WAGE,
                employer_rate=RATE,
                non_staff_share=bad,
            )


def test_the_share_against_operator_cost_is_the_movia_comparison():
    authority = authority_cost(
        count=1, staff_each=10, gross_monthly_ron=WAGE, employer_rate=RATE, non_staff_share=0.5
    )
    assert share_of_operator_cost(authority, authority.total_ron * 10) == pytest.approx(0.1)
    # No operator means no ratio rather than a division by zero.
    assert share_of_operator_cost(authority, 0.0) == 0.0
