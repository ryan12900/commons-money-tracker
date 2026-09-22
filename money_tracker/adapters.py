"""M10 — Real-account adapters (reference implementations, local-only).

Optional, read-only connectors that pull balances, holdings, and
transactions from a person's own accounts into the repo's shared data
model (Transaction / NetWorthSnapshot). Sample data stays the default:
every read-only path in this repo runs with zero credentials, and the
live adapters are only constructed when explicitly requested.

Read-only by design: the adapter interface exposes no write, transfer,
payment, or trade methods at all, so an adapter can never move money —
there is simply no method to call.

Credential rules (non-negotiable):
- Secrets live in environment variables ONLY, read lazily when a live
  adapter is instantiated — never at import time, never in a config
  file, never in the repo, and never echoed into errors or logs.
- Real balances/holdings/transactions are never committed to this repo,
  never written to sample_data/, and never posted to the Commons sheet.
- These are reference implementations using the providers' public REST
  endpoints via the standard library (no third-party SDK needed).
  Production use should prefer the official SDKs and token vaults.

Env vars (read only inside the live adapter constructors):
    Plaid:    PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ACCESS_TOKEN,
              PLAID_ENV (default "sandbox"; set "production" for real data)
    Coinbase: COINBASE_API_KEY, COINBASE_API_SECRET
              (Coinbase Advanced Trade legacy API key, HMAC-signed)

Sample/demo data only in the repo. Never commit real balances, accounts,
holdings, spending, credentials, or anything that identifies a real person.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
import time
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal

from money_tracker.models import Transaction, NetWorthSnapshot
from money_tracker.transfers import map_provider_category

# Repo root: adapters.py lives in <root>/money_tracker/adapters.py, so the
# sample data sits next to it. Used only by SampleDataAdapter.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class AdapterError(Exception):
    """Base error for adapter failures."""


class AdapterNotConfiguredError(AdapterError):
    """Raised when a live adapter is requested without credentials.

    The message names the MISSING variable names only — never values —
    so it is safe to print, log, or paste into the Commons sheet.
    """


# ---------------------------------------------------------------------------
# Shared value objects
# ---------------------------------------------------------------------------

@dataclass
class Balance:
    """One account balance. Label only — never account numbers."""
    label: str            # free text, e.g. "Plaid Checking"
    amount: Decimal       # always positive; `kind` says which side
    kind: str = "asset"   # "asset" | "liability"
    account_type: str = ""  # e.g. "checking", "brokerage", "crypto"

    def __post_init__(self):
        if not isinstance(self.amount, Decimal):
            self.amount = Decimal(str(self.amount))


@dataclass
class Holding:
    """One investment/crypto position."""
    symbol: str           # ticker or currency code, e.g. "AAPL", "BTC"
    name: str             # human name, e.g. "Apple Inc."
    quantity: Decimal
    value: Decimal        # market value in the account's currency
    account: str = ""     # label only

    def __post_init__(self):
        for f in ("quantity", "value"):
            v = getattr(self, f)
            if not isinstance(v, Decimal):
                setattr(self, f, Decimal(str(v)))


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------

class ReadOnlyAdapter(ABC):
    """Read-only source of balances, holdings, and transactions.

    Implementations must be side-effect free: no writes, transfers,
    payments, trades, or credential persistence. `source_id` is a stable
    machine key ("sample", "plaid", "coinbase"); `name` is human-facing.
    """

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def source_id(self) -> str: ...

    @abstractmethod
    def get_balances(self) -> list:
        """[Balance] — one per account. Label only, never account numbers."""

    @abstractmethod
    def get_holdings(self) -> list:
        """[Holding] — investment/crypto positions. [] when not supported."""

    @abstractmethod
    def get_transactions(self, start_date: str = None, end_date: str = None) -> list:
        """[Transaction] in the shared model. Dates are YYYY-MM-DD; the
        range filters inclusively. [] when the source has nothing new."""

    def as_snapshot(self, as_of: str) -> NetWorthSnapshot:
        """Build a NetWorthSnapshot from current balances.

        Holdings are intentionally excluded: a brokerage's balance already
        covers its holdings' value, and double-counting them would inflate
        net worth. Holdings remain available via get_holdings() as a
        drill-down.
        """
        assets, liabilities = {}, {}
        for b in self.get_balances():
            (assets if b.kind == "asset" else liabilities)[b.label] = b.amount
        return NetWorthSnapshot(as_of=as_of, assets=assets, liabilities=liabilities)


# ---------------------------------------------------------------------------
# Sample-data adapter (the default)
# ---------------------------------------------------------------------------

class SampleDataAdapter(ReadOnlyAdapter):
    """Adapter over the repo's bundled sample data.

    This is what `make check`, `make demo`, and the dashboard use unless
    a live source is explicitly configured. No credentials, no network.
    """

    @property
    def name(self) -> str:
        return "Sample data"

    @property
    def source_id(self) -> str:
        return "sample"

    def _sample_pkg(self):
        """Import sample_data lazily so the package import stays light."""
        if REPO_ROOT not in sys.path:
            sys.path.insert(0, REPO_ROOT)
        from sample_data import demo_snapshots  # noqa: PLC0415
        from money_tracker import importer  # noqa: PLC0415
        return demo_snapshots, importer

    def get_balances(self) -> list:
        demo_snapshots, _ = self._sample_pkg()
        latest = max(demo_snapshots.SNAPSHOTS, key=lambda s: s["as_of"])
        balances = [
            Balance(label=k, amount=v, kind="asset", account_type="sample")
            for k, v in latest["assets"].items()
        ] + [
            Balance(label=k, amount=v, kind="liability", account_type="sample")
            for k, v in latest["liabilities"].items()
        ]
        return balances

    def get_holdings(self) -> list:
        return []  # sample data has no per-security positions

    def get_transactions(self, start_date: str = None, end_date: str = None) -> list:
        _, importer = self._sample_pkg()
        csv_path = os.path.join(REPO_ROOT, "sample_data", "demo_transactions.csv")
        transactions, _errors = importer.import_csv(csv_path)
        return [
            t for t in transactions
            if (start_date is None or t.date >= start_date)
            and (end_date is None or t.date <= end_date)
        ]


# ---------------------------------------------------------------------------
# Minimal stdlib HTTP helpers (kept private to this module)
# ---------------------------------------------------------------------------

def _post_json(url: str, payload: dict, headers: dict = None, timeout: int = 30) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=body,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str, headers: dict = None, timeout: int = 30) -> dict:
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------------------
# Plaid (bank/brokerage) — reference adapter
# ---------------------------------------------------------------------------

_PLAID_HOSTS = {
    "sandbox": "https://sandbox.plaid.com",
    "development": "https://development.plaid.com",
    "production": "https://production.plaid.com",
}

# Plaid personal_finance_category.detailed -> taxonomy path, via
# transfers.map_provider_category. Unknown codes resolve to
# Uncategorized/Uncategorized — never guessed (see map_provider_category).
_PLAID_CATEGORY_MAP = {
    "FOOD_AND_DRINK_COFFEE": ("Food/Coffee", False),
    "FOOD_AND_DRINK_GROCERIES": ("Food/Groceries", False),
    "FOOD_AND_DRINK_RESTAURANTS": ("Food/Dining Out", False),
    "HOUSING_RENT": ("Housing/Rent", False),
    "HOUSING_UTILITIES": ("Housing/Utilities", False),
    "TRANSPORTATION_PUBLIC_TRANSIT": ("Transport/Transit", False),
    "TRANSPORTATION_RIDE_SHARE": ("Transport/Rideshare", False),
    "INCOME_WAGES": ("Income/Salary", False),
    "TRANSFER_IN_ACCOUNT_TRANSFER": ("Uncategorized/Uncategorized", True),
    "TRANSFER_OUT_ACCOUNT_TRANSFER": ("Uncategorized/Uncategorized", True),
}


def _plaid_env(name: str, env: dict = None) -> str:
    """Read one Plaid credential. `env` is an injectable mapping so tests
    can supply fixtures without touching the real environment."""
    source = env if env is not None else os.environ
    return (source.get(name) or "").strip()


class PlaidAdapter(ReadOnlyAdapter):
    """Reference Plaid adapter (bank/brokerage), read-only endpoints only.

    Uses /accounts/balance/get, /transactions/sync, and
    /investments/holdings/get. Pass `client` (an object with a
    `.post(path, payload) -> dict` method) to inject fixtures in tests —
    an injected client skips credential validation entirely. Otherwise a
    stdlib HTTP client is built from env vars.

    Env: PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ACCESS_TOKEN,
         PLAID_ENV (default "sandbox").
    """

    def __init__(self, client=None, env: dict = None,
                 client_id: str = None, secret: str = None,
                 access_token: str = None, plaid_env: str = None):
        # Credentials are resolved here — lazily, at instantiation — and
        # never stored anywhere but this instance. Importing this module
        # reads nothing from the environment.
        self._client_id = client_id or _plaid_env("PLAID_CLIENT_ID", env)
        self._secret = secret or _plaid_env("PLAID_SECRET", env)
        self._access_token = access_token or _plaid_env("PLAID_ACCESS_TOKEN", env)
        self._env_name = (plaid_env or _plaid_env("PLAID_ENV", env) or "sandbox").lower()
        if client is None:
            missing = [
                var for var, val in (
                    ("PLAID_CLIENT_ID", self._client_id),
                    ("PLAID_SECRET", self._secret),
                    ("PLAID_ACCESS_TOKEN", self._access_token),
                ) if not val
            ]
            if missing:
                raise AdapterNotConfiguredError(
                    "Plaid adapter needs credentials in the environment: "
                    + ", ".join(missing)
                    + ". See money_tracker/adapters.py for the full list."
                )
        if self._env_name not in _PLAID_HOSTS:
            raise AdapterError(
                f"Unknown PLAID_ENV {self._env_name!r}; "
                f"expected one of {sorted(_PLAID_HOSTS)}."
            )
        self._client = client or _PlaidHttpClient(
            _PLAID_HOSTS[self._env_name],
            self._client_id, self._secret, self._access_token,
        )

    @property
    def name(self) -> str:
        return "Plaid (bank/brokerage)"

    @property
    def source_id(self) -> str:
        return "plaid"

    def _post(self, path: str, payload: dict) -> dict:
        return self._client.post(path, payload)

    def get_balances(self) -> list:
        data = self._post("/accounts/balance/get", {})
        balances = []
        for acct in data.get("accounts", []):
            avail = (acct.get("balances") or {})
            amount = avail.get("current")
            if amount is None:
                continue
            label = (acct.get("official_name") or acct.get("name") or "Plaid account").strip()
            a_type = (acct.get("type") or "").lower()
            kind = "liability" if a_type in ("credit", "loan") else "asset"
            balances.append(Balance(
                label=label, amount=amount, kind=kind,
                account_type=(acct.get("subtype") or a_type or "plaid"),
            ))
        return balances

    def get_transactions(self, start_date: str = None, end_date: str = None) -> list:
        # /transactions/sync is cursor-based; walk until !has_more.
        added, cursor, has_more = [], "", True
        while has_more:
            data = self._post("/transactions/sync", {"cursor": cursor} if cursor else {})
            added.extend(data.get("added", []))
            cursor = data.get("next_cursor", "")
            has_more = bool(data.get("has_more"))
        transactions = []
        for raw in added:
            date = raw.get("authorized_date") or raw.get("date") or ""
            if not date:
                continue
            if start_date and date < start_date:
                continue
            if end_date and date > end_date:
                continue
            # Plaid sign convention: positive amount = money OUT.
            amount = -(Decimal(str(raw.get("amount") or 0)))
            pfc = (raw.get("personal_finance_category") or {})
            code = (pfc.get("detailed") or "").upper()
            category, _is_transfer = map_provider_category(code, _PLAID_CATEGORY_MAP)
            transactions.append(Transaction(
                date=date,
                description=(raw.get("name") or "Plaid transaction").strip(),
                amount=amount,
                category=category,
                account="plaid",
                source="plaid",
                merchant=(raw.get("merchant_name") or ""),
            ))
        return transactions

    def get_holdings(self) -> list:
        data = self._post("/investments/holdings/get", {})
        securities = {
            s.get("security_id"): s
            for s in data.get("securities", [])
        }
        holdings = []
        for h in data.get("holdings", []):
            sec = securities.get(h.get("security_id")) or {}
            value = h.get("institution_value")
            holdings.append(Holding(
                symbol=(sec.get("ticker_symbol") or sec.get("name") or "?").strip(),
                name=(sec.get("name") or "").strip(),
                quantity=h.get("quantity") or 0,
                value=value if value is not None else 0,
            ))
        return holdings


class _PlaidHttpClient:
    """Stdlib HTTP client for Plaid's read-only endpoints."""

    def __init__(self, host: str, client_id: str, secret: str, access_token: str):
        self._host = host
        self._auth = {
            "client_id": client_id,
            "secret": secret,
            "access_token": access_token,
        }

    def post(self, path: str, payload: dict) -> dict:
        return _post_json(self._host + path, {**self._auth, **payload})


# ---------------------------------------------------------------------------
# Coinbase (crypto) — reference adapter
# ---------------------------------------------------------------------------

_COINBASE_BASE = "https://api.coinbase.com/api/v3/brokerage"


class CoinbaseAdapter(ReadOnlyAdapter):
    """Reference Coinbase adapter (Advanced Trade, HMAC-signed), read-only.

    Reads /accounts (balances) and /orders/historical/fills (trade fills
    as transactions — crypto activity in this API is fills and transfers).
    Pass `client` (an object with `.get(path) -> dict`) for test fixtures —
    an injected client skips credential validation entirely. Otherwise a
    stdlib HTTP client is built from env vars.

    Env: COINBASE_API_KEY, COINBASE_API_SECRET (Advanced Trade legacy key).
    """

    def __init__(self, client=None, env: dict = None,
                 api_key: str = None, api_secret: str = None):
        self._api_key = api_key or _plaid_env("COINBASE_API_KEY", env)
        self._api_secret = api_secret or _plaid_env("COINBASE_API_SECRET", env)
        if client is None:
            missing = [
                var for var, val in (
                    ("COINBASE_API_KEY", self._api_key),
                    ("COINBASE_API_SECRET", self._api_secret),
                ) if not val
            ]
            if missing:
                raise AdapterNotConfiguredError(
                    "Coinbase adapter needs credentials in the environment: "
                    + ", ".join(missing)
                    + ". See money_tracker/adapters.py for the full list."
                )
        self._client = client or _CoinbaseHttpClient(self._api_key, self._api_secret)

    @property
    def name(self) -> str:
        return "Coinbase (crypto)"

    @property
    def source_id(self) -> str:
        return "coinbase"

    def get_balances(self) -> list:
        data = self._client.get("/accounts")
        balances = []
        for acct in data.get("accounts", []):
            avail = (acct.get("available_balance") or {})
            amount = Decimal(str(avail.get("value") or 0))
            if amount <= 0:
                continue
            currency = (avail.get("currency") or "").upper()
            balances.append(Balance(
                label=f"Coinbase {currency or 'crypto'}",
                amount=amount, kind="asset", account_type="crypto",
            ))
        return balances

    def get_holdings(self) -> list:
        return [
            Holding(
                symbol=b.label.replace("Coinbase ", ""),
                name=b.label,
                quantity=b.amount,
                value=b.amount,  # native units; fiat valuation is out of scope
                account=b.label,
            )
            for b in self.get_balances()
        ]

    def get_transactions(self, start_date: str = None, end_date: str = None) -> list:
        data = self._client.get("/orders/historical/fills")
        transactions = []
        for fill in data.get("fills", []):
            trade_time = fill.get("trade_time") or ""
            date = trade_time[:10]
            if not date:
                continue
            if start_date and date < start_date:
                continue
            if end_date and date > end_date:
                continue
            side = (fill.get("side") or "").upper()
            size = Decimal(str(fill.get("size") or 0))
            price = Decimal(str(fill.get("price") or 0))
            amount = size * price
            # BUY spends quote currency (money out), SELL receives it.
            if side == "BUY":
                amount = -amount
            transactions.append(Transaction(
                date=date,
                description=f"{fill.get('product_id', '')} {side} fill".strip(),
                amount=amount,
                category="Finance/Investments",
                account="coinbase",
                source="coinbase",
            ))
        return transactions


class _CoinbaseHttpClient:
    """Stdlib HMAC-signed client for Coinbase Advanced Trade (read-only)."""

    def __init__(self, api_key: str, api_secret: str):
        self._api_key = api_key
        self._api_secret = api_secret

    def _headers(self, method: str, path: str, body: str = "") -> dict:
        timestamp = str(int(time.time()))
        message = timestamp + method + path + body
        signature = hmac.new(
            self._api_secret.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return {
            "CB-ACCESS-KEY": self._api_key,
            "CB-ACCESS-SIGN": signature,
            "CB-ACCESS-TIMESTAMP": timestamp,
            "Content-Type": "application/json",
        }

    def get(self, path: str) -> dict:
        url = _COINBASE_BASE + path
        req = urllib.request.Request(
            url, headers=self._headers("GET", "/api/v3/brokerage" + path), method="GET")
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
