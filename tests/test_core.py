"""M2/M3/M4/M5/M6 smoke tests — run with `make check`."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from money_tracker import (
    Transaction,
    classify, all_paths, import_csv, merge_transactions,
    is_transfer, map_provider_category, split_transfers,
    snapshot_net_worth, net_worth_over_time, save_snapshots, load_snapshots,
    BudgetPlanner, default_limits, build_dashboard,
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
    assert len(txns) == 13, f"expected 13 rows, got {len(txns)}"
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
    assert payload["summary"]["transfer_count"] == 2
    assert payload["spend_by_category"]["Housing/Rent"] == 1800.0
    assert payload["net_worth_history"] == [("2026-09-01", 70.0)]
    json.dumps(payload)  # must be JSON-serializable


def test_transfers():
    assert is_transfer("Demo Credit Card Payment")
    assert is_transfer("AUTOPAY - Demo Card")
    assert is_transfer("Savings Xfer")
    assert not is_transfer("Whole Foods Market")
    txns = [
        Transaction("2026-09-01", "Whole Foods", -10.0, "Food/Groceries"),
        Transaction("2026-09-02", "Demo Transfer", -50.0, "Uncategorized/Uncategorized"),
    ]
    real, xfers = split_transfers(txns)
    assert len(real) == 1 and len(xfers) == 1
    mapping = {"PFC_XFER": ("Finance/Fees", True)}
    assert map_provider_category("PFC_XFER", mapping) == ("Finance/Fees", True)
    assert map_provider_category("NOPE", mapping) == ("Uncategorized/Uncategorized", False)
    # invalid taxonomy path is demoted, transfer flag kept
    assert map_provider_category("BAD", {"BAD": ("Nope/Nope", True)}) == (
        "Uncategorized/Uncategorized", True)


def test_merge():
    a = Transaction("2026-09-01", "Whole Foods", -10.0, "Food/Groceries", "demo-card")
    dup = Transaction("2026-09-01", "whole foods ", -10.0, "Food/Groceries", "DEMO-CARD")
    new = Transaction("2026-09-02", "Uber", -20.0, "Transport/Rideshare", "demo-card")
    merged, added = merge_transactions([a], [dup, new])
    assert added == 1 and len(merged) == 2 and merged[1] is new


def test_snapshot_store():
    import tempfile
    snaps = [snapshot_net_worth("2026-09-01", {"a": 100.0}, {"l": 30.0})]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "snaps.json")
        assert load_snapshots(p) == []
        save_snapshots(p, snaps)
        loaded = load_snapshots(p)
        assert len(loaded) == 1
        assert loaded[0].as_of == "2026-09-01" and loaded[0].net_worth == 70.0


def test_default_limits():
    lims = default_limits()
    assert lims["Food/Groceries"] > 0 and lims["Housing/Rent"] > 0
    assert set(lims) <= set(all_paths())


if __name__ == "__main__":
    test_taxonomy()
    test_importer()
    test_net_worth()
    test_budget()
    test_dashboard()
    test_transfers()
    test_merge()
    test_snapshot_store()
    test_default_limits()
    print("all tests passed")
