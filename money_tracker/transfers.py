"""Transfer detection + provider-category mapping (extends M3).

A transfer moves money between the user's own accounts (credit-card payment,
savings transfer, brokerage funding). Transfers are NOT income or spending:
counting them inflates both sides of the dashboard, so split them out before
reporting.

Detection here is keyword-based on the description. Providers that ship their
own category codes should map them explicitly with map_provider_category()
instead of relying on keywords.
"""

from money_tracker.taxonomy import all_paths

TRANSFER_KEYWORDS = [
    "credit card payment",
    "card payment",
    "autopay",
    "transfer",
    "xfer",
]

_VALID_PATHS = set(all_paths())


def is_transfer(description: str) -> bool:
    """True when the description looks like an inter-account transfer."""
    text = (description or "").lower()
    return any(k in text for k in TRANSFER_KEYWORDS)


def map_provider_category(code: str, mapping: dict) -> tuple:
    """Map a provider's category code to (taxonomy path, is_transfer).

    mapping: {provider_code: (taxonomy path, is_transfer)}.
    Unknown codes resolve to ("Uncategorized/Uncategorized", False) — never
    guessed. Paths not in the taxonomy are demoted to Uncategorized.
    """
    path, transfer = mapping.get(code, ("Uncategorized/Uncategorized", False))
    if path not in _VALID_PATHS:
        path = "Uncategorized/Uncategorized"
    return path, bool(transfer)


def split_transfers(transactions: list) -> tuple:
    """Partition transactions into (real_transactions, transfers)."""
    real, transfers = [], []
    for t in transactions:
        (transfers if is_transfer(t.description) else real).append(t)
    return real, transfers
