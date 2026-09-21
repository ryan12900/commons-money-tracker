"""M2 — Canonical spending taxonomy.

Two-level tree. Every transaction resolves to exactly one leaf.
Unknown descriptions classify to 'Uncategorized', never guessed.
Renames go through spec review (M7).
"""

import re

CATEGORIES = {
    "Food": ["Groceries", "Dining Out", "Coffee", "Delivery"],
    "Housing": ["Rent", "Utilities", "Internet", "Maintenance"],
    "Transport": ["Transit", "Rideshare", "Gas", "Parking"],
    "Health": ["Gym", "Medical", "Pharmacy", "Wellness"],
    "Shopping": ["Clothing", "Electronics", "Home", "Personal Care"],
    "Entertainment": ["Streaming", "Events", "Games", "Hobbies"],
    "Travel": ["Flights", "Hotels", "Food Away", "Local Transport"],
    "Finance": ["Fees", "Interest", "Investments", "Insurance"],
    "Income": ["Salary", "Bonus", "Side Gig", "Interest Earned"],
    "Uncategorized": ["Uncategorized"],
}

# keyword hints per leaf, used only as a fallback for manual entry
_KEYWORDS = {
    "Food/Groceries": ["whole foods", "trader joe", "grocery", "supermarket"],
    "Food/Dining Out": ["restaurant", "chipotle", "sweetgreen", "diner"],
    "Food/Coffee": ["starbucks", "coffee", "blue bottle"],
    "Housing/Rent": ["rent", "landlord"],
    "Housing/Utilities": ["con ed", "utility", "electric"],
    "Transport/Transit": ["metro", "mta", "omny"],
    "Transport/Rideshare": ["uber", "lyft"],
    "Income/Salary": ["payroll", "salary", "paycheck"],
    "Finance/Investments": ["brokerage", "schwab", "fidelity"],
}


def all_paths() -> list:
    """Every valid 'Parent/Leaf' path."""
    return [f"{parent}/{leaf}" for parent, leaves in CATEGORIES.items() for leaf in leaves]


def classify(description: str) -> str:
    """Best-effort keyword match on a leading word boundary.

    Returns 'Uncategorized/Uncategorized' when unsure — never guessed.
    The leading boundary stops mid-word false positives: 'Different Store'
    does NOT match the 'rent' keyword, while 'Rent - 5th Ave' and
    'Con Edison' (prefix of the 'con ed' keyword) still do.
    """
    text = (description or "").lower()
    for path, keywords in _KEYWORDS.items():
        if any(re.search(rf"\b{re.escape(k)}", text) for k in keywords):
            return path
    return "Uncategorized/Uncategorized"
