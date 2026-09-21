"""Demo run: import demo CSV, apply budgets, build dashboard. Sample data only."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from money_tracker import (
    import_csv, merge_transactions, split_transfers,
    snapshot_net_worth, save_snapshots, load_snapshots,
    BudgetPlanner, default_limits, build_dashboard,
)
from sample_data.demo_snapshots import SNAPSHOTS

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "sample_data", "demo_transactions.csv")

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
planner.set_limits("2026-09", {
    "Food/Groceries": 400.00,
    "Food/Dining Out": 200.00,
    "Housing/Rent": 1800.00,
    "Transport/Transit": 100.00,
})
planner.add_transactions(transactions)
report = planner.report("2026-09")

snapshots = [
    snapshot_net_worth(s["as_of"], s["assets"], s["liabilities"])
    for s in SNAPSHOTS
]

import tempfile
store_path = os.path.join(tempfile.gettempdir(), "demo_snapshot_history.json")
save_snapshots(store_path, snapshots)
print(f"snapshot store round-trip: {len(load_snapshots(store_path))} snapshots")

dashboard = build_dashboard(transactions, snapshots, report)
print(json.dumps(dashboard, indent=2))
