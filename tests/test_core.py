"""M2/M3/M4/M5/M6 smoke tests — run with `make check`."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from money_tracker import (
    classify, import_csv, snapshot_net_worth, net_worth_over_time,
    BudgetPlanner, build_dashboard,
)

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "..", "sample_data", "demo_transactions.csv")


def test_taxonomy():
    assert classify("Whole Foods Market") == "Food/Groceries"
    assert classify("OMNY Transit") == "Transport/Transit"
    assert classify("Demo Payroll Deposit") == "Income/Salary"
    assert classify("??? unknown merchant") == "Uncategorized/Uncategorized"


def test_importer():
    txns, errors = import_csv(CSV)
    assert len(txns) == 11, f"expected 11 rows, got {len(txns)}"
    # one row has a blank category -> Uncategorized
    assert any(t.category == "Uncategorized/Uncategorized" for t in txns)
    # no bad-amount rows in the fixture
    assert errors == [], errors


def test_net_worth():
    s = snapshot_net_worth("2026-09-01", {"a": 100.0}, {"l": 30.0})
    assert s.net_worth == 70.0
    hist = net_worth_over_time([
        snapshot_net_worth("2026-09-01", {"a": 100.0}, {"l": 30.0}),
        snapshot_net_worth("2026-08-01", {"a": 90.0}, {"l": 30.0}),
    ])
    assert hist[0][0] == "2026-08-01" and hist[1][0] == "2026-09-01"


def test_budget():
    txns, _ = import_csv(CSV)
    planner = BudgetPlanner()
    planner.set_limits("2026-09", {"Food/Groceries": 400.0, "Housing/Rent": 1800.0})
    planner.add_transactions(txns)
    report = planner.report("2026-09")
    groceries = report["Food/Groceries"]
    assert groceries["spent"] == 186.42 + 74.21
    assert groceries["remaining"] == 400.0 - (186.42 + 74.21)
    rent = report["Housing/Rent"]
    assert rent["spent"] == 1800.0 and rent["variance"] == 0.0


def test_dashboard():
    txns, _ = import_csv(CSV)
    snapshots = [snapshot_net_worth("2026-09-01", {"a": 100.0}, {"l": 30.0})]
    payload = build_dashboard(txns, snapshots, {})
    assert payload["summary"]["transaction_count"] == 11
    assert payload["spend_by_category"]["Housing/Rent"] == 1800.0
    assert payload["net_worth_history"] == [("2026-09-01", 70.0)]
    json.dumps(payload)  # must be JSON-serializable


if __name__ == "__main__":
    test_taxonomy()
    test_importer()
    test_net_worth()
    test_budget()
    test_dashboard()
    print("all tests passed")
