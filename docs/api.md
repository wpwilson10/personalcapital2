# Python API

## Methods

Each method makes a single HTTP request and returns a response container with typed data and summary information.

| Method | Returns | Description |
|---|---|---|
| `get_accounts()` | `AccountsResult` | Linked accounts + aggregate summary |
| `get_transactions(start, end)` | `TransactionsResult` | Transactions + categories + cashflow summary |
| `get_holdings()` | `HoldingsResult` | Investment holdings + total value |
| `get_net_worth(start, end)` | `NetWorthResult` | Daily net worth + change summary |
| `get_account_balances(start, end)` | `AccountBalancesResult` | Daily account balances |
| `get_performance(start, end, account_ids)` | `PerformanceResult` | Investment + benchmark performance + per-account summaries |
| `get_quotes(start, end)` | `QuotesResult` | Portfolio vs benchmark + snapshot + market quotes |
| `get_spending(start, end, interval)` | `SpendingResult` | Current spending (all intervals, see note below) |

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
# Use get_holdings for account IDs — get_accounts may not list all investment accounts
holdings = client.get_holdings().holdings
inv_ids = list({h.user_account_id for h in holdings if h.value > 0})
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

## Stale-session recovery: `run_authenticated`

`run_authenticated(operation, session_path)` wraps any `EmpowerClient` call so stale cached cookies trigger a one-shot re-authentication and retry instead of an unrecoverable failure. The `pc2` CLI uses this for every data command — library callers can use it the same way.

```python
from datetime import date
from personalcapital2 import run_authenticated

# If the cached session is stale, authenticate() runs once and the operation
# is retried. A second failure propagates.
result = run_authenticated(lambda c: c.get_accounts())

result = run_authenticated(
    lambda c: c.get_net_worth(date(2026, 1, 1), date(2026, 3, 31)),
)
```

The operation **must be idempotent** — it can run twice on the recovery path. All `EmpowerClient.get_*` methods are read-only and safe to retry.

If `EMPOWER_EMAIL`/`EMPOWER_PASSWORD` aren't set, recovery prompts for credentials interactively. Set them to avoid mid-command prompts in scripts. In non-TTY environments, recovery raises `InteractiveAuthRequired` instead of hanging.

## Headless library use

`authenticate()` is a TTY-friendly convenience wrapper. Library callers wanting full control over credential sourcing and 2FA pickup — for example, an agent that retrieves the verification code from an SMS provider or IMAP inbox — can skip `authenticate()` and call the lower-level `EmpowerClient` methods directly.

```python
from pathlib import Path
from personalcapital2 import EmpowerClient, TwoFactorMode, TwoFactorRequiredError

client = EmpowerClient(session_path=Path("session.json"))
try:
    client.login(email, password)
except TwoFactorRequiredError:
    client.send_2fa_challenge(TwoFactorMode.SMS)
    code = fetch_code_from_my_sms_provider()  # caller's responsibility
    client.verify_2fa_and_login(TwoFactorMode.SMS, code, password)
client.save_session()
```

The three-step pattern — `login` → `send_2fa_challenge` → `verify_2fa_and_login` — mirrors what `authenticate()` does internally. Use it when you need to source the code from somewhere other than stdin.

## Exceptions

All exceptions are exported from the package root.

| Exception | Raised when |
|---|---|
| `EmpowerAuthError` | Login failed (bad credentials, CSRF extraction failure), session is stale, or 2FA prompt couldn't complete. |
| `InteractiveAuthRequired` | Subclass of `EmpowerAuthError`. Authentication needs an interactive terminal but none is available (no TTY, env vars unset). Lets callers distinguish "no TTY" from "bad credentials" without parsing strings. |
| `TwoFactorRequiredError` | Subclass of `EmpowerAuthError`. The server requires 2FA before password auth can proceed. Used as a control-flow signal during the login flow; `run_authenticated` re-raises it without retry. |
| `EmpowerAPIError` | The HTTP request reached Empower and got a structured rejection (`spHeader.success = false`) or returned non-JSON. |
| `EmpowerNetworkError` | Transport-level failure reaching Empower (connection refused, timeout, DNS). Distinct from `EmpowerAuthError` (4xx auth) and `EmpowerAPIError` (server-side rejection). |

```python
from personalcapital2 import (
    EmpowerAPIError,
    EmpowerAuthError,
    EmpowerNetworkError,
    InteractiveAuthRequired,
    TwoFactorRequiredError,
    run_authenticated,
)

try:
    result = run_authenticated(lambda c: c.get_accounts())
except InteractiveAuthRequired:
    # Headless environment, no creds — surface a clear error to the caller
    ...
except EmpowerNetworkError:
    # Retry later, alert ops, etc.
    ...
except EmpowerAuthError:
    # Re-auth path also failed — bad creds or 2FA needed
    ...
```
