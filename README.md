# personalcapital2

[![CI](https://github.com/wpwilson10/personalcapital2/actions/workflows/ci.yml/badge.svg)](https://github.com/wpwilson10/personalcapital2/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/personalcapital2)](https://pypi.org/project/personalcapital2/)
[![Python](https://img.shields.io/pypi/pyversions/personalcapital2)](https://pypi.org/project/personalcapital2/)
[![License](https://img.shields.io/pypi/l/personalcapital2)](LICENSE)

Get your financial data out of Empower (formerly Personal Capital) and into your own tools. Track net worth over time, analyze spending, monitor investment performance, or let an AI agent answer questions about your finances.

Three interfaces, one library:
- **Python API** — frozen dataclasses with `Decimal` precision, not raw JSON
- **CLI** (`pc2`) — structured JSON to stdout, pipe to `jq`, scripts, or spreadsheets
- **MCP server** — drop into Claude Desktop, ask *"how much did I spend on dining last quarter?"*

Built on the reverse-engineering work of [haochi/personalcapital](https://github.com/haochi/personalcapital) and [traviscook21/personalcapital](https://github.com/traviscook21/personalcapital) (both MIT). Adds typed dataclasses, an agent-first CLI, and an MCP server on top.

## Install

```bash
pip install personalcapital2
# or with uv
uv add personalcapital2
```

## Quick start

```python
from datetime import date, timedelta
from personalcapital2 import authenticate

client = authenticate()  # interactive login with 2FA

result = client.get_accounts()
for acct in result.accounts:
    print(f"{acct.name:<30} ${acct.balance}")
print(f"Net worth: ${result.summary.networth:,.2f}")

result = client.get_transactions(date.today() - timedelta(days=90), date.today())
for txn in result.transactions:
    print(f"{txn.date}  {txn.description:<30}  ${txn.amount:.2f}")
print(f"Net cashflow: ${result.summary.net_cashflow:,.2f}")
```

### Authentication

`authenticate()` reads credentials from environment variables, falling back to interactive prompts:

| Variable | Purpose |
|---|---|
| `EMPOWER_EMAIL` | Empower account email |
| `EMPOWER_PASSWORD` | Empower account password |
| `EMPOWER_2FA_MODE` | `sms` (the only method Empower still offers) — optional; 2FA defaults to SMS |
| `PC2_SESSION_PATH` | Custom session file location (default: `~/.config/personalcapital2/session.json`) |

Credentials go to Empower over HTTPS only — never stored, logged, or transmitted elsewhere.

> **Note:** Empower removed email 2FA — verification codes are sent by SMS only. `EMPOWER_2FA_MODE` is kept for compatibility but now only accepts `sms`; a stale `email` value raises a clear error pointing you to SMS.

Sessions live ~24 hours. With `EMPOWER_EMAIL` and `EMPOWER_PASSWORD` set, a command whose session has expired signs in again on its own, as long as Empower doesn't ask for a new SMS code. When it does, the command prompts for the code in a terminal. Without a terminal, it fails before any code is sent, and you run `pc2 login`. Override the session path per-command with `--session`.

#### Headless authentication

Without a terminal, `pc2 login` takes the email and password from `EMPOWER_EMAIL`/`EMPOWER_PASSWORD` and reads only the SMS code from stdin. The code doesn't exist until `pc2 login` has asked Empower to send it, so start the command with stdin as a pipe and write the code once it arrives:

```python
import subprocess

# EMPOWER_EMAIL and EMPOWER_PASSWORD are set in the environment.
login = subprocess.Popen(["pc2", "login"], stdin=subprocess.PIPE, text=True)
code = wait_for_sms_code()  # your SMS pickup
login.communicate(code + "\n")
```

Data commands never read stdin. Without a terminal, one that needs a new login fails at once with an `EmpowerAuthError` instead of prompting, and sends no SMS.

## CLI

The `pc2` command outputs structured JSON (data to stdout, errors to stderr) and follows an [agent-first design](https://dev.to/uenyioha/writing-cli-tools-that-ai-agents-actually-want-to-use-39no): every error has a machine-readable type and recovery suggestion, exit codes are meaningful, and the help text is self-documenting.

JSON output is the API call's full result, the same shape the Python API and MCP tools return, summaries included:

```bash
pc2 accounts | jq '.summary.networth'       # {"accounts": [...], "summary": {...}}
pc2 transactions --start 90d | jq '.transactions[] | select(.category_name == "Groceries")'
```

`--format csv` prints the command's table (for example, just the accounts rows).

```bash
pc2 accounts                                # all linked accounts
pc2 transactions --start 90d                # last 90 days of transactions
pc2 holdings                                # current investment positions
pc2 net-worth --start yb --format csv       # YTD net worth as CSV
pc2 performance --start mb-6 --account-ids 123,456
pc2 spending                                # current month/week/year spending
```

Date shortcuts: `30d` (days ago), `mb` / `me` (month begin/end), `yb` / `ye` (year begin/end), `mb-3` (3 months ago). See [CLI Reference](docs/cli.md) for the full list.

## Python API

Methods return response containers with typed dataclass fields and a pre-computed summary, not bare lists:

```python
result = client.get_accounts()
result.accounts     # tuple[Account, ...]
result.summary      # AccountsSummary — networth, assets, liabilities, ...

result = client.get_transactions(start, end)
result.transactions # tuple[Transaction, ...]
result.categories   # tuple[Category, ...]
result.summary      # TransactionsSummary — money_in, money_out, net_cashflow, ...
```

All fields use `datetime.date` and `decimal.Decimal`. See the [API Reference](docs/api.md) for the full method list and the [Model Reference](docs/models.md) for every field and type.

## MCP Server

An MCP tool server gives AI agents (Claude Code, Claude Desktop, etc.) direct access to your financial data. The agent can call tools like `get_transactions` or `get_holdings` and reason over the results.

```bash
uv tool install "personalcapital2[mcp]"   # or: pip install "personalcapital2[mcp]"
pc2 login   # authenticate first
pc2 mcp     # start the server
```

The `[mcp]` extra needs `mcp>=2.1`. When upgrading from 0.4.x, upgrade the extra too: `uv tool upgrade personalcapital2` or `pip install -U "personalcapital2[mcp]"`.

Client config (Claude Code / Claude Desktop):

```json
{
  "mcpServers": {
    "empower": {
      "type": "stdio",
      "command": "pc2",
      "args": ["mcp"],
      "env": {
        "PC2_SESSION_PATH": "~/.config/personalcapital2/session.json",
        "EMPOWER_EMAIL": "you@example.com",
        "EMPOWER_PASSWORD": "..."
      }
    }
  }
}
```

When the cached session expires mid-conversation, the agent recovers in chat without dropping to a terminal: it calls `start_authentication`, asks you for the SMS verification code, then calls `complete_authentication` with the code. The server reads the credentials from this env block.

> Note: `EMPOWER_PASSWORD` sits plaintext in the MCP client config — standard pattern for MCP servers, but worth knowing.

The server is token-aware. Responses are compact JSON capped at ~12,500 tokens (configurable via `PC2_MCP_MAX_CHARS`), and summaries are always complete. When a date-based list (transactions, net worth, balances, performance, portfolio vs benchmark) doesn't fit, the newest whole days are kept and `truncated.next_end_date` tells the agent where to page back from. Tool errors come back with `isError: true`.

## Known API quirks

This library uses Empower's unofficial internal web API, which is not affiliated with Empower and may change without notice.

- **`is_spending` is unreliable on refunds.** Use `transaction_type` (e.g. `"Refund"`) instead.
- **`performance` and `benchmarks` share one API call.** `get_performance()` returns both in a single `PerformanceResult`.
- **`get_accounts` may not list all accounts with holdings.** Some accounts (employer 401k plans, crypto exchanges) can appear in `get_holdings`, `get_account_balances`, and `get_performance` but not in `get_accounts`. Use `get_holdings` to discover investment account IDs.
- **Fee fields can be `NaN`.** The API returns `"NaN"` for `fees_per_year`, `fund_fees`, `total_fee`, and `advisory_fee_percentage` on some investment accounts (401k plans, crypto, RSUs). These are coerced to `None` — the account is not dropped.
- **Benchmarks are Empower's blended indexes.** `benchmarks` in `get_performance` are `^PC_US_STOCKS`, `^PC_US_BONDS`, `^PC_INTL_STOCKS`, `^PC_INTL_BONDS`, `^PC_ALTERNATIVES` and `^PC_BLENDED`, not the S&P 500. The S&P 500 is in `get_quotes`.
- **`portfolio_vs_benchmark` values are percentages.** `portfolio_value` and `sp500_value` come from the API's `YOU` and `^INX` series: cumulative percent change since the first day of the range, not dollar values.
- **Histories start with a baseline row.** Performance and quotes histories begin on the trading day before `start_date` (or the first available date) with a value of 0.
- **Unknown account IDs aren't an error.** `get_performance` with IDs Empower doesn't recognize returns empty `investments` and `account_summaries`; benchmarks still come back. An empty list returns every investment account.
- **Row order isn't guaranteed.** Transactions came back newest-first in 2026-03 and oldest-first on 2026-11-21 with the same request (the client asks for newest-first; Empower doesn't reliably honor it). Sort by `date` if order matters.
- **`get_spending` ignores date range and interval.** The API always returns current-period spending for all three interval types (MONTH, WEEK, YEAR), regardless of the `start_date`, `end_date`, or `interval` parameters.
- **Only email-address logins are supported.** Accounts that sign in with a username get `LoginRejectedError` with Empower's code (113 or 207). Those accounts go through Empower's newer login, which this library doesn't support yet ([#9](https://github.com/wpwilson10/personalcapital2/issues/9)).
- **Sessions expire.** Typically ~24 hours, sometimes sooner. CLI users run `pc2 login` again; MCP users let the agent call `start_authentication` / `complete_authentication`. Stale-session recovery handles this automatically when `EMPOWER_EMAIL`/`EMPOWER_PASSWORD` are set and Empower doesn't ask for a new SMS code. `pc2 status` only reads the session file: `"exists": true` doesn't mean Empower still accepts the session.
