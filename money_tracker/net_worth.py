"""M4 — Net-worth snapshots: point-in-time assets minus liabilities."""

import json
import os
from decimal import Decimal

from money_tracker.models import NetWorthSnapshot


def snapshot_net_worth(as_of: str, assets: dict, liabilities: dict) -> NetWorthSnapshot:
    """Build one snapshot. Labels are free text; amounts become Decimal."""
    return NetWorthSnapshot(
        as_of=as_of,
        assets=dict(assets),
        liabilities=dict(liabilities),
    )


def net_worth_over_time(snapshots: list) -> list:
    """Sorted (as_of, net_worth-as-float) series for the dashboard."""
    ordered = sorted(snapshots, key=lambda s: s.as_of)
    return [(s.as_of, float(s.net_worth)) for s in ordered]


def credit_card_balances(snapshot: NetWorthSnapshot) -> dict:
    """Balances-by-card view for one snapshot.

    Liability labels containing "card" (case-insensitive) are treated as
    credit-card accounts — a label convention, not a classification: name
    cards with "card" in the label (e.g. "demo-credit-card") to appear here.
    Returns {cards: {label: Decimal}, total: Decimal}.
    """
    cards = {
        label: balance
        for label, balance in snapshot.liabilities.items()
        if "card" in label.lower()
    }
    return {
        "cards": cards,
        "total": sum(cards.values(), Decimal("0")),
    }


def save_snapshots(path: str, snapshots: list) -> None:
    """Persist snapshots to a JSON file: [{as_of, assets, liabilities}].

    Amounts are stored as decimal strings, not floats — JSON has no decimal
    type and floats cannot represent most cent values (0.1 + 0.2 != 0.3),
    so string storage is the only exact round-trip. Loading coerces them
    back to Decimal. Sample/demo data only — never write real balances.
    """
    payload = [
        {
            "as_of": s.as_of,
            "assets": {k: str(v) for k, v in s.assets.items()},
            "liabilities": {k: str(v) for k, v in s.liabilities.items()},
        }
        for s in snapshots
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def load_snapshots(path: str) -> list:
    """Load snapshots saved by save_snapshots.

    Returns [] when the file is absent OR unreadable — corrupt JSON,
    wrong shape, or unparseable amounts. A broken history file must never
    crash the dashboard, so every failure mode degrades to an empty list.
    """
    if not os.path.exists(path):
        return []
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, list):
            return []
        return [
            NetWorthSnapshot(
                as_of=p["as_of"],
                assets=p["assets"],
                liabilities=p["liabilities"],
            )
            for p in payload
            if isinstance(p, dict)
            and isinstance(p.get("assets"), dict)
            and isinstance(p.get("liabilities"), dict)
            and "as_of" in p
        ]
    except (OSError, ValueError, ArithmeticError):
        # OSError: unreadable file. ValueError: JSONDecodeError.
        # ArithmeticError: Decimal.InvalidOperation on garbage amounts.
        return []
