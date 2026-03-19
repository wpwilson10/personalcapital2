# personalcapital2

Python client for the Empower (formerly Personal Capital) unofficial API.

> **Disclaimer:** This library is unofficial and not affiliated with Empower or Personal Capital. It accesses Empower's internal web API, which is undocumented and may change without notice.

The package is named `personalcapital2` for discoverability (it replaces the abandoned `personalcapital` package). The API classes use `Empower*` because that's the current service name.

## What you can get

- **Accounts** — linked bank, investment, credit, and loan accounts
- **Transactions** — spending, income, and transfers with categories
- **Holdings** — investment positions with tickers, quantities, and values
- **Net worth** — daily historical breakdown (assets, liabilities, cash, investments, etc.)
- **Account balances** — daily balance history per account
- **Investment performance** — cumulative returns per account
- **Benchmark performance** — S&P 500 and other index returns for comparison
- **Portfolio vs benchmark** — side-by-side portfolio and S&P 500 indexed values

## Install

```bash
pip install personalcapital2
```

## Quick start

```python
from datetime import date
from personalcapital2 import EmpowerClient, authenticate

# Interactive login (handles 2FA prompts)
client = authenticate()

# Fetch typed data — no need to know endpoint URLs or parsers
accounts = client.get_accounts()
for acct in accounts:
    print(f"{acct.name} ({acct.firm_name}): asset={acct.is_asset}")

transactions = client.get_transactions(date(2026, 1, 1), date(2026, 3, 31))
for txn in transactions:
    print(f"{txn.date} {txn.description}: ${txn.amount}")

holdings = client.get_holdings()
net_worth = client.get_net_worth(date(2025, 1, 1), date(2026, 3, 31))
balances = client.get_account_balances(date(2025, 1, 1), date(2026, 3, 31))

# Performance requires account IDs (no hidden network calls)
inv_ids = [a.user_account_id for a in accounts if a.product_type == "INVESTMENT"]
perf = client.get_investment_performance(date(2025, 1, 1), date(2026, 3, 31), inv_ids)
benchmarks = client.get_benchmark_performance(date(2025, 1, 1), date(2026, 3, 31), inv_ids)
pvb = client.get_portfolio_vs_benchmark(date(2025, 1, 1), date(2026, 3, 31))
categories = client.get_categories(date(2026, 1, 1), date(2026, 3, 31))
```

All convenience methods return frozen dataclasses with proper types (`datetime.date` for dates, `float` for amounts, `None` for optional fields).

## Low-level API

For direct API access, use `fetch()` with the raw endpoint and optional parsers:

```python
from personalcapital2.parsers import parse_accounts

data = client.fetch("/newaccount/getAccounts2")
rows = parse_accounts(data, synced_at="2026-01-01T00:00:00")
# rows is list[dict[str, Any]] — the parser's raw output
```

## Known API issues

The Empower API has quirks that this library passes through without modification:

- **`is_spending` is unreliable on refunds.** Refunds and reimbursements can have `is_spending=True` even though they are money coming in. Use `transaction_type` (e.g. `"Refund"`) to identify refunds rather than relying on `is_spending` alone.

## Development

```bash
uv sync
uv run pytest
uv run pyright .
uv run ruff check .
```
