"""M6 — Unified dashboard builder. Output is JSON-serializable.

Transfers (see money_tracker/transfers.py) are excluded from income/spend by
default so inter-account moves don't inflate both sides of the summary.

Each spend category is drillable: `transactions_by_category` lists every
underlying purchase (date, merchant, location, items, amount) so a category
total can be expanded into the transactions behind it. The `recurring`
section flags subscriptions and other fixed obligations detected by
money_tracker/recurring; `payroll` flags biweekly income deposits
(money_tracker/payroll); `credit_card_balances` breaks out card balances
from the latest snapshot.
"""

from __future__ import annotations
from decimal import Decimal

from money_tracker.models import Transaction
from money_tracker.net_worth import credit_card_balances, net_worth_over_time
from money_tracker.payroll import detect_payroll
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
    data_source: str = "sample",
) -> dict:
    """Assemble the unified money dashboard payload.

    `data_source` labels where the input data came from ("sample" by
    default; "plaid"/"coinbase" when a live-local adapter fed the inputs).
    It is a label only — the caller is responsible for sourcing the
    transactions/snapshots from the matching adapter (see
    money_tracker/data_source.get_adapter).
    """
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
            "merchant": t.merchant,
            "location": t.location,
            "items": list(t.items),
            "amount": _json_money(t.amount),
            "account": t.account,
        })

    latest_snapshot = max(snapshots, key=lambda s: s.as_of) if snapshots else None

    return {
        # where the input data came from: "sample" (default) or a live-local
        # adapter id such as "plaid"/"coinbase" (see data_source.py)
        "data_source": data_source,
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
        # biweekly payroll deposits (see money_tracker/payroll.py)
        "payroll": _json_money(detect_payroll(real)),
        # balances by credit card, from the latest snapshot
        "credit_card_balances": _json_money(
            credit_card_balances(latest_snapshot)
        ) if latest_snapshot else {"cards": {}, "total": 0.0},
        "net_worth_history": net_worth_over_time(snapshots),
        "budget": _json_money(budget_report),
    }
