# M7 — Peer Review Checklist

Every contribution to this repo needs approval from a **different agent**
before merge. Copy this into the PR description and have the reviewer sign off.

## Reviewer info
- Author agent:
- Reviewer agent:
- Sheet claim row (🚀money_tracker tab):
- Module(s):

## Checklist
- [ ] `make check` passes on the PR branch
- [ ] New code has tests
- [ ] Follows SPEC.md data model (Transaction / NetWorthSnapshot / Budget)
- [ ] Categories resolve to taxonomy paths; no invented top-level categories
- [ ] **Sample data only** — no real balances, holdings, accounts, spending,
      health data, credentials, addresses, or contacts in code, fixtures,
      or comments
- [ ] No hardcoded secrets, tokens, or API keys
- [ ] PR description names the claimed module

## Sign-off
- [ ] Approved by reviewer (different agent than author)
- [ ] Merged by:
