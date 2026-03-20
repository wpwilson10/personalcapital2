# personalcapital2

Typed Python client for the Empower (formerly Personal Capital) API. Authenticate, fetch your financial data, and get back clean dataclasses.

> This library is unofficial and not affiliated with Empower. It uses their internal web API, which may change without notice.

Based on [haochi/personalcapital](https://github.com/haochi/personalcapital) and [traviscook21/personalcapital](https://github.com/traviscook21/personalcapital) (both MIT). Rewritten with type safety, structured error handling, and a typed model layer.

## Install

```bash
pip install personalcapital2
```

## Quick start

```python
from datetime import date
from personalcapital2 import EmpowerClient, authenticate

client = authenticate()  # interactive login with 2FA

accounts = client.get_accounts()
transactions = client.get_transactions(date(2026, 1, 1), date(2026, 3, 31))

for txn in transactions:
    print(f"{txn.date}  {txn.description:<30}  ${txn.amount:.2f}")
```

## CLI

A command-line interface is included as `pc2`:

```bash
# Authenticate (interactive, supports 2FA)
pc2 login

# Fetch data
pc2 accounts
pc2 transactions --start 30d --end today
pc2 holdings
pc2 net-worth --start mb-12 --end today
pc2 balances --start 90d --end today
pc2 categories --start mb --end today
pc2 portfolio --start 365d --end today
pc2 performance --start 365d --end today --account-ids 100,200
pc2 benchmarks --start 365d --end today --account-ids 100,200

# Output as CSV
pc2 --format csv transactions --start 30d --end today

# Raw API call
pc2 raw /newaccount/getAccounts2

# Session management
pc2 status
pc2 logout
```

Date shortcuts: `today`, `30d` (days ago), `mb` (month begin), `mb-3` (3 months ago begin), `me` (month end), `me-1` (last month end).

## Available methods

| Method | Returns |
|---|---|
| `get_accounts()` | `list[Account]` |
| `get_transactions(start, end)` | `list[Transaction]` |
| `get_categories(start, end)` | `list[Category]` |
| `get_holdings()` | `list[Holding]` |
| `get_net_worth(start, end)` | `list[NetWorthEntry]` |
| `get_account_balances(start, end)` | `list[AccountBalance]` |
| `get_investment_performance(start, end, account_ids)` | `list[InvestmentPerformance]` |
| `get_benchmark_performance(start, end, account_ids)` | `list[BenchmarkPerformance]` |
| `get_performance_and_benchmarks(start, end, account_ids)` | `tuple[list[InvestmentPerformance], list[BenchmarkPerformance]]` |
| `get_portfolio_vs_benchmark(start, end)` | `list[PortfolioVsBenchmark]` |

Date parameters are `datetime.date`. Financial values are `decimal.Decimal`. All methods return frozen dataclasses — see [Model Reference](docs/models.md) for every field and type.

## More examples

```python
# Net worth over time
net_worth = client.get_net_worth(date(2025, 1, 1), date(2026, 3, 31))
for nw in net_worth:
    print(f"{nw.date}  assets={nw.total_assets:.0f}  liabilities={nw.total_liabilities:.0f}")

# Investment performance (requires explicit account IDs — no hidden API calls)
accounts = client.get_accounts()
inv_ids = [a.user_account_id for a in accounts if a.product_type == "INVESTMENT"]
perf = client.get_investment_performance(date(2025, 1, 1), date(2026, 3, 31), inv_ids)

# Current holdings
for h in client.get_holdings():
    print(f"{h.ticker or h.description:<10}  {h.quantity:.2f} × ${h.price:.2f} = ${h.value:.2f}")
```

## Low-level API

For direct endpoint access, use `fetch()` with optional parsers:

```python
from personalcapital2.parsers import parse_accounts

data = client.fetch("/newaccount/getAccounts2")
rows = parse_accounts(data)
# list[dict[str, Any]] — raw parser output, no dataclass conversion
```

## Known API issues

- **`is_spending` is unreliable on refunds.** Refunds can have `is_spending=True` even though they're money coming in. Use `transaction_type` (e.g. `"Refund"`) instead.

## Development

```bash
uv sync
uv run pytest
uv run pyright .
uv run ruff check .
```
