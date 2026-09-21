"""M9 — Biweekly payroll tracking.

Finds regular payroll deposits: positive-amount transactions that repeat on
a biweekly cadence (the standard US payroll rhythm — e.g. a biweekly direct
deposit). Built on money_tracker/recurring so the cadence bands stay in one
place.

Sample/demo data only — run this over the user's own import, not fixtures.
"""

import datetime
from decimal import Decimal

from money_tracker.recurring import detect_recurring

# A biweekly pay period is 14 days; the recurring bands allow 12-16.
_PAY_PERIOD_DAYS = 14


def detect_payroll(transactions: list, min_occurrences: int = 3) -> list:
    """Flag biweekly income deposits as payroll series.

    Returns [{merchant, cadence ("biweekly"), occurrences, avg_amount
    (Decimal), last_date, next_expected_date}], sorted by average amount
    descending. Only positive-amount series on the biweekly cadence count —
    a biweekly *bill* is a subscription, not payroll.
    """
    income = [t for t in transactions if t.amount > 0]
    payroll = []
    for series in detect_recurring(income, min_occurrences=min_occurrences):
        if series["cadence"] != "biweekly":
            continue
        last = datetime.date.fromisoformat(series["last_date"])
        payroll.append({
            **series,
            "next_expected_date": (
                last + datetime.timedelta(days=_PAY_PERIOD_DAYS)
            ).isoformat(),
        })
    return sorted(payroll, key=lambda r: r["avg_amount"], reverse=True)


def payroll_ytd(transactions: list, year: str) -> Decimal:
    """Total payroll-deposit income for a calendar year (YYYY).

    A transaction counts when its description matches a detected payroll
    series merchant — keyword matching is exact on the normalized merchant
    name, never fuzzy.
    """
    merchants = {p["merchant"] for p in detect_payroll(transactions)}
    total = Decimal("0")
    for t in transactions:
        if (t.date.startswith(year) and t.amount > 0
                and t.description.strip().lower() in merchants):
            total += t.amount
    return total
