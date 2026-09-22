"""Local data-source selection for money_tracker (T-OP-5).

Chooses which ReadOnlyAdapter feeds the dashboard: the bundled sample
data (default) or an explicitly configured live-local adapter. Real data
is only ever loaded from a LOCAL, gitignored config file on the user's
own machine; secrets live in environment variables ONLY.

Config file: ~/.commons-money-tracker/config.json
              (override with the MONEY_TRACKER_CONFIG env var)
Supported keys (non-secret settings only):
    {"data_source": "sample" | "plaid" | "coinbase",
     "plaid_env": "sandbox" | "development" | "production"}

If the file is absent, the source is "sample". If the file contains a
key that looks like a secret (token, secret, password, api key), loading
REFUSES — secrets must be env vars, never config values. This file, like
everything else in the repo, must never contain real balances or creds.
"""

from __future__ import annotations

import json
import os

from money_tracker.adapters import (
    AdapterError,
    CoinbaseAdapter,
    PlaidAdapter,
    ReadOnlyAdapter,
    SampleDataAdapter,
)

CONFIG_ENV_VAR = "MONEY_TRACKER_CONFIG"
DEFAULT_CONFIG_PATH = os.path.join(
    os.path.expanduser("~"), ".commons-money-tracker", "config.json")

SOURCES = {
    "sample": SampleDataAdapter,
    "plaid": PlaidAdapter,
    "coinbase": CoinbaseAdapter,
}

# Any config key containing one of these is treated as a secret and refused.
_SECRET_MARKERS = ("secret", "token", "password", "passwd", "api_key", "apikey",
                   "private_key", "client_secret")


def config_path() -> str:
    """Where the local config lives (outside the repo)."""
    return os.environ.get(CONFIG_ENV_VAR) or DEFAULT_CONFIG_PATH


def load_local_config(path: str = None) -> dict:
    """Load the local config file. Returns {} when absent.

    Refuses to load when a key looks like a secret — those belong in env
    vars only. Raises AdapterError on unreadable/invalid JSON so a broken
    config fails loudly instead of silently falling back to sample data.
    """
    path = path or config_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            config = json.load(f)
    except (OSError, ValueError) as e:
        raise AdapterError(f"cannot read local config at {path}: {e}")
    if not isinstance(config, dict):
        raise AdapterError(f"local config at {path} must be a JSON object")
    for key in config:
        lowered = str(key).lower()
        if any(marker in lowered for marker in _SECRET_MARKERS):
            raise AdapterError(
                f"refusing to load local config: key {key!r} looks like a "
                "secret — put secrets in environment variables only, never "
                "in the config file."
            )
    return config


def get_adapter(source: str = None, config: dict = None) -> ReadOnlyAdapter:
    """Build the adapter for `source` (default: config's data_source,
    default "sample"). Raises AdapterError on unknown sources and
    AdapterNotConfiguredError when a live adapter lacks credentials."""
    if source is None:
        source = (config or load_local_config()).get("data_source", "sample")
    source = str(source).lower()
    cls = SOURCES.get(source)
    if cls is None:
        raise AdapterError(
            f"unknown data source {source!r}; expected one of {sorted(SOURCES)}"
        )
    if cls is PlaidAdapter and config and config.get("plaid_env"):
        return cls(plaid_env=config["plaid_env"])
    return cls()
