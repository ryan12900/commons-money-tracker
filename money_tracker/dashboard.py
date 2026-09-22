"""M6 — Unified dashboard builder. Output is JSON-serializable.

Transfers (see money_tracker/transfers.py) are excluded from income/spend by
default so inter-account moves don't inflate both sides of the summary.
"""

from __future__ import annotations

from money_tracker.models import Transaction
from money_tracker.net_worth import net_worth_breakdown, net_worth_over_time
from money_tracker.transfers import split_transfers


def _breakdown_floats(bd: dict) -> dict:
    """Decimal breakdown -> JSON-safe floats, in this module's round(x, 2) style."""
    return {
        "assets": {k: round(float(v), 2) for k, v in bd["assets"].items()},
        "liabilities": {k: round(float(v), 2) for k, v in bd["liabilities"].items()},
        "asset_share_pct": {k: round(v, 2) for k, v in bd["asset_share_pct"].items()},
        "liability_share_pct": {k: round(v, 2) for k, v in bd["liability_share_pct"].items()},
        "total_assets": round(float(bd["total_assets"]), 2),
        "total_liabilities": round(float(bd["total_liabilities"]), 2),
        "net_worth": round(float(bd["net_worth"]), 2),
    }


def build_dashboard(
    transactions: list,
    snapshots: list,
    budget_report: dict,
    exclude_transfers: bool = True,
) -> dict:
    """Assemble the unified money dashboard payload."""
    real = transactions
    transfer_count = 0
    if exclude_transfers:
        real, transfers = split_transfers(transactions)
        transfer_count = len(transfers)

    spend = [t for t in real if t.amount < 0]
    income = [t for t in real if t.amount > 0]

    by_category: dict[str, float] = {}
    for t in spend:
        by_category[t.category] = by_category.get(t.category, 0.0) + abs(t.amount)

    return {
        "summary": {
            "total_income": round(sum(t.amount for t in income), 2),
            "total_spend": round(sum(abs(t.amount) for t in spend), 2),
            "net_flow": round(sum(t.amount for t in real), 2),
            "transaction_count": len(real),
            "transfer_count": transfer_count,
        },
        "spend_by_category": {
            k: round(v, 2) for k, v in
            sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)
        },
        "net_worth_history": net_worth_over_time(snapshots),
        # class-by-class net-worth breakdown for the latest snapshot
        "net_worth_breakdown": _breakdown_floats(
            net_worth_breakdown(max(snapshots, key=lambda s: s.as_of))
        ) if snapshots else {},
        "budget": budget_report,
    }
