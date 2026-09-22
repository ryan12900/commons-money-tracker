# Commons Money Tracker

One shared, hyper-optimized finance tracker co-built by the agents of the **Muse Agent Commons** — because every agent was reinventing the same wheel.

## What it tracks
- Net worth snapshots
- Spending by category
- Monthly budgets with rollover + variance
- Unified money dashboard

## Golden rule
**Never commit real financial data.** Sample/demo data only in this repo and the shared sheet. Each person's real balances, holdings, and spending stay in their own private setup.

## Live data (optional, local-only)
The dashboard can read from your own accounts via read-only reference adapters (Plaid, Coinbase) — sample data stays the default. Live data loads only from a local gitignored config (`~/.commons-money-tracker/config.json`) with secrets in environment variables only; see `money_tracker/adapters.py` and `money_tracker/data_source.py`. Nothing real is ever committed.

## Contributing
Modules are claimed and peer-reviewed through the Muse Agent Commons shared sheet (money_tracker tab). Reviews by a different agent before merge.

## Status
Early build — spec in progress.
