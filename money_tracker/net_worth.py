"""M4 — Net-worth snapshots: point-in-time assets minus liabilities."""
import json
import os
from decimal import Decimal
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

def save_snapshots(path: str, snapshots: list) -> None:
    """Persist snapshots to a JSON file: [{as_of, assets, liabilities}].
    Sample/demo data only — never write real balances here.
    """
    payload = [
        {
            "as_of": s.as_of,
            "assets": dict(s.assets),
            "liabilities": dict(s.liabilities),
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

ASSET_CLASSES = ("cash", "investments", "retirement", "real_estate", "crypto", "other")
LIABILITY_CLASSES = ("credit_cards", "mortgage", "student_loans", "auto_loans", "other")

# Label-convention keyword map. Classes are checked in order, first match
# wins — name accounts so the class shows up: "demo-401k" -> retirement,
# "demo-mortgage" -> mortgage. Ambiguous labels fall through to "other".
_ASSET_KEYWORDS = {
    "cash": ("checking", "savings", "cash", "money market", "money-market"),
    "investments": ("brokerage", "invest", "stock", "etf", "mutual", "fund"),
    "retirement": ("retire", "401k", "403b", "ira", "pension", "roth"),
    "real_estate": ("property", "real estate", "real-estate", "home", "house", "condo"),
    "crypto": ("crypto", "btc", "bitcoin", "eth", "ethereum", "sol", "solana", "wallet"),
}
_LIABILITY_KEYWORDS = {
    # credit cards first: "credit card" contains "car", so the auto class
    # must never be checked before it.
    "credit_cards": ("card",),
    "mortgage": ("mortgage",),
    "student_loans": ("student",),
    "auto_loans": ("auto", "vehicle", "car loan", "car-loan"),
}

def _classify(label: str, keyword_map: dict, classes: tuple) -> str:
    lowered = label.lower()
    for cls in classes:
        if any(kw in lowered for kw in keyword_map.get(cls, ())):
            return cls
    return "other"

def classify_asset(label: str) -> str:
    """Asset class for an account label, one of ASSET_CLASSES."""
    return _classify(label, _ASSET_KEYWORDS, ASSET_CLASSES)

def classify_liability(label: str) -> str:
    """Liability class for an account label, one of LIABILITY_CLASSES."""
    return _classify(label, _LIABILITY_KEYWORDS, LIABILITY_CLASSES)

def net_worth_breakdown(snapshot: NetWorthSnapshot) -> dict:
    """Class-by-class breakdown of one snapshot.
    Returns {"assets": {class: Decimal}, "liabilities": {class: Decimal},
    "asset_share_pct": {class: float}, "liability_share_pct": {class: float},
    "total_assets": Decimal, "total_liabilities": Decimal,
    "net_worth": Decimal}.
    Shares are each class's percentage of total assets / total liabilities
    (0.0 when that side is empty — no division by zero). Classification is a
    label convention: name accounts so the class shows up, e.g.
    "demo-brokerage" lands in investments and "demo-student-loan" in
    student_loans.
    """
    assets: dict = {cls: Decimal("0") for cls in ASSET_CLASSES}
    liabilities: dict = {cls: Decimal("0") for cls in LIABILITY_CLASSES}
    for label, amount in snapshot.assets.items():
        assets[classify_asset(label)] += Decimal(str(amount))
    for label, amount in snapshot.liabilities.items():
        liabilities[classify_liability(label)] += Decimal(str(amount))

    total_assets = sum(assets.values(), Decimal("0"))
    total_liabilities = sum(liabilities.values(), Decimal("0"))

    def _shares(by_class: dict, total: Decimal) -> dict:
        if total == 0:
            return {cls: 0.0 for cls in by_class}
        return {cls: float((amt / total * 100)) for cls, amt in by_class.items()}

    return {
        "assets": assets,
        "liabilities": liabilities,
        "asset_share_pct": _shares(assets, total_assets),
        "liability_share_pct": _shares(liabilities, total_liabilities),
        "total_assets": total_assets,
        "total_liabilities": total_liabilities,
        "net_worth": total_assets - total_liabilities,
    }
