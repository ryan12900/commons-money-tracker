"""M3 — CSV import template.

Expected columns (header row required):
    date,description,amount,category,account

- `date` must be a real calendar date in YYYY-MM-DD format
  (validated strictly; malformed dates are reported as errors).
- `amount` is a signed number stored as Decimal; negative = money out.
- `category` must be a valid path from taxonomy.all_paths().
  Unknown or blank categories become 'Uncategorized/Uncategorized'.
- Malformed rows are skipped and reported in `errors`.
"""

import csv
import datetime
from decimal import Decimal, InvalidOperation

from money_tracker.models import Transaction
from money_tracker.taxonomy import all_paths


def valid_date(value: str) -> bool:
    """True only for real calendar dates in YYYY-MM-DD form."""
    try:
        datetime.date.fromisoformat(value)
        return True
    except (ValueError, TypeError):
        return False


def import_csv(path: str):
    """Parse a CSV file. Returns (transactions, errors)."""
    valid = set(all_paths())
    transactions, errors = [], []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):  # row 1 is the header
            date = (row.get("date") or "").strip()
            if not valid_date(date):
                errors.append(f"row {i}: bad date {date!r}")
                continue
            try:
                amount = Decimal(str(row["amount"]).strip())
            except (KeyError, InvalidOperation, TypeError, ValueError):
                errors.append(f"row {i}: bad amount {row.get('amount')!r}")
                continue
            category = (row.get("category") or "").strip()
            if category not in valid:
                category = "Uncategorized/Uncategorized"
            transactions.append(Transaction(
                date=date,
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
        t.amount.quantize(Decimal("0.01")),
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
