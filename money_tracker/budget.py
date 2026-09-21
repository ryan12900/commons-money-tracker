"""M5 — Budget planner: monthly limits with rollover + variance.

Rollover: unspent budget (limit - spent, floored at 0) is APPLIED to the next
month — last month's rollover becomes this month's `rollover_in` and is added
to the limit to form the month's `available` amount. Only the unspent part of
the base limit rolls (a prior rollover does not roll again), so rollover
cannot compound indefinitely.

Variance: actual spend minus limit (positive = over budget).

Spend is transfer-aware: transactions whose description matches
transfers.is_transfer() are inter-account moves, not spending, and are
excluded from every spend total (so a credit-card payment can never inflate
"unbudgeted"). The rent report is a dedicated Housing/Rent view — payment
history plus limit tracking for the month.
"""

from __future__ import annotations
from decimal import Decimal

from money_tracker.models import Transaction
from money_tracker.taxonomy import all_paths
from money_tracker.transfers import is_transfer

_VALID_PATHS = set(all_paths())
_RENT_CATEGORY = "Housing/Rent"


def _prev_month(month: str) -> str:
    """'2026-09' -> '2026-08'."""
    y, m = int(month[:4]), int(month[5:7])
    m -= 1
    if m == 0:
        m, y = 12, y - 1
    return f"{y:04d}-{m:02d}"


class BudgetPlanner:
    def __init__(self):
        self.limits: dict[str, dict] = {}      # month -> {category: Decimal}
        self.transactions: list[Transaction] = []

    def set_limits(self, month: str, limits: dict) -> None:
        """month = 'YYYY-MM'. limits = {category path: amount}.

        Category paths are validated against the taxonomy — a typo raises
        ValueError instead of silently producing an empty report section.
        """
        bad = [k for k in limits if k not in _VALID_PATHS]
        if bad:
            raise ValueError(
                f"unknown category path(s): {bad} — "
                f"valid paths: {sorted(_VALID_PATHS)}"
            )
        self.limits[month] = {k: Decimal(str(v)) for k, v in limits.items()}

    def add_transactions(self, transactions: list) -> None:
        self.transactions.extend(transactions)

    def _spent(self, month: str) -> dict:
        """Per-category spend for a month, transfers excluded.

        Inter-account moves are not spending: without this filter a
        credit-card payment would inflate "unbudgeted" and poison rollover
        math. See transfers.is_transfer() for the keyword heuristic.
        """
        spent: dict[str, Decimal] = {}
        for t in self.transactions:
            if (t.date.startswith(month) and t.amount < 0
                    and not is_transfer(t.description)):
                spent[t.category] = spent.get(t.category, Decimal("0")) + abs(t.amount)
        return spent

    def report(self, month: str) -> dict:
        """Per-category {limit, rollover_in, available, spent, remaining,
        variance} + rollover_to_next for the following month.

        Also includes an "unbudgeted" key: {category: spent} for categories
        with spending but no limit this month, so unbudgeted spend is never
        invisible in the report.
        """
        spent = self._spent(month)
        limits = self.limits.get(month, {})
        prev_spent = self._spent(_prev_month(month))
        prev_limits = self.limits.get(_prev_month(month), {})
        report = {}
        for category, limit in limits.items():
            actual = spent.get(category, Decimal("0"))
            prev_actual = prev_spent.get(category, Decimal("0"))
            prev_limit = prev_limits.get(category, Decimal("0"))
            rollover_in = max(Decimal("0"), prev_limit - prev_actual)
            available = limit + rollover_in
            report[category] = {
                "limit": limit,
                "rollover_in": rollover_in,
                "available": available,
                "spent": actual,
                "remaining": available - actual,
                "variance": actual - limit,
                "rollover_to_next": max(Decimal("0"), limit - actual),
            }
        report["unbudgeted"] = {
            category: amount for category, amount in spent.items()
            if category not in limits
        }
        return report

    def rent_report(self, month: str) -> dict:
        """Dedicated rent view for a month (YYYY-MM).

        Returns {month, paid, limit, remaining, payments: [{date, amount,
        description, account}], payment_count}. Transfers are excluded from
        `paid` — a transfer that happens to sit in Housing/Rent is a money
        move, not rent.
        """
        payments = [
            {
                "date": t.date,
                "amount": abs(t.amount),
                "description": t.description,
                "account": t.account,
            }
            for t in self.transactions
            if (t.date.startswith(month) and t.amount < 0
                    and t.category == _RENT_CATEGORY
                    and not is_transfer(t.description))
        ]
        payments.sort(key=lambda p: p["date"])
        paid = sum((p["amount"] for p in payments), Decimal("0"))
        limit = self.limits.get(month, {}).get(_RENT_CATEGORY, Decimal("0"))
        return {
            "month": month,
            "paid": paid,
            "limit": limit,
            "remaining": limit - paid,
            "payments": payments,
            "payment_count": len(payments),
        }


def default_limits() -> dict:
    """Starter budget template (demo amounts, USD/month).

    Round placeholder numbers only — tune every limit to your own spending
    before relying on a report. Never commit real budget figures as "defaults".
    """
    return {
        "Food/Groceries": Decimal("500.00"),
        "Food/Dining Out": Decimal("300.00"),
        "Food/Coffee": Decimal("75.00"),
        "Food/Delivery": Decimal("120.00"),
        "Housing/Rent": Decimal("2000.00"),
        "Housing/Utilities": Decimal("150.00"),
        "Transport/Transit": Decimal("120.00"),
        "Transport/Rideshare": Decimal("120.00"),
        "Health/Gym": Decimal("60.00"),
        "Shopping/Clothing": Decimal("250.00"),
        "Entertainment/Streaming": Decimal("40.00"),
    }
