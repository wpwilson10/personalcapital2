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

result = client.get_accounts()
for acct in result.accounts:
    print(f"{acct.name:<30} {acct.firm_name}")
print(f"Net worth: ${result.summary.networth:.2f}")

result = client.get_transactions(date(2026, 1, 1), date(2026, 3, 31))
for txn in result.transactions:
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
pc2 snapshot --start 365d --end today
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

Each method makes a single HTTP request and returns a response container with typed data and summary information.

| Method | Returns | Description |
|---|---|---|
| `get_accounts()` | `AccountsResult` | Linked accounts + aggregate summary |
| `get_transactions(start, end)` | `TransactionsResult` | Transactions + categories + cashflow summary |
| `get_holdings()` | `HoldingsResult` | Investment holdings + total value |
| `get_net_worth(start, end)` | `NetWorthResult` | Daily net worth + change summary |
| `get_account_balances(start, end)` | `list[AccountBalance]` | Daily account balances |
| `get_performance(start, end, account_ids)` | `PerformanceResult` | Investment + benchmark performance + per-account summaries |
| `get_quotes(start, end)` | `QuotesResult` | Portfolio vs benchmark + snapshot + market quotes |

Date parameters are `datetime.date`. Financial values are `decimal.Decimal`. All models are frozen dataclasses — see [Model Reference](docs/models.md) for every field and type.

### Response containers

Methods return container objects instead of bare lists:

```python
result = client.get_accounts()
result.accounts     # tuple[Account, ...]
result.summary      # AccountsSummary (networth, assets, liabilities, ...)

result = client.get_transactions(date(2026, 1, 1), date(2026, 3, 31))
result.transactions # tuple[Transaction, ...]
result.categories   # tuple[Category, ...]
result.summary      # TransactionsSummary (money_in, money_out, ...)

result = client.get_holdings()
result.holdings     # tuple[Holding, ...]
result.total_value  # Decimal

result = client.get_net_worth(date(2025, 1, 1), date(2026, 3, 31))
result.entries      # tuple[NetWorthEntry, ...]
result.summary      # NetWorthSummary (date_range_change, ...)

result = client.get_performance(start, end, account_ids)
result.investments       # tuple[InvestmentPerformance, ...]
result.benchmarks        # tuple[BenchmarkPerformance, ...]
result.account_summaries # tuple[AccountPerformanceSummary, ...]

result = client.get_quotes(start, end)
result.portfolio_vs_benchmark  # tuple[PortfolioVsBenchmark, ...]
result.snapshot                # PortfolioSnapshot
result.market_quotes           # tuple[MarketQuote, ...]
```

## More examples

```python
# Net worth over time
result = client.get_net_worth(date(2025, 1, 1), date(2026, 3, 31))
for nw in result.entries:
    print(f"{nw.date}  assets={nw.total_assets:.0f}  liabilities={nw.total_liabilities:.0f}")
print(f"Total change: ${result.summary.date_range_change:.2f}")

# Investment performance (requires explicit account IDs — no hidden API calls)
accounts = client.get_accounts().accounts
inv_ids = [a.user_account_id for a in accounts if a.product_type == "INVESTMENT"]
result = client.get_performance(date(2025, 1, 1), date(2026, 3, 31), inv_ids)
for s in result.account_summaries:
    print(f"{s.account_name}: ${s.current_balance:.0f} ({s.date_range_balance_percentage_change:.1f}%)")

# Current holdings
result = client.get_holdings()
for h in result.holdings:
    print(f"{h.ticker or h.description:<10}  {h.quantity:.2f} × ${h.price:.2f} = ${h.value:.2f}")
print(f"Total: ${result.total_value:.2f}")
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
