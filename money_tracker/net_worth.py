"""M4 — Net-worth snapshots: point-in-time assets minus liabilities."""

from money_tracker.models import NetWorthSnapshot


def snapshot_net_worth(as_of: str, assets: dict, liabilities: dict) -> NetWorthSnapshot:
    """Build one snapshot. Labels are free text, amounts signed."""
    return NetWorthSnapshot(
        as_of=as_of,
        assets=dict(assets),
        liabilities=dict(liabilities),
    )


def net_worth_over_time(snapshots: list) -> list:
    """Sorted (as_of, net_worth) series for the dashboard."""
    ordered = sorted(snapshots, key=lambda s: s.as_of)
    return [(s.as_of, s.net_worth) for s in ordered]
