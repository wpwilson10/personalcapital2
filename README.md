# personalcapital2

Typed Python client for the Empower (formerly Personal Capital) API. Authenticate, fetch your financial data, and get back clean dataclasses.

> This library is unofficial and not affiliated with Empower. It uses their internal web API, which may change without notice.

Based on [haochi/personalcapital](https://github.com/haochi/personalcapital) and [traviscook21/personalcapital](https://github.com/traviscook21/personalcapital) (both MIT). Rewritten with type safety, structured error handling, and a typed model layer.

## Install

Not yet on PyPI — install directly from GitHub:

```bash
pip install git+https://github.com/wpwilson10/personalcapital2.git
# or with uv
uv add git+https://github.com/wpwilson10/personalcapital2.git
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

### Authentication

`authenticate()` reads credentials from environment variables, falling back to interactive prompts:

| Variable | Purpose |
|---|---|
| `EMPOWER_EMAIL` | Empower account email |
| `EMPOWER_PASSWORD` | Empower account password |

If neither is set, you'll be prompted interactively (2FA supported via SMS or email).

Sessions are saved to `~/.config/personalcapital2/session.json` and reused across calls until they expire. Empower sessions typically last 1-2 days before requiring re-authentication.

## CLI

A command-line interface is included as `pc2`. All output is structured JSON — data to stdout, errors to stderr — so it works equally well for humans and AI agents.

```bash
# Authenticate (interactive, supports 2FA)
pc2 login

# Fetch data (--start defaults to 30d, --end defaults to today)
pc2 accounts
pc2 transactions
pc2 holdings
pc2 transactions --start 90d
pc2 net-worth --start mb-12
pc2 balances --start 90d
pc2 categories --start mb
pc2 portfolio --start 365d
pc2 snapshot --start 365d
pc2 spending --start 90d --interval MONTH
pc2 performance --start 365d --account-ids 100,200
pc2 benchmarks --start 365d --account-ids 100,200

# Output as CSV (--format works before or after the subcommand)
pc2 --format csv transactions --start 30d
pc2 transactions --start 30d --format csv

# Raw API call
pc2 raw /newaccount/getAccounts2

# Session management (always JSON)
pc2 status          # {"session_path": "...", "exists": true, "age_seconds": 3600, "age_human": "1h"}
pc2 logout          # {"session_path": "...", "deleted": true}
```

### Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Authentication error (no session, expired, 2FA required) |
| 2 | Usage error (bad arguments, unknown command) |
| 3 | API error (request failed, rate limited) |
| 4 | Unexpected error |

### Structured errors

All errors are JSON to stderr with a consistent schema:

```json
{"error": "No session found. Run: pc2 login", "type": "EmpowerAuthError", "suggestion": "pc2 login"}
```

The `suggestion` field appears when a concrete recovery action is available (auth errors, invalid account IDs).

### Date shortcuts

| Shortcut | Meaning | Example |
|---|---|---|
| `today` | Current date | `2026-03-24` |
| `Nd` | N days ago | `30d` → 30 days ago |
| `mb` | Start of current month | `2026-03-01` |
| `mb-N` | Start of month, N months back | `mb-3` → 3 months ago |
| `me` | End of current month | `2026-03-31` |
| `me-N` | End of month, N months back | `me-1` → last month end |
| `yb` | Start of current year | `2026-01-01` |
| `yb-N` | Start of year, N years back | `yb-1` → last Jan 1 |
| `ye` | End of current year | `2026-12-31` |
| `ye-N` | End of year, N years back | `ye-1` → last Dec 31 |
| `YYYY-MM-DD` | Exact date | `2026-01-15` |

### Available endpoints for `pc2 raw`

The Empower API has 7 endpoints that return data:

| Endpoint | Description |
|---|---|
| `/newaccount/getAccounts2` | Accounts + summary totals |
| `/transaction/getUserTransactions` | Transactions + cashflow summary |
| `/invest/getHoldings` | Holdings + total value |
| `/account/getHistories` | Net worth + balances |
| `/account/getPerformanceHistories` | Performance + benchmarks |
| `/invest/getQuotes` | Portfolio vs benchmark + market quotes |
| `/account/getUserSpending` | Spending by interval |

Most endpoints require date parameters via `--data startDate=2026-01-01 --data endDate=2026-03-31`.

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
| `get_spending(start, end, interval)` | `SpendingResult` | Spending by interval (MONTH/WEEK/YEAR) |

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

## Known API quirks

- **`is_spending` is unreliable on refunds.** Refunds can have `is_spending=True` even though they're money coming in. Use `transaction_type` (e.g. `"Refund"`) instead.
- **`performance` and `benchmarks` share one API call.** The CLI commands `pc2 performance` and `pc2 benchmarks` both call the same endpoint (`getPerformanceHistories`) and show different slices of the result. In the Python API, `get_performance()` returns both in a single `PerformanceResult`.
- **Sessions expire.** Empower sessions typically last 1-2 days. If you get an auth error, run `pc2 login` again.

## Development

```bash
uv sync
uv run pytest
uv run pyright .
uv run ruff check .
```
