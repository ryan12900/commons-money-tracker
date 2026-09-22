"""Commons Money Tracker — shared finance core (sample data only)."""

from money_tracker.models import Transaction, NetWorthSnapshot
from money_tracker.taxonomy import CATEGORIES, all_paths, classify
from money_tracker.transfers import (
    TRANSFER_KEYWORDS,
    P2P_KEYWORDS,
    is_transfer,
    is_p2p,
    map_provider_category,
    split_transfers,
    TransferLedger,
    build_ledger,
)
from money_tracker.importer import import_csv, merge_transactions, valid_date
from money_tracker.net_worth import (
    snapshot_net_worth,
    net_worth_over_time,
    credit_card_balances,
    save_snapshots,
    load_snapshots,
)
from money_tracker.budget import BudgetPlanner, default_limits
from money_tracker.recurring import detect_recurring, CADENCE_BANDS
from money_tracker.payroll import detect_payroll, payroll_ytd
from money_tracker.dashboard import build_dashboard
from money_tracker.adapters import (
    AdapterError,
    AdapterNotConfiguredError,
    Balance,
    CoinbaseAdapter,
    Holding,
    PlaidAdapter,
    ReadOnlyAdapter,
    SampleDataAdapter,
)
from money_tracker.data_source import (
    get_adapter,
    load_local_config,
    config_path,
)

__version__ = "0.4.0"
__all__ = [
    "Transaction", "NetWorthSnapshot",
    "CATEGORIES", "all_paths", "classify",
    "TRANSFER_KEYWORDS", "P2P_KEYWORDS", "is_transfer", "is_p2p",
    "map_provider_category", "split_transfers",
    "TransferLedger", "build_ledger",
    "import_csv", "merge_transactions", "valid_date",
    "snapshot_net_worth", "net_worth_over_time", "credit_card_balances",
    "save_snapshots", "load_snapshots",
    "BudgetPlanner", "default_limits",
    "detect_recurring", "CADENCE_BANDS",
    "detect_payroll", "payroll_ytd",
    "build_dashboard",
    "AdapterError", "AdapterNotConfiguredError",
    "Balance", "Holding", "ReadOnlyAdapter",
    "SampleDataAdapter", "PlaidAdapter", "CoinbaseAdapter",
    "get_adapter", "load_local_config", "config_path",
]
