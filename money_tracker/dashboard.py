"""M6 — Unified dashboard builder. Output is JSON-serializable.

Transfers (see money_tracker/transfers.py) are excluded from income/spend by
default so inter-account moves don't inflate both sides of the summary.

Each spend category is drillable: `transactions_by_category` lists every
underlying purchase (date, merchant, amount) so a category total can be
expanded into the transactions behind it. The `recurring` section flags
subscriptions and other fixed obligations detected by money_tracker/recurring.
"""

from __future__ import annotations
from decimal import Decimal

from money_tracker.models import Transaction
from money_tracker.net_worth import net_worth_over_time
from money_tracker.recurring import detect_recurring
from money_tracker.transfers import split_transfers


def _json_money(value):
    """Convert Decimal to a 2dp float for JSON output; pass other values through."""
    if isinstance(value, Decimal):
        return float(value.quantize(Decimal("0.01")))
    if isinstance(value, dict):
        return {k: _json_money(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_money(v) for v in value]
    return value


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

    by_category: dict[str, Decimal] = {}
    tx_by_category: dict[str, list] = {}
    for t in spend:
        by_category[t.category] = by_category.get(t.category, Decimal("0")) + abs(t.amount)
        tx_by_category.setdefault(t.category, []).append({
            "date": t.date,
            "description": t.description,
            "amount": float(t.amount),
            "account": t.account,
        })

    return {
        "summary": {
            "total_income": _json_money(sum((t.amount for t in income), Decimal("0"))),
            "total_spend": _json_money(sum((abs(t.amount) for t in spend), Decimal("0"))),
            "net_flow": _json_money(sum((t.amount for t in real), Decimal("0"))),
            "transaction_count": len(real),
            "transfer_count": transfer_count,
        },
        "spend_by_category": {
            k: _json_money(v) for k, v in
            sorted(by_category.items(), key=lambda kv: kv[1], reverse=True)
        },
        # drill-down: every purchase behind each category total
        "transactions_by_category": tx_by_category,
        # subscriptions / fixed obligations (see money_tracker/recurring.py)
        "recurring": _json_money(detect_recurring(real)),
        "net_worth_history": net_worth_over_time(snapshots),
        "budget": _json_money(budget_report),
    }
