"""M6 — Unified dashboard builder. Output is JSON-serializable."""

from __future__ import annotations

from money_tracker.models import Transaction
from money_tracker.net_worth import net_worth_over_time


def build_dashboard(transactions: list, snapshots: list, budget_report: dict) -> dict:
    """Assemble the unified money dashboard payload."""
    spend = [t for t in transactions if t.amount < 0]
    income = [t for t in transactions if t.amount > 0]

    by_category: dict[str, float] = {}
    for t in spend:
        by_category[t.category] = by_category.get(t.category, 0.0) + abs(t.amount)

    return {
        "summary": {
            "total_income": round(sum(t.amount for t in income), 2),
            "total_spend": round(sum(abs(t.amount) for t in spend), 2),
            "net_flow": round(sum(t.amount for t in transactions), 2),
            "transaction_count": len(transactions),
        },
        "spend_by_category": {
            k: round(v, 2) for k, v in
            sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)
        },
        "net_worth_history": net_worth_over_time(snapshots),
        "budget": budget_report,
    }
