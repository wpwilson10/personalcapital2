# personalcapital2

Python client for the Empower (formerly Personal Capital) unofficial API.

> **Disclaimer:** This library is unofficial and not affiliated with Empower or Personal Capital. It accesses Empower's internal web API, which is undocumented and may change without notice.

The package is named `personalcapital2` for discoverability (it replaces the abandoned `personalcapital` package). The API classes use `Empower*` because that's the current service name.

Based on the original reverse-engineering work by [haochi/personalcapital](https://github.com/haochi/personalcapital) (MIT) and the URL migration fix by [traviscook21/personalcapital](https://github.com/traviscook21/personalcapital) (MIT). Rewritten with type safety, JSON session persistence, proper error handling, and a typed model layer.

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

## Models

All convenience methods return frozen dataclasses with proper types (`datetime.date` for dates, `float` for amounts, `None` for optional fields).

### Account

| Field | Type |
|---|---|
| `user_account_id` | `int` |
| `account_id` | `str` |
| `name` | `str` |
| `firm_name` | `str` |
| `account_type` | `str` |
| `account_type_group` | `str \| None` |
| `product_type` | `str` |
| `currency` | `str` |
| `is_asset` | `bool` |
| `is_closed` | `bool` |
| `created_at` | `date \| None` |

### Transaction

| Field | Type |
|---|---|
| `user_transaction_id` | `int` |
| `user_account_id` | `int` |
| `date` | `date` |
| `amount` | `float` |
| `is_cash_in` | `bool` |
| `is_income` | `bool` |
| `is_spending` | `bool` |
| `description` | `str` |
| `original_description` | `str \| None` |
| `simple_description` | `str \| None` |
| `category_id` | `int \| None` |
| `merchant` | `str \| None` |
| `transaction_type` | `str \| None` |
| `status` | `str \| None` |
| `currency` | `str` |

### Category

| Field | Type |
|---|---|
| `category_id` | `int` |
| `name` | `str` |
| `type` | `str` |

### Holding

| Field | Type |
|---|---|
| `snapshot_date` | `date` |
| `user_account_id` | `int` |
| `ticker` | `str \| None` |
| `cusip` | `str \| None` |
| `description` | `str` |
| `quantity` | `float` |
| `price` | `float` |
| `value` | `float` |
| `holding_type` | `str \| None` |
| `security_type` | `str \| None` |
| `holding_percentage` | `float \| None` |
| `source` | `str \| None` |

### NetWorthEntry

| Field | Type |
|---|---|
| `date` | `date` |
| `networth` | `float` |
| `total_assets` | `float` |
| `total_liabilities` | `float` |
| `total_cash` | `float` |
| `total_investment` | `float` |
| `total_credit` | `float` |
| `total_mortgage` | `float` |
| `total_loan` | `float` |
| `total_other_assets` | `float` |
| `total_other_liabilities` | `float` |

### AccountBalance

| Field | Type |
|---|---|
| `date` | `date` |
| `user_account_id` | `int` |
| `balance` | `float` |

### InvestmentPerformance

| Field | Type |
|---|---|
| `date` | `date` |
| `user_account_id` | `int` |
| `performance` | `float \| None` |

### BenchmarkPerformance

| Field | Type |
|---|---|
| `date` | `date` |
| `benchmark` | `str` |
| `performance` | `float` |

### PortfolioVsBenchmark

| Field | Type |
|---|---|
| `date` | `date` |
| `portfolio_value` | `float \| None` |
| `sp500_value` | `float \| None` |

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
