"""M8 — Recurring transaction detection.

Groups transactions by normalized merchant description and flags merchants
that repeat on a regular cadence: subscriptions, rent, payroll deposits,
utility autopays. Detected series feed the dashboard's "recurring" section so
a tracker can tell fixed obligations apart from one-off spending.

Cadence bands (day gaps between consecutive occurrences, all must land in
the same band):
    weekly:    6-8
    biweekly: 12-16
    monthly:  27-33

Sample/demo data only — run this over the user's own import, not fixtures.
"""

import datetime
from decimal import Decimal

CADENCE_BANDS = {
    "weekly": (6, 8),
    "biweekly": (12, 16),
    "monthly": (27, 33),
}


def _merchant_key(description: str) -> str:
    return (description or "").strip().lower()


def _band_for(gaps: list) -> str | None:
    """Cadence name if every gap falls in the same band, else None."""
    names = []
    for g in gaps:
        name = next((n for n, (lo, hi) in CADENCE_BANDS.items() if lo <= g <= hi),
                    None)
        if name is None:
            return None
        names.append(name)
    return names[0] if len(set(names)) == 1 else None


def detect_recurring(transactions: list, min_occurrences: int = 3) -> list:
    """Flag merchants repeating on a weekly/biweekly/monthly cadence.

    Returns [{merchant, cadence, occurrences, avg_amount (Decimal),
    last_date}], sorted by average amount descending. Merchants with fewer
    than min_occurrences, or with irregular gaps, are ignored.
    """
    groups: dict[str, list] = {}
    for t in transactions:
        groups.setdefault(_merchant_key(t.description), []).append(t)

    found = []
    for merchant, items in groups.items():
        if len(items) < min_occurrences:
            continue
        dates = sorted(datetime.date.fromisoformat(t.date) for t in items)
        gaps = [(dates[i + 1] - dates[i]).days for i in range(len(dates) - 1)]
        cadence = _band_for(gaps)
        if cadence is None:
            continue
        total = sum((abs(t.amount) for t in items), Decimal("0"))
        found.append({
            "merchant": merchant,
            "cadence": cadence,
            "occurrences": len(items),
            "avg_amount": total / len(items),
            "last_date": dates[-1].isoformat(),
        })
    return sorted(found, key=lambda r: r["avg_amount"], reverse=True)
