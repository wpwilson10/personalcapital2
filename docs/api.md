# Python API

## Methods

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
| `get_spending(start, end, interval)` | `SpendingResult` | Spending by interval (MONTH/WEEK/YEAR) |

Date parameters are `datetime.date`. Financial values are `decimal.Decimal`. All models are frozen dataclasses — see [Model Reference](models.md) for every field and type.

## Response containers

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

## Examples

```python
from datetime import date
from personalcapital2 import EmpowerClient, authenticate

client = authenticate()

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
