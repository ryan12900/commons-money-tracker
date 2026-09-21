"""M5 — Budget planner: monthly limits with rollover + variance.

Rollover: unspent budget (limit - spent, floored at 0) carries forward
into next month's available amount for that category.
Variance: actual spend minus limit (positive = over budget).
"""

from __future__ import annotations

from money_tracker.models import Transaction


class BudgetPlanner:
    def __init__(self):
        self.limits: dict[str, dict] = {}      # month -> {category: limit}
        self.transactions: list[Transaction] = []

    def set_limits(self, month: str, limits: dict) -> None:
        """month = 'YYYY-MM'. limits = {category path: amount}."""
        self.limits[month] = dict(limits)

    def add_transactions(self, transactions: list) -> None:
        self.transactions.extend(transactions)

    def _spent(self, month: str) -> dict:
        spent: dict[str, float] = {}
        for t in self.transactions:
            if t.date.startswith(month) and t.amount < 0:
                spent[t.category] = spent.get(t.category, 0.0) + abs(t.amount)
        return spent

    def report(self, month: str) -> dict:
        """Per-category {limit, spent, remaining, variance} + rollover info."""
        spent = self._spent(month)
        limits = self.limits.get(month, {})
        report = {}
        for category, limit in limits.items():
            actual = spent.get(category, 0.0)
            report[category] = {
                "limit": limit,
                "spent": actual,
                "remaining": limit - actual,
                "variance": actual - limit,
                "rollover_to_next": max(0.0, limit - actual),
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
