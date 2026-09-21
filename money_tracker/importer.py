"""M3 — CSV import template.

Expected columns (header row required):
    date,description,amount,category,account

Optional enrichment columns (may be absent):
    merchant,location,items
  - `items` holds order/item names as semicolon-separated text
    ("Organic Milk;Bananas") for order/item enrichment.

- `date` must be a real calendar date in YYYY-MM-DD format
  (validated strictly; malformed dates are reported as errors).
- `amount` is a signed number stored as Decimal; negative = money out.
  Bank formatting is tolerated: a leading `$`, thousands commas, and
  parenthesized negatives ("(12.34)" -> -12.34) are stripped first.
  Non-finite values (NaN, Infinity) are rejected as errors.
- `category` must be a valid path from taxonomy.all_paths()
  (matched case-insensitively). Unknown or blank categories become
  'Uncategorized/Uncategorized' — never guessed.
- Malformed rows are skipped and reported in `errors`.
- Files are opened with `utf-8-sig` so a UTF-8 BOM cannot mangle the
  first header into an invisible date/amount.
"""

import csv
import datetime
from decimal import Decimal, InvalidOperation

from money_tracker.models import Transaction
from money_tracker.taxonomy import all_paths

_VALID_PATHS = {p.lower(): p for p in all_paths()}


def valid_date(value: str) -> bool:
    """True only for real calendar dates in YYYY-MM-DD form."""
    try:
        datetime.date.fromisoformat(value)
        return True
    except (ValueError, TypeError):
        return False


def _clean_amount(raw) -> Decimal:
    """Parse a bank-formatted amount into a finite Decimal.

    Tolerates '$', thousands separators, and parenthesized negatives.
    Raises InvalidOperation on anything else — including NaN/Infinity,
    which Decimal would otherwise accept silently.
    """
    text = str(raw or "").strip()
    negative = text.startswith("(") and text.endswith(")")
    text = text.strip("()").replace("$", "").replace(",", "").strip()
    amount = Decimal(text)  # raises InvalidOperation on garbage
    if not amount.is_finite():
        raise InvalidOperation("non-finite amount")
    return -amount if negative else amount


def import_csv(path: str):
    """Parse a CSV file. Returns (transactions, errors)."""
    transactions, errors = [], []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):  # row 1 is the header
            date = (row.get("date") or "").strip()
            if not valid_date(date):
                errors.append(f"row {i}: bad date {date!r}")
                continue
            try:
                amount = _clean_amount(row.get("amount"))
            except (InvalidOperation, TypeError, ValueError):
                errors.append(f"row {i}: bad amount {row.get('amount')!r}")
                continue
            category = (row.get("category") or "").strip()
            category = _VALID_PATHS.get(category.lower(), "Uncategorized/Uncategorized")
            items = [i.strip() for i in (row.get("items") or "").split(";")]
            transactions.append(Transaction(
                date=date,
                description=(row.get("description") or "").strip(),
                amount=amount,
                category=category,
                account=(row.get("account") or "").strip(),
                source=f"csv:{i}",
                merchant=(row.get("merchant") or "").strip(),
                location=(row.get("location") or "").strip(),
                items=[i for i in items if i],
            ))
    return transactions, errors


def _tx_key(t) -> tuple:
    """Dedup identity: date + normalized description + amount + account.

    Amounts are quantized to cents so Decimal values dedup exactly —
    no float binary dust can split or merge keys.
    """
    return (
        t.date,
        t.description.strip().lower(),
        t.amount.quantize(Decimal("0.01")),
        t.account.strip().lower(),
    )


def merge_transactions(existing: list, incoming: list, allow_duplicates: bool = False) -> tuple:
    """Merge new transactions into an existing list, skipping duplicates.

    Dedup key is (date, description, amount, account); re-importing the same
    CSV adds zero. Returns (merged_list, added_count). The order of
    `existing` is preserved and genuinely new rows are appended.

    Known trade-off: two genuinely identical purchases (same coffee, same
    card, same day) share one dedup key and collapse into a single entry.
    If your data has real duplicates, disambiguate the descriptions
    ("Demo Coffee #2") or pass allow_duplicates=True to keep every row.
    """
    seen = {_tx_key(t) for t in existing}
    merged = list(existing)
    added = 0
    for t in incoming:
        key = _tx_key(t)
        if allow_duplicates or key not in seen:
            seen.add(key)
            merged.append(t)
            added += 1
    return merged, added
