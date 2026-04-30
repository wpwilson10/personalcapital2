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
| `EMPOWER_2FA_MODE` | `sms` or `email` — skips the interactive 2FA-method prompt (read only when 2FA is required) |
| `PC2_SESSION_PATH` | Custom session file location (default: `~/.config/personalcapital2/session.json`) |

Credentials go to Empower over HTTPS only — never stored, logged, or transmitted elsewhere.

Sessions live ~24 hours. Set `EMPOWER_EMAIL` and `EMPOWER_PASSWORD` (and `EMPOWER_2FA_MODE` if 2FA may fire) so commands self-heal when a session expires; otherwise re-run `pc2 login`. Override the session path per-command with `--session`.

#### Headless authentication

For unattended invocation, pipe the verification code on stdin:

```bash
EMPOWER_EMAIL=... EMPOWER_PASSWORD=... EMPOWER_2FA_MODE=sms \
    printf '%s\n' "$CODE" | pc2 login
```

The orchestrator handles SMS/email pickup; `pc2` reads the code from stdin.

## CLI

The `pc2` command outputs structured JSON (data to stdout, errors to stderr) and follows an [agent-first design](https://dev.to/uenyioha/writing-cli-tools-that-ai-agents-actually-want-to-use-39no): every error has a machine-readable type and recovery suggestion, exit codes are meaningful, and the help text is self-documenting.

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
pip install "personalcapital2[mcp]"
pc2 login   # authenticate first
pc2 mcp     # start the server
```

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
        "EMPOWER_PASSWORD": "...",
        "EMPOWER_2FA_MODE": "sms"
      }
    }
  }
}
```

When the cached session expires mid-conversation, the agent recovers in chat without dropping to a terminal: it calls `start_authentication`, asks you for the 6-digit code, then calls `complete_authentication` with the code. The server reads the credentials and `EMPOWER_2FA_MODE` from this env block.

> Note: `EMPOWER_PASSWORD` sits plaintext in the MCP client config — standard pattern for MCP servers, but worth knowing.

The server is token-aware — large responses are automatically truncated to fit within context limits (~12,500 tokens by default, configurable via `PC2_MCP_MAX_CHARS`), while summaries are always preserved in full.

## Known API quirks

This library uses Empower's unofficial internal web API, which is not affiliated with Empower and may change without notice.

- **`is_spending` is unreliable on refunds.** Use `transaction_type` (e.g. `"Refund"`) instead.
- **`performance` and `benchmarks` share one API call.** `get_performance()` returns both in a single `PerformanceResult`.
- **`get_accounts` may not list all accounts with holdings.** Some accounts (employer 401k plans, crypto exchanges) can appear in `get_holdings`, `get_account_balances`, and `get_performance` but not in `get_accounts`. Use `get_holdings` to discover investment account IDs.
- **Fee fields can be `NaN`.** The API returns `"NaN"` for `fees_per_year`, `fund_fees`, `total_fee`, and `advisory_fee_percentage` on some investment accounts (401k plans, crypto, RSUs). These are coerced to `None` — the account is not dropped.
- **`get_spending` ignores date range and interval.** The API always returns current-period spending for all three interval types (MONTH, WEEK, YEAR), regardless of the `start_date`, `end_date`, or `interval` parameters.
- **Sessions expire.** Typically ~24 hours, sometimes sooner. CLI users run `pc2 login` again; MCP users let the agent call `start_authentication` / `complete_authentication`. Stale-session recovery handles this automatically when `EMPOWER_EMAIL`/`EMPOWER_PASSWORD` (and `EMPOWER_2FA_MODE` if needed) are set.
