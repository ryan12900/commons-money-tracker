"""M10 (T-OP-5) adapter tests — run with `make check`.

Covers the ReadOnlyAdapter interface, the sample-data adapter, the Plaid
and Coinbase reference adapters (against fixture clients — no network, no
credentials), lazy credential loading, the local-config loader's secret
refusal, the dashboard data-source switch, and the .gitignore coverage.

Sample/fixture data only. No real balances, credentials, or account data.
"""

import json
import os
import subprocess
import sys
import tempfile
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from money_tracker import (
    AdapterError,
    AdapterNotConfiguredError,
    Balance,
    CoinbaseAdapter,
    Holding,
    PlaidAdapter,
    ReadOnlyAdapter,
    SampleDataAdapter,
    Transaction,
    build_dashboard,
    get_adapter,
    load_local_config,
)

HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(HERE)

# Live-adapter env vars — scrubbed for the credential tests.
_LIVE_VARS = ("PLAID_CLIENT_ID", "PLAID_SECRET", "PLAID_ACCESS_TOKEN",
              "PLAID_ENV", "COINBASE_API_KEY", "COINBASE_API_SECRET")


def _scrubbed_env():
    env = dict(os.environ)
    for var in _LIVE_VARS + ("MONEY_TRACKER_CONFIG",):
        env.pop(var, None)
    return env


class _EnvGuard:
    """Temporarily replace os.environ with the given mapping."""

    def __init__(self, mapping):
        self.mapping = mapping
        self.saved = dict(os.environ)

    def __enter__(self):
        os.environ.clear()
        os.environ.update(self.mapping)

    def __exit__(self, *exc):
        os.environ.clear()
        os.environ.update(self.saved)


# ---------------------------------------------------------------------------
# Fixture clients (no network)
# ---------------------------------------------------------------------------

class FakePlaidClient:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def post(self, path, payload):
        self.calls.append((path, payload))
        return self.routes[path]


PLAID_FIXTURES = {
    "/accounts/balance/get": {"accounts": [
        {"name": "Plaid Checking", "official_name": "Plaid Gold Checking",
         "type": "depository", "subtype": "checking",
         "balances": {"current": 1234.56}},
        {"name": "Plaid Credit Card", "type": "credit",
         "subtype": "credit card", "balances": {"current": 210.75}},
        {"name": "No balance yet", "type": "depository",
         "subtype": "savings", "balances": {}},
    ]},
    "/transactions/sync": {"added": [
        {"date": "2026-09-05", "name": "Demo Coffee", "amount": 4.50,
         "merchant_name": "Demo Coffee",
         "personal_finance_category": {"detailed": "FOOD_AND_DRINK_COFFEE"}},
        {"date": "2026-09-06", "name": "Demo Payroll", "amount": -4200.00,
         "personal_finance_category": {"detailed": "INCOME_WAGES"}},
        {"date": "2026-09-07", "name": "Mystery charge", "amount": 12.00,
         "personal_finance_category": {"detailed": "SOME_NEW_CODE"}},
    ], "has_more": False, "next_cursor": "cursor-1"},
    "/investments/holdings/get": {
        "holdings": [{"security_id": "s1", "quantity": 10,
                      "institution_value": 2500.00}],
        "securities": [{"security_id": "s1", "ticker_symbol": "AAPL",
                        "name": "Apple Inc."}],
    },
}


class FakeCoinbaseClient:
    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def get(self, path):
        self.calls.append(path)
        return self.routes[path]


COINBASE_FIXTURES = {
    "/accounts": {"accounts": [
        {"available_balance": {"value": "0.5", "currency": "BTC"}},
        {"available_balance": {"value": "0", "currency": "ETH"}},  # skipped
        {"available_balance": {"value": "1200.00", "currency": "USD"}},
    ]},
    "/orders/historical/fills": {"fills": [
        {"trade_time": "2026-09-05T14:00:00Z", "product_id": "BTC-USD",
         "side": "BUY", "size": "0.1", "price": "60000"},
        {"trade_time": "2026-09-06T14:00:00Z", "product_id": "ETH-USD",
         "side": "SELL", "size": "2", "price": "3000"},
    ]},
}


def _plaid(env=None):
    return PlaidAdapter(client=FakePlaidClient(PLAID_FIXTURES), env=env or {})


def _coinbase(env=None):
    return CoinbaseAdapter(client=FakeCoinbaseClient(COINBASE_FIXTURES), env=env or {})


# ---------------------------------------------------------------------------
# Interface + read-only-by-design
# ---------------------------------------------------------------------------

def test_interface_conformance():
    for adapter in (SampleDataAdapter(), _plaid(), _coinbase()):
        assert isinstance(adapter, ReadOnlyAdapter)
        assert isinstance(adapter.name, str) and adapter.name
        assert adapter.source_id in ("sample", "plaid", "coinbase")
        assert isinstance(adapter.get_balances(), list)
        assert isinstance(adapter.get_holdings(), list)
        assert isinstance(adapter.get_transactions(), list)
        # read-only by design: no write/transfer/payment/trade surface exists
        for verb in ("transfer", "send", "withdraw", "pay", "trade",
                     "write", "post_transaction", "create_order"):
            assert not hasattr(adapter, verb), f"{adapter.source_id} has {verb}"


def test_value_objects_coerce_decimal():
    b = Balance(label="x", amount=10.5)
    assert isinstance(b.amount, Decimal)
    h = Holding(symbol="BTC", name="Bitcoin", quantity="0.5", value=30000)
    assert isinstance(h.quantity, Decimal) and isinstance(h.value, Decimal)


# ---------------------------------------------------------------------------
# Sample adapter (default)
# ---------------------------------------------------------------------------

def test_sample_adapter():
    a = SampleDataAdapter()
    txns = a.get_transactions()
    assert len(txns) == 24, f"expected 24 sample rows, got {len(txns)}"
    assert all(isinstance(t, Transaction) and isinstance(t.amount, Decimal)
               for t in txns)
    balances = a.get_balances()
    by_label = {b.label: b for b in balances}
    assert by_label["demo-savings"].kind == "asset"
    assert by_label["demo-credit-card"].kind == "liability"
    assert by_label["demo-brokerage"].amount == Decimal("47000")
    assert a.get_holdings() == []
    snap = a.as_snapshot("2026-09-01")
    assert snap.net_worth == Decimal("46900"), snap.net_worth


def test_sample_adapter_date_filter():
    a = SampleDataAdapter()
    sept = a.get_transactions(start_date="2026-09-01", end_date="2026-09-30")
    assert sept and all(t.date.startswith("2026-09") for t in sept)
    assert len(sept) < len(a.get_transactions())


# ---------------------------------------------------------------------------
# Credential handling: lazy, never at import, never echoed
# ---------------------------------------------------------------------------

def test_import_reads_no_env():
    """Importing the modules with a scrubbed env must succeed and the
    sample path must work — nothing is read at import time."""
    code = (
        "import sys; sys.path.insert(0, %r);"
        "import money_tracker.adapters, money_tracker.data_source;"
        "a = money_tracker.adapters.SampleDataAdapter();"
        "assert len(a.get_transactions()) == 24;"
        "assert money_tracker.data_source.load_local_config('/nonexistent') == {};"
        "print('ok')" % REPO_ROOT
    )
    proc = subprocess.run([sys.executable, "-c", code], env=_scrubbed_env(),
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "ok"


def test_plaid_missing_credentials():
    with _EnvGuard(_scrubbed_env()):
        try:
            PlaidAdapter()
        except AdapterNotConfiguredError as e:
            msg = str(e)
        else:
            raise AssertionError("expected AdapterNotConfiguredError")
    for var in ("PLAID_CLIENT_ID", "PLAID_SECRET", "PLAID_ACCESS_TOKEN"):
        assert var in msg, f"{var} not named in: {msg}"


def test_plaid_partial_credentials_still_refuses():
    with _EnvGuard({**_scrubbed_env(), "PLAID_CLIENT_ID": "id-only"}):
        try:
            PlaidAdapter()
        except AdapterNotConfiguredError as e:
            msg = str(e)
        else:
            raise AssertionError("expected AdapterNotConfiguredError")
    assert "id-only" not in msg  # values are never echoed
    assert "PLAID_SECRET" in msg and "PLAID_ACCESS_TOKEN" in msg


def test_plaid_unknown_env_rejected():
    env = {**_scrubbed_env(), "PLAID_CLIENT_ID": "x", "PLAID_SECRET": "y",
           "PLAID_ACCESS_TOKEN": "z", "PLAID_ENV": "narnia"}
    try:
        PlaidAdapter(env=env)
    except AdapterError as e:
        assert "narnia" in str(e)
    else:
        raise AssertionError("expected AdapterError for bad PLAID_ENV")


def test_coinbase_missing_credentials():
    with _EnvGuard(_scrubbed_env()):
        try:
            CoinbaseAdapter()
        except AdapterNotConfiguredError as e:
            msg = str(e)
        else:
            raise AssertionError("expected AdapterNotConfiguredError")
    assert "COINBASE_API_KEY" in msg and "COINBASE_API_SECRET" in msg


# ---------------------------------------------------------------------------
# Mapping: fixtures -> shared model
# ---------------------------------------------------------------------------

def test_plaid_mapping():
    a = _plaid()
    balances = {b.label: b for b in a.get_balances()}
    assert balances["Plaid Gold Checking"].kind == "asset"
    assert balances["Plaid Gold Checking"].amount == Decimal("1234.56")
    assert balances["Plaid Credit Card"].kind == "liability"
    assert balances["Plaid Credit Card"].amount == Decimal("210.75")
    assert "No balance yet" not in balances  # accounts w/o balance skipped

    txns = {t.description: t for t in a.get_transactions()}
    coffee = txns["Demo Coffee"]
    assert coffee.amount == Decimal("-4.50")  # Plaid +outflow -> negative
    assert coffee.category == "Food/Coffee"
    assert coffee.merchant == "Demo Coffee"
    assert coffee.source == "plaid"
    payroll = txns["Demo Payroll"]
    assert payroll.amount == Decimal("4200.00")  # Plaid -inflow -> positive
    assert payroll.category == "Income/Salary"
    mystery = txns["Mystery charge"]
    assert mystery.category == "Uncategorized/Uncategorized"  # never guessed

    holdings = a.get_holdings()
    assert len(holdings) == 1
    assert holdings[0].symbol == "AAPL"
    assert holdings[0].quantity == Decimal("10")
    assert holdings[0].value == Decimal("2500.00")

    snap = a.as_snapshot("2026-09-22")
    assert snap.net_worth == Decimal("1234.56") - Decimal("210.75")


def test_plaid_transaction_date_filter():
    a = _plaid()
    one = a.get_transactions(start_date="2026-09-06", end_date="2026-09-06")
    assert [t.description for t in one] == ["Demo Payroll"]


def test_coinbase_mapping():
    a = _coinbase()
    balances = {b.label: b for b in a.get_balances()}
    assert set(balances) == {"Coinbase BTC", "Coinbase USD"}  # zero ETH skipped
    assert balances["Coinbase BTC"].amount == Decimal("0.5")
    assert balances["Coinbase BTC"].account_type == "crypto"
    assert all(b.kind == "asset" for b in balances.values())

    holdings = {h.symbol: h for h in a.get_holdings()}
    assert holdings["BTC"].quantity == Decimal("0.5")

    txns = a.get_transactions()
    by_desc = {t.description: t for t in txns}
    buy = by_desc["BTC-USD BUY fill"]
    assert buy.amount == Decimal("-6000.00")  # BUY = money out
    assert buy.category == "Finance/Investments"
    sell = by_desc["ETH-USD SELL fill"]
    assert sell.amount == Decimal("6000.00")  # SELL = money in
    assert all(t.source == "coinbase" for t in txns)


# ---------------------------------------------------------------------------
# data_source: config + factory
# ---------------------------------------------------------------------------

def test_get_adapter_defaults_to_sample():
    with _EnvGuard({**_scrubbed_env(), "MONEY_TRACKER_CONFIG": "/nonexistent.json"}):
        adapter = get_adapter()
    assert isinstance(adapter, SampleDataAdapter)
    assert adapter.source_id == "sample"


def test_get_adapter_unknown_source():
    try:
        get_adapter("schwab")
    except AdapterError as e:
        assert "schwab" in str(e)
    else:
        raise AssertionError("expected AdapterError")


def test_get_adapter_live_from_config():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = os.path.join(tmp, "config.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"data_source": "plaid", "plaid_env": "sandbox"}, f)
        env = {**_scrubbed_env(), "MONEY_TRACKER_CONFIG": cfg,
               "PLAID_CLIENT_ID": "x", "PLAID_SECRET": "y",
               "PLAID_ACCESS_TOKEN": "z"}
        with _EnvGuard(env):
            assert load_local_config()["data_source"] == "plaid"
            adapter = get_adapter()
        assert isinstance(adapter, PlaidAdapter)


def test_config_refuses_secrets():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = os.path.join(tmp, "config.json")
        with open(cfg, "w", encoding="utf-8") as f:
            json.dump({"data_source": "sample", "plaid_secret": "shh"}, f)
        try:
            load_local_config(cfg)
        except AdapterError as e:
            assert "secret" in str(e).lower()
        else:
            raise AssertionError("expected AdapterError for secret-like key")


def test_config_invalid_json_fails_loudly():
    with tempfile.TemporaryDirectory() as tmp:
        cfg = os.path.join(tmp, "config.json")
        with open(cfg, "w", encoding="utf-8") as f:
            f.write("{not json")
        try:
            load_local_config(cfg)
        except AdapterError:
            pass
        else:
            raise AssertionError("expected AdapterError for invalid JSON")


# ---------------------------------------------------------------------------
# Dashboard data-source switch
# ---------------------------------------------------------------------------

def test_dashboard_data_source_switch():
    a = SampleDataAdapter()
    txns = a.get_transactions()
    snap = a.as_snapshot("2026-09-01")
    default = build_dashboard(txns, [snap], {})
    assert default["data_source"] == "sample"
    live = build_dashboard(txns, [snap], {}, data_source="coinbase")
    assert live["data_source"] == "coinbase"
    assert json.dumps(live)  # still JSON-serializable


def test_gitignore_covers_local_config():
    with open(os.path.join(REPO_ROOT, ".gitignore"), encoding="utf-8") as f:
        content = f.read()
    for pattern in ("local_config.json", ".commons-money-tracker/", "*-live.json"):
        assert pattern in content, f"{pattern} missing from .gitignore"


TESTS = [
    test_interface_conformance,
    test_value_objects_coerce_decimal,
    test_sample_adapter,
    test_sample_adapter_date_filter,
    test_import_reads_no_env,
    test_plaid_missing_credentials,
    test_plaid_partial_credentials_still_refuses,
    test_plaid_unknown_env_rejected,
    test_coinbase_missing_credentials,
    test_plaid_mapping,
    test_plaid_transaction_date_filter,
    test_coinbase_mapping,
    test_get_adapter_defaults_to_sample,
    test_get_adapter_unknown_source,
    test_get_adapter_live_from_config,
    test_config_refuses_secrets,
    test_config_invalid_json_fails_loudly,
    test_dashboard_data_source_switch,
    test_gitignore_covers_local_config,
]


if __name__ == "__main__":
    for test in TESTS:
        test()
        print(f"ok - {test.__name__}")
    print("all adapter tests passed")
