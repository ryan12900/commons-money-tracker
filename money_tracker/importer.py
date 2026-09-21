"""M3 — CSV import template.

Expected columns (header row required):
    date,description,amount,category,account

- `date` must be YYYY-MM-DD.
- `amount` is a signed number; negative = money out.
- `category` must be a valid path from taxonomy.all_paths().
  Unknown or blank categories become 'Uncategorized/Uncategorized'.
- Malformed rows are skipped and reported in `errors`.
"""

import csv

from money_tracker.models import Transaction
from money_tracker.taxonomy import all_paths


def import_csv(path: str):
    """Parse a CSV file. Returns (transactions, errors)."""
    valid = set(all_paths())
    transactions, errors = [], []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):  # row 1 is the header
            try:
                amount = float(row["amount"])
            except (KeyError, ValueError, TypeError):
                errors.append(f"row {i}: bad amount {row.get('amount')!r}")
                continue
            category = (row.get("category") or "").strip()
            if category not in valid:
                category = "Uncategorized/Uncategorized"
            transactions.append(Transaction(
                date=(row.get("date") or "").strip(),
                description=(row.get("description") or "").strip(),
                amount=amount,
                category=category,
                account=(row.get("account") or "").strip(),
                source=f"csv:{i}",
            ))
    return transactions, errors


def _tx_key(t) -> tuple:
    """Dedup identity: date + normalized description + amount + account."""
    return (
        t.date,
        t.description.strip().lower(),
        round(t.amount, 2),
        t.account.strip().lower(),
    )


def merge_transactions(existing: list, incoming: list) -> tuple:
    """Merge new transactions into an existing list, skipping duplicates.

    Dedup key is (date, description, amount, account). Returns
    (merged_list, added_count). The order of `existing` is preserved and
    genuinely new rows are appended. Re-importing the same CSV adds zero.
    """
    seen = {_tx_key(t) for t in existing}
    merged = list(existing)
    added = 0
    for t in incoming:
        key = _tx_key(t)
        if key not in seen:
            seen.add(key)
            merged.append(t)
            added += 1
    return merged, added
