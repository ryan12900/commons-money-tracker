"""Shared data model. Money is decimal.Decimal everywhere — plain floats are
never exact for money (0.1 + 0.2 != 0.3), and even demo data should be.

Sample/demo data only. Never commit real balances, accounts, or spending."""

from __future__ import annotations
from dataclasses import dataclass, field
from decimal import Decimal


@dataclass
class Transaction:
    date: str              # YYYY-MM-DD
    description: str       # free text from statement
    amount: Decimal        # negative = money out, positive = money in
    category: str          # "Parent/Leaf" path, see taxonomy.py
    account: str = ""      # label only, never account numbers
    source: str = "manual"

    def __post_init__(self):
        if not isinstance(self.amount, Decimal):
            # Decimal(str(...)) avoids float binary artifacts: 186.42 -> exact.
            self.amount = Decimal(str(self.amount))


@dataclass
class NetWorthSnapshot:
    as_of: str                       # YYYY-MM-DD
    assets: dict                     # {label: amount}
    liabilities: dict                # {label: amount}

    def __post_init__(self):
        self.assets = {k: Decimal(str(v)) for k, v in self.assets.items()}
        self.liabilities = {k: Decimal(str(v)) for k, v in self.liabilities.items()}

    @property
    def net_worth(self) -> Decimal:
        return (sum(self.assets.values(), Decimal("0"))
                - sum(self.liabilities.values(), Decimal("0")))


@dataclass
class Budget:
    month: str                       # YYYY-MM
    limits: dict = field(default_factory=dict)   # {category path: amount}
    rollover: dict = field(default_factory=dict) # unspent carried forward
