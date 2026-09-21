"""Transfer detection + provider-category mapping (extends M3).

A transfer moves money between the user's own accounts (credit-card payment,
savings transfer, brokerage funding). Transfers are NOT income or spending:
counting them inflates both sides of the dashboard, so split them out before
reporting.

Detection here is keyword-based on the description. Providers that ship their
own category codes should map them explicitly with map_provider_category()
instead of relying on keywords.

Keyword detection is a heuristic, not a classification: Zelle / Venmo /
Cash App / wire can also be real spending (paying a friend back for dinner,
paying a contractor). Treat the transfer list as a review queue before
excluding it from spend — when the provider ships category codes, prefer
map_provider_category() for precision.
"""

from money_tracker.taxonomy import all_paths
from decimal import Decimal

TRANSFER_KEYWORDS = [
    "credit card payment",
    "card payment",
    "autopay",
    "transfer",
    "xfer",
    # peer-to-peer rails — often inter-account moves; see the heuristic
    # caveat above. Review before excluding from spend.
    "zelle",
    "venmo",
    "cash app",
    "cashapp",
    "wire",
]

_VALID_PATHS = set(all_paths())

# Rails that are peer-to-peer by nature (vs. inter-account moves like
# "credit card payment"). A P2P transfer may be a real expense (paying a
# friend back for dinner) or a pure money move — the ledger below is the
# review queue where that call gets made.
P2P_KEYWORDS = ["zelle", "venmo", "cash app", "cashapp"]


def is_transfer(description: str) -> bool:
    """True when the description looks like an inter-account transfer."""
    text = (description or "").lower()
    return any(k in text for k in TRANSFER_KEYWORDS)


def is_p2p(description: str) -> bool:
    """True when the description looks like a peer-to-peer payment."""
    text = (description or "").lower()
    return any(k in text for k in P2P_KEYWORDS)


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


class TransferLedger:
    """Review queue for peer-to-peer payments, with manual relabeling.

    Keyword detection (is_p2p) cannot tell a real expense ("Zelle to Demo
    Dana for dinner") from a money move ("Venmo cashout to checking"). The
    ledger holds every detected P2P payment; a human relabels each entry
    into its true category (or leaves it Uncategorized to keep it excluded
    from spend). Amounts stay Decimal throughout.
    """

    def __init__(self):
        self._entries: list[dict] = []
        self._next_id = 1

    def add(self, transaction) -> int:
        """Record one P2P transfer. Returns the entry id."""
        amount = transaction.amount
        if not isinstance(amount, Decimal):
            amount = Decimal(str(amount))
        entry = {
            "id": self._next_id,
            "date": transaction.date,
            "description": transaction.description,
            "amount": amount,
            "account": transaction.account,
            "category": "Uncategorized/Uncategorized",
        }
        self._entries.append(entry)
        self._next_id += 1
        return entry["id"]

    def relabel(self, entry_id: int, category_path: str) -> dict:
        """Assign an entry its true category. Unknown paths raise ValueError
        instead of silently producing a category the reports can't see."""
        if category_path not in _VALID_PATHS:
            raise ValueError(
                f"unknown category path: {category_path!r} — "
                "see taxonomy.all_paths()"
            )
        entry = self._find(entry_id)
        entry["category"] = category_path
        return entry

    def _find(self, entry_id: int) -> dict:
        for e in self._entries:
            if e["id"] == entry_id:
                return e
        raise KeyError(f"no ledger entry with id {entry_id}")

    def entries(self) -> list:
        """All entries, oldest first. Unlabeled ones are still unreviewed."""
        return sorted(self._entries, key=lambda e: (e["date"], e["id"]))

    def unreviewed(self) -> list:
        """Entries still sitting in Uncategorized — the review backlog."""
        return [e for e in self.entries()
                if e["category"] == "Uncategorized/Uncategorized"]

    def relabeled_spend(self) -> dict:
        """{category: total} over entries a human relabeled — real spend
        rescued from the transfer exclusion."""
        totals: dict[str, Decimal] = {}
        for e in self._entries:
            if e["category"] != "Uncategorized/Uncategorized" and e["amount"] < 0:
                totals[e["category"]] = totals.get(e["category"], Decimal("0")) \
                    + abs(e["amount"])
        return totals


def build_ledger(transactions: list) -> TransferLedger:
    """Collect every P2P-keyword transaction into a fresh TransferLedger."""
    ledger = TransferLedger()
    for t in transactions:
        if is_p2p(t.description):
            ledger.add(t)
    return ledger
