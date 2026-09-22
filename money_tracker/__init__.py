"""Commons Money Tracker — shared finance core (sample data only)."""

from money_tracker.models import Transaction, NetWorthSnapshot, Budget
from money_tracker.taxonomy import CATEGORIES, all_paths, classify
from money_tracker.transfers import (
    TRANSFER_KEYWORDS,
    is_transfer,
    map_provider_category,
    split_transfers,
)
from money_tracker.importer import import_csv, merge_transactions
from money_tracker.net_worth import (
    snapshot_net_worth,
    net_worth_over_time,
    classify_asset,
    classify_liability,
    net_worth_breakdown,
    save_snapshots,
    load_snapshots,
)
from money_tracker.budget import BudgetPlanner, default_limits
from money_tracker.dashboard import build_dashboard

__version__ = "0.2.0"
__all__ = [
    "Transaction", "NetWorthSnapshot", "Budget",
    "CATEGORIES", "all_paths", "classify",
    "TRANSFER_KEYWORDS", "is_transfer", "map_provider_category", "split_transfers",
    "import_csv", "merge_transactions",
    "snapshot_net_worth", "net_worth_over_time", "save_snapshots", "load_snapshots",
    "classify_asset", "classify_liability", "net_worth_breakdown",
    "BudgetPlanner", "default_limits", "build_dashboard",
]
