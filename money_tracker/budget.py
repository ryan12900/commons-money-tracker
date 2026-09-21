"""M5 — Budget planner: monthly limits with rollover + variance.

Rollover: unspent budget (limit - spent, floored at 0) is APPLIED to the next
month — last month's rollover becomes this month's `rollover_in` and is added
to the limit to form the month's `available` amount. Only the unspent part of
the base limit rolls (a prior rollover does not roll again), so rollover
cannot compound indefinitely.

Variance: actual spend minus limit (positive = over budget).
"""

from __future__ import annotations
from decimal import Decimal

from money_tracker.models import Transaction


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
        """month = 'YYYY-MM'. limits = {category path: amount}."""
        self.limits[month] = {k: Decimal(str(v)) for k, v in limits.items()}

    def add_transactions(self, transactions: list) -> None:
        self.transactions.extend(transactions)

    def _spent(self, month: str) -> dict:
        spent: dict[str, Decimal] = {}
        for t in self.transactions:
            if t.date.startswith(month) and t.amount < 0:
                spent[t.category] = spent.get(t.category, Decimal("0")) + abs(t.amount)
        return spent

    def report(self, month: str) -> dict:
        """Per-category {limit, rollover_in, available, spent, remaining,
        variance} + rollover_to_next for the following month."""
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
        return report


def default_limits() -> dict:
    """Starter budget template (demo amounts, USD/month).

    Round placeholder numbers only — tune every limit to your own spending
    before relying on a report. Never commit real budget figures as "defaults".
    """
    return {
        "Food/Groceries": 500.00,
        "Food/Dining Out": 300.00,
        "Food/Coffee": 75.00,
        "Food/Delivery": 120.00,
        "Housing/Rent": 2000.00,
        "Housing/Utilities": 150.00,
        "Transport/Transit": 120.00,
        "Transport/Rideshare": 120.00,
        "Health/Gym": 60.00,
        "Shopping/Clothing": 250.00,
        "Entertainment/Streaming": 40.00,
    }
