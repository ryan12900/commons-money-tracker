"""Demo run: import demo CSV, apply budgets, build dashboard. Sample data only."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from money_tracker import (
    Transaction, import_csv, merge_transactions, split_transfers,
    snapshot_net_worth, save_snapshots, load_snapshots,
    credit_card_balances, BudgetPlanner, default_limits,
    detect_payroll, payroll_ytd, TransferLedger, build_ledger,
    build_dashboard,
)
from sample_data.demo_snapshots import SNAPSHOTS

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "sample_data", "demo_transactions.csv")


def main():
    transactions, errors = import_csv(CSV)
    if errors:
        print("import errors:", errors)

    real, transfers = split_transfers(transactions)
    print(f"imported {len(transactions)} rows; {len(transfers)} transfers excluded from spend/income")

    # re-importing the same CSV must add nothing (dedup)
    merged, added = merge_transactions(transactions, import_csv(CSV)[0])
    print(f"dedup re-import: {added} new rows (merged total {len(merged)})")
    print(f"default budget template covers {len(default_limits())} categories")

    planner = BudgetPlanner()
    # August groceries were untouched, so the full August limit rolls into September
    planner.set_limits("2026-08", {"Food/Groceries": 400.00})
    planner.set_limits("2026-09", {
        "Food/Groceries": 400.00,
        "Food/Dining Out": 200.00,
        "Housing/Rent": 1800.00,
        "Transport/Transit": 100.00,
    })
    planner.add_transactions(transactions)
    report = planner.report("2026-09")
    groceries = report["Food/Groceries"]
    print(f"rollover applied: Groceries rollover_in={groceries['rollover_in']} "
          f"available={groceries['available']} spent={groceries['spent']}")
    if report["unbudgeted"]:
        print(f"unbudgeted spend: {report['unbudgeted']}")

    rent = planner.rent_report("2026-09")
    print(f"rent: paid={rent['paid']} of limit={rent['limit']} "
          f"({rent['payment_count']} payment(s))")

    # biweekly payroll tracking (fictional "Demo Payroll Deposit" series)
    for p in detect_payroll(transactions):
        print(f"payroll: {p['merchant']} ({p['cadence']}, {p['occurrences']}x, "
              f"avg ${p['avg_amount']:.2f}, next expected {p['next_expected_date']})")
    print(f"payroll YTD 2026: ${payroll_ytd(transactions, '2026'):.2f}")

    # peer-payment ledger: a Zelle dinner payback is real spend, relabeled by hand
    ledger = build_ledger(transactions)
    zelle = Transaction("2026-09-05", "Zelle payment to Demo Dana", -40.00,
                        "Uncategorized/Uncategorized", "demo-checking")
    entry_id = ledger.add(zelle)
    ledger.relabel(entry_id, "Food/Dining Out")
    print(f"p2p ledger: {len(ledger.entries())} entries, "
          f"{len(ledger.unreviewed())} unreviewed, "
          f"relabeled spend={ledger.relabeled_spend()}")

    snapshots = [
        snapshot_net_worth(s["as_of"], s["assets"], s["liabilities"])
        for s in SNAPSHOTS
    ]
    latest = max(snapshots, key=lambda s: s.as_of)
    cards = credit_card_balances(latest)
    print(f"credit cards ({latest.as_of}): {cards['cards']} total={cards['total']}")

    import tempfile
    store_path = os.path.join(tempfile.gettempdir(), "demo_snapshot_history.json")
    save_snapshots(store_path, snapshots)
    print(f"snapshot store round-trip: {len(load_snapshots(store_path))} snapshots")

    dashboard = build_dashboard(transactions, snapshots, report)
    for r in dashboard["recurring"]:
        print(f"recurring: {r['merchant']} ({r['cadence']}, "
              f"{r['occurrences']}x, avg ${r['avg_amount']:.2f})")
    print(json.dumps(dashboard, indent=2))


if __name__ == "__main__":
    main()
