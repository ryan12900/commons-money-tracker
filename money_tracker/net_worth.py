"""M4 — Net-worth snapshots: point-in-time assets minus liabilities."""

import json
import os

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


def save_snapshots(path: str, snapshots: list) -> None:
    """Persist snapshots to a JSON file: [{as_of, assets, liabilities}].

    Amounts are stored as floats (JSON has no decimal type); loading coerces
    them back to Decimal. Sample/demo data only — never write real balances.
    """
    payload = [
        {
            "as_of": s.as_of,
            "assets": {k: float(v) for k, v in s.assets.items()},
            "liabilities": {k: float(v) for k, v in s.liabilities.items()},
        }
        for s in snapshots
    ]
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)


def load_snapshots(path: str) -> list:
    """Load snapshots saved by save_snapshots. Returns [] if the file is absent."""
    if not os.path.exists(path):
        return []
    with open(path) as f:
        payload = json.load(f)
    return [
        NetWorthSnapshot(
            as_of=p["as_of"],
            assets=p["assets"],
            liabilities=p["liabilities"],
        )
        for p in payload
    ]
