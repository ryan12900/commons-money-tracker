"""M2/M3/M4/M5/M6/M8 smoke tests — run with `make check`."""

import json
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from money_tracker import (
    Transaction,
    classify, all_paths, import_csv, merge_transactions, valid_date,
    is_transfer, map_provider_category, split_transfers,
    snapshot_net_worth, net_worth_over_time, save_snapshots, load_snapshots,
    BudgetPlanner, default_limits,
    detect_recurring, build_dashboard,
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
    assert len(txns) == 24, f"expected 24 rows, got {len(txns)}"
    # one row has a blank category -> Uncategorized
    assert any(t.category == "Uncategorized/Uncategorized" for t in txns)
    # no bad rows in the fixture
    assert errors == [], errors
    # amounts are Decimal
    assert all(isinstance(t.amount, Decimal) for t in txns)


def test_date_validation():
    assert valid_date("2026-09-01")
    assert not valid_date("09/01/2026")   # wrong format
    assert not valid_date("2026-02-30")   # not a real calendar date
    assert not valid_date("")             # missing
    assert not valid_date(None)           # None


def test_importer_rejects_bad_dates_and_amounts():
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
        f.write("date,description,amount,category,account\n")
        f.write("2026-09-01,Good Row,-10.00,Food/Coffee,demo-card\n")
        f.write("09/02/2026,Bad Format,-5.00,Food/Coffee,demo-card\n")
        f.write("2026-02-30,Bad Calendar,-5.00,Food/Coffee,demo-card\n")
        f.write("2026-09-04,Bad Amount,abc,Food/Coffee,demo-card\n")
        path = f.name
    try:
        txns, errors = import_csv(path)
    finally:
        os.unlink(path)
    assert len(txns) == 1 and txns[0].description == "Good Row"
    assert len(errors) == 3, errors
    assert sum("bad date" in e for e in errors) == 2
    assert sum("bad amount" in e for e in errors) == 1


def test_net_worth():
    s = snapshot_net_worth("2026-09-01", {"a": 100.0}, {"l": 30.0})
    assert s.net_worth == Decimal("70.0")
    hist = net_worth_over_time([
        snapshot_net_worth("2026-09-01", {"a": 100.0}, {"l": 30.0}),
        snapshot_net_worth("2026-08-01", {"a": 90.0}, {"l": 30.0}),
    ])
    assert hist[0][0] == "2026-08-01" and hist[1][0] == "2026-09-01"
    assert hist[0][1] == 60.0 and hist[1][1] == 70.0  # floats for JSON


def test_budget():
    txns, _ = import_csv(CSV)
    planner = BudgetPlanner()
    # August: Groceries budget untouched -> full 400 rolls forward
    planner.set_limits("2026-08", {"Food/Groceries": 400.0})
    planner.set_limits("2026-09", {"Food/Groceries": 400.0, "Housing/Rent": 1800.0})
    planner.add_transactions(txns)
    report = planner.report("2026-09")
    groceries = report["Food/Groceries"]
    assert groceries["spent"] == Decimal("260.63")
    assert groceries["rollover_in"] == Decimal("400.00")   # applied, not just computed
    assert groceries["available"] == Decimal("800.00")
    assert groceries["remaining"] == Decimal("539.37")
    assert groceries["variance"] == Decimal("-139.37")
    assert groceries["rollover_to_next"] == Decimal("139.37")
    rent = report["Housing/Rent"]
    assert rent["rollover_in"] == Decimal("0")
    assert rent["spent"] == Decimal("1800.00") and rent["variance"] == Decimal("0")


def test_dashboard():
    txns, _ = import_csv(CSV)
    snapshots = [snapshot_net_worth("2026-09-01", {"a": 100.0}, {"demo-card": 30.0})]
    payload = build_dashboard(txns, snapshots, {})
    assert payload["summary"]["transaction_count"] == 20
    assert payload["summary"]["transfer_count"] == 4
    assert payload["summary"]["total_income"] == 25200.0
    assert payload["summary"]["total_spend"] == 2463.72
    assert payload["summary"]["net_flow"] == 22736.28
    assert payload["spend_by_category"]["Housing/Rent"] == 1800.0
    # category drill-down: every purchase behind the total
    groceries = payload["transactions_by_category"]["Food/Groceries"]
    assert {g["description"] for g in groceries} == {"Whole Foods Market", "Trader Joes"}
    assert all(set(g) == {"date", "description", "merchant", "location",
                          "items", "amount", "account"} for g in groceries)
    whole_foods = next(g for g in groceries if g["description"] == "Whole Foods Market")
    assert whole_foods["merchant"] == "Whole Foods Market"
    assert whole_foods["location"] == "New York, NY"
    assert whole_foods["items"] == ["Organic Milk", "Bananas", "Rotisserie Chicken"]
    # payroll: biweekly fictional deposit series
    assert len(payload["payroll"]) == 1
    assert payload["payroll"][0]["cadence"] == "biweekly"
    assert payload["payroll"][0]["next_expected_date"] == "2026-09-25"
    # credit-card balances from the latest snapshot
    assert payload["credit_card_balances"]["cards"] == {"demo-card": 30.0}
    assert payload["credit_card_balances"]["total"] == 30.0
    # recurring detection (transfers excluded)
    rec = {r["merchant"]: r for r in payload["recurring"]}
    assert rec["demo payroll deposit"]["cadence"] == "biweekly"
    assert rec["demo payroll deposit"]["occurrences"] == 6
    assert rec["netflix"]["cadence"] == "monthly"
    assert rec["con edison"]["cadence"] == "monthly"
    assert payload["net_worth_history"] == [("2026-09-01", 70.0)]
    json.dumps(payload)  # must be JSON-serializable


def test_recurring():
    monthly = [Transaction(f"2026-0{m}-05", "Demo Sub", -9.99, "Entertainment/Streaming")
               for m in (7, 8, 9)]
    found = detect_recurring(monthly)
    assert len(found) == 1
    assert found[0]["merchant"] == "demo sub"
    assert found[0]["cadence"] == "monthly"
    assert found[0]["avg_amount"] == Decimal("9.99")
    assert found[0]["occurrences"] == 3
    # irregular gaps are ignored
    irregular = [
        Transaction("2026-07-01", "One Off Shop", -5.0, "Food/Coffee"),
        Transaction("2026-07-02", "One Off Shop", -5.0, "Food/Coffee"),
        Transaction("2026-09-20", "One Off Shop", -5.0, "Food/Coffee"),
    ]
    assert detect_recurring(irregular) == []
    # too few occurrences ignored
    assert detect_recurring(monthly[:2]) == []


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
        assert loaded[0].as_of == "2026-09-01" and loaded[0].net_worth == Decimal("70.0")


def test_default_limits():
    lims = default_limits()
    assert lims["Food/Groceries"] > 0 and lims["Housing/Rent"] > 0
    assert set(lims) <= set(all_paths())
    assert all(isinstance(v, Decimal) for v in lims.values())


def _write_csv(rows):
    import tempfile
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, newline="")
    f.write("date,description,amount,category,account\n")
    f.writelines(rows)
    f.close()
    return f.name


def test_importer_bank_amount_formats():
    path = _write_csv([
        '2026-09-01,Salary,"$2,520.00",Income/Salary,demo-bank\n',
        '2026-09-02,Refund,"(45.10)",Food/Groceries,demo-card\n',
        '2026-09-03,NaN Row,nan,Food/Coffee,demo-card\n',
        '2026-09-04,Inf Row,Infinity,Food/Coffee,demo-card\n',
    ])
    try:
        txns, errors = import_csv(path)
    finally:
        os.unlink(path)
    assert len(txns) == 2, (txns, errors)
    assert txns[0].amount == Decimal("2520.00")
    assert txns[1].amount == Decimal("-45.10")
    assert len(errors) == 2 and all("bad amount" in e for e in errors)


def test_importer_bom_and_case_insensitive_category():
    import tempfile
    f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False,
                                    newline="", encoding="utf-8-sig")
    f.write("date,description,amount,category,account\n")
    f.write("2026-09-01,Latte,-4.50,food/coffee,demo-card\n")
    f.close()
    try:
        txns, errors = import_csv(f.name)
    finally:
        os.unlink(f.name)
    assert errors == [], errors
    assert len(txns) == 1
    assert txns[0].date == "2026-09-01"  # BOM did not mangle the header
    assert txns[0].category == "Food/Coffee"


def test_snapshot_store_corrupt():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "snaps.json")
        with open(p, "w") as f:
            f.write("{not valid json!!!")
        assert load_snapshots(p) == []
        with open(p, "w") as f:
            f.write('{"wrong": "shape"}')
        assert load_snapshots(p) == []
        with open(p, "w") as f:
            f.write('[{"as_of": "2026-09-01", "assets": {"a": "bogus"}, "liabilities": {}}]')
        assert load_snapshots(p) == []


def test_snapshot_amounts_stored_exact():
    import tempfile
    snaps = [snapshot_net_worth("2026-09-01", {"a": 0.1, "b": 1999.99}, {"l": 33.33})]
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "snaps.json")
        save_snapshots(p, snaps)
        with open(p) as f:
            raw = json.load(f)
        assert all(isinstance(v, str) for v in raw[0]["assets"].values())
        loaded = load_snapshots(p)
        assert loaded[0].assets == {"a": Decimal("0.1"), "b": Decimal("1999.99")}
        assert loaded[0].liabilities == {"l": Decimal("33.33")}


def test_transfer_p2p_keywords():
    assert is_transfer("Zelle payment to Demo Dana")
    assert is_transfer("Venmo cashout")
    assert is_transfer("Cash App transfer")
    assert is_transfer("Wire transfer received")
    assert not is_transfer("Whole Foods Market")


def test_budget_unbudgeted_rollup():
    txns, _ = import_csv(CSV)
    planner = BudgetPlanner()
    planner.set_limits("2026-09", {"Food/Groceries": 400.0})
    planner.add_transactions(txns)
    report = planner.report("2026-09")
    assert "unbudgeted" in report
    assert report["unbudgeted"]["Housing/Rent"] == Decimal("1800.00")
    assert "Food/Groceries" not in report["unbudgeted"]


def test_set_limits_validates_paths():
    planner = BudgetPlanner()
    try:
        planner.set_limits("2026-09", {"Nope/Nope": 10})
    except ValueError:
        pass
    else:
        raise AssertionError("set_limits accepted an invalid category path")
    planner.set_limits("2026-09", {"Food/Coffee": 75})
    assert "Food/Coffee" in planner.limits["2026-09"]


def test_merge_allow_duplicates():
    a = Transaction("2026-09-01", "Demo Coffee", -4.5, "Food/Coffee", "demo-card")
    b = Transaction("2026-09-01", "Demo Coffee", -4.5, "Food/Coffee", "demo-card")
    merged, added = merge_transactions([], [a, b])
    assert added == 1 and len(merged) == 1  # genuine duplicate collapses by default
    merged, added = merge_transactions([], [a, b], allow_duplicates=True)
    assert added == 2 and len(merged) == 2


def test_classify_word_boundaries():
    assert classify("Different Store") == "Uncategorized/Uncategorized"
    assert classify("Rent - Demo Apartments") == "Housing/Rent"
    assert classify("Con Edison") == "Housing/Utilities"


def test_budget_excludes_transfers():
    # Regression: a credit-card payment must never inflate budget spend,
    # even when the planner is handed unsplit transactions.
    txns = [
        Transaction("2026-09-01", "Whole Foods", -100.0, "Food/Groceries", "demo-card"),
        Transaction("2026-09-16", "Demo Credit Card Payment", -1500.0,
                    "Uncategorized/Uncategorized", "demo-checking"),
    ]
    planner = BudgetPlanner()
    planner.set_limits("2026-09", {"Food/Groceries": 400.0})
    planner.add_transactions(txns)
    report = planner.report("2026-09")
    assert report["Food/Groceries"]["spent"] == Decimal("100.00")
    # the transfer is invisible: not in unbudgeted, not in any spend total
    assert "Uncategorized/Uncategorized" not in report["unbudgeted"]
    assert report["unbudgeted"] == {}


def test_payroll_detection():
    from money_tracker import detect_payroll, payroll_ytd
    txns, _ = import_csv(CSV)
    found = detect_payroll(txns)
    assert len(found) == 1
    p = found[0]
    assert p["merchant"] == "demo payroll deposit"
    assert p["cadence"] == "biweekly"
    assert p["occurrences"] == 6
    assert p["avg_amount"] == Decimal("4200.00")
    assert p["last_date"] == "2026-09-11"
    assert p["next_expected_date"] == "2026-09-25"
    # biweekly bills are subscriptions, not payroll
    bills = [Transaction(f"2026-0{m}-05", "Demo Sub", -9.99, "Entertainment/Streaming")
             for m in (7, 8, 9)]
    assert detect_payroll(bills) == []
    assert payroll_ytd(txns, "2026") == Decimal("25200.00")


def test_rent_report():
    txns, _ = import_csv(CSV)
    planner = BudgetPlanner()
    planner.set_limits("2026-09", {"Housing/Rent": 1800.0})
    planner.add_transactions(txns)
    rent = planner.rent_report("2026-09")
    assert rent["month"] == "2026-09"
    assert rent["paid"] == Decimal("1800.00")
    assert rent["limit"] == Decimal("1800.00")
    assert rent["remaining"] == Decimal("0")
    assert rent["payment_count"] == 1
    assert rent["payments"][0]["description"] == "Demo Landlord Rent"
    # a month with no rent payment reports zero, not an error
    empty = planner.rent_report("2026-08")
    assert empty["paid"] == Decimal("0") and empty["payment_count"] == 0


def test_credit_card_balances():
    from money_tracker import credit_card_balances
    s = snapshot_net_worth("2026-09-01",
                           {"demo-savings": 10500.00},
                           {"demo-credit-card": 1500.00,
                            "demo-student-loan": 9100.00})
    cards = credit_card_balances(s)
    assert cards["cards"] == {"demo-credit-card": Decimal("1500.00")}
    assert cards["total"] == Decimal("1500.00")
    assert "demo-student-loan" not in cards["cards"]


def test_transfer_ledger():
    from money_tracker import TransferLedger, build_ledger, is_p2p
    assert is_p2p("Zelle payment to Demo Dana")
    assert is_p2p("Venmo cashout")
    assert not is_p2p("Demo Credit Card Payment")
    assert not is_p2p("Whole Foods Market")

    txns = [
        Transaction("2026-09-01", "Zelle payment to Demo Dana", -40.0,
                    "Uncategorized/Uncategorized", "demo-checking"),
        Transaction("2026-09-02", "Venmo cashout", 200.0,
                    "Uncategorized/Uncategorized", "demo-checking"),
        Transaction("2026-09-03", "Whole Foods", -10.0, "Food/Groceries", "demo-card"),
    ]
    ledger = build_ledger(txns)
    assert len(ledger.entries()) == 2
    assert len(ledger.unreviewed()) == 2
    first_id = ledger.entries()[0]["id"]
    ledger.relabel(first_id, "Food/Dining Out")
    assert len(ledger.unreviewed()) == 1
    assert ledger.relabeled_spend() == {"Food/Dining Out": Decimal("40.00")}
    # unknown category paths raise instead of silently vanishing
    try:
        ledger.relabel(first_id, "Nope/Nope")
    except ValueError:
        pass
    else:
        raise AssertionError("ledger accepted an invalid category path")
    try:
        ledger.relabel(999, "Food/Coffee")
    except KeyError:
        pass
    else:
        raise AssertionError("ledger relabeled a missing entry id")


def test_merchant_location_items_import():
    txns, errors = import_csv(CSV)
    assert errors == [], errors
    whole_foods = next(t for t in txns if t.description == "Whole Foods Market")
    assert whole_foods.merchant == "Whole Foods Market"
    assert whole_foods.location == "New York, NY"
    assert whole_foods.items == ["Organic Milk", "Bananas", "Rotisserie Chicken"]
    netflix = next(t for t in txns
                   if t.description == "Netflix" and t.date == "2026-09-12")
    assert netflix.items == ["Premium Plan"]
    assert netflix.location == ""
    # fields default empty when columns are absent (backward compatible)
    t = Transaction("2026-09-01", "X", -1.0, "Food/Coffee")
    assert t.merchant == "" and t.location == "" and t.items == []


if __name__ == "__main__":
    test_taxonomy()
    test_importer()
    test_date_validation()
    test_importer_rejects_bad_dates_and_amounts()
    test_net_worth()
    test_budget()
    test_dashboard()
    test_recurring()
    test_transfers()
    test_merge()
    test_snapshot_store()
    test_default_limits()
    test_importer_bank_amount_formats()
    test_importer_bom_and_case_insensitive_category()
    test_snapshot_store_corrupt()
    test_snapshot_amounts_stored_exact()
    test_transfer_p2p_keywords()
    test_budget_unbudgeted_rollup()
    test_set_limits_validates_paths()
    test_merge_allow_duplicates()
    test_classify_word_boundaries()
    test_budget_excludes_transfers()
    test_payroll_detection()
    test_rent_report()
    test_credit_card_balances()
    test_transfer_ledger()
    test_merchant_location_items_import()
    print("all tests passed")
