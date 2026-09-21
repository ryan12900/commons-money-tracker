"""Shared data model. Amounts are plain floats — sample/demo data only."""

from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class Transaction:
    date: str              # YYYY-MM-DD
    description: str       # free text from statement
    amount: float          # negative = money out, positive = money in
    category: str          # "Parent/Leaf" path, see taxonomy.py
    account: str = ""      # label only, never account numbers
    source: str = "manual"


@dataclass
class NetWorthSnapshot:
    as_of: str                       # YYYY-MM-DD
    assets: dict                     # {label: amount}
    liabilities: dict                # {label: amount}

    @property
    def net_worth(self) -> float:
        return sum(self.assets.values()) - sum(self.liabilities.values())


@dataclass
class Budget:
    month: str                       # YYYY-MM
    limits: dict = field(default_factory=dict)   # {category path: amount}
    rollover: dict = field(default_factory=dict) # unspent carried forward
