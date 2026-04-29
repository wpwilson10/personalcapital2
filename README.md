# personalcapital2

[![CI](https://github.com/wpwilson10/personalcapital2/actions/workflows/ci.yml/badge.svg)](https://github.com/wpwilson10/personalcapital2/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/personalcapital2)](https://pypi.org/project/personalcapital2/)
[![Python](https://img.shields.io/pypi/pyversions/personalcapital2)](https://pypi.org/project/personalcapital2/)
[![License](https://img.shields.io/pypi/l/personalcapital2)](LICENSE)

Get your financial data out of Empower (formerly Personal Capital) and into your own tools. Track net worth over time, analyze spending, monitor investment performance, or let an AI agent answer questions about your finances.

Three interfaces, one library:
- **Python API** — frozen dataclasses with `Decimal` precision, not raw JSON
- **CLI** (`pc2`) — structured JSON to stdout, pipe to `jq`, scripts, or spreadsheets
- **MCP server** — give Claude or other AI agents direct access to your financial data

Built on the reverse-engineering work of [haochi/personalcapital](https://github.com/haochi/personalcapital) and [traviscook21/personalcapital](https://github.com/traviscook21/personalcapital) (both MIT).

## Install

```bash
pip install personalcapital2
# or with uv
uv add personalcapital2
```

## Quick start

```python
from datetime import date
from personalcapital2 import authenticate

client = authenticate()  # interactive login with 2FA

result = client.get_accounts()
for acct in result.accounts:
    print(f"{acct.name:<30} ${acct.balance}")
print(f"Net worth: ${result.summary.networth:,.2f}")

result = client.get_transactions(date(2026, 1, 1), date(2026, 3, 31))
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
| `PC2_SESSION_PATH` | Custom session file location (default: `~/.config/personalcapital2/session.json`) |

Credentials are sent directly to Empower's servers over HTTPS — this library never stores, logs, or transmits them anywhere else. Sessions are saved and reused until they expire — typically within ~24 hours, sometimes sooner. The session path can also be overridden per-command with `--session`.

## CLI

The `pc2` command outputs structured JSON (data to stdout, errors to stderr). Designed for scripting and AI agents — every error includes a machine-readable type and recovery suggestion.

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

All methods return frozen dataclasses with `datetime.date` and `decimal.Decimal` fields. See [API Reference](docs/api.md) for methods, response containers, and examples, and [Model Reference](docs/models.md) for every field and type.

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
      "env": {"PC2_SESSION_PATH": "~/.config/personalcapital2/session.json"}
    }
  }
}
```

The server is token-aware — large responses are automatically truncated to fit within context limits (~12,500 tokens by default, configurable via `PC2_MCP_MAX_CHARS`), while summaries are always preserved in full.

The CLI and MCP server follow an [agent-first design](https://dev.to/uenyioha/writing-cli-tools-that-ai-agents-actually-want-to-use-39no): structured JSON errors with recovery suggestions, meaningful exit codes, self-documenting help text, and non-interactive TTY detection.

CLI exit codes:

| Code | Meaning |
| ---- | ------- |
| `0` | success |
| `1` | authentication error (no session, expired, 2FA required) |
| `2` | usage error (bad arguments, unknown command) |
| `3` | API error (request failed, rate limited, HTTP 4xx/5xx from Empower) |
| `4` | unexpected error |
| `5` | network error (transport-level failure reaching Empower) |

### Session recovery

Stale cached sessions are handled automatically: if a data command finds the saved session expired, the CLI re-authenticates and retries the request once. Set `EMPOWER_EMAIL` and `EMPOWER_PASSWORD` to avoid a mid-command password prompt during recovery. Headless 2FA is not yet supported (tracked in [#5](https://github.com/wpwilson10/personalcapital2/issues/5)) — non-TTY environments will fail fast with a structured `EmpowerAuthError` rather than hanging on the prompt.

## Known API quirks

This library uses Empower's unofficial internal web API, which is not affiliated with Empower and may change without notice.

- **`is_spending` is unreliable on refunds.** Use `transaction_type` (e.g. `"Refund"`) instead.
- **`performance` and `benchmarks` share one API call.** `get_performance()` returns both in a single `PerformanceResult`.
- **`get_accounts` may not list all accounts with holdings.** Some accounts (employer 401k plans, crypto exchanges) can appear in `get_holdings`, `get_account_balances`, and `get_performance` but not in `get_accounts`. Use `get_holdings` to discover investment account IDs.
- **Fee fields can be `NaN`.** The API returns `"NaN"` for `fees_per_year`, `fund_fees`, `total_fee`, and `advisory_fee_percentage` on some investment accounts (401k plans, crypto, RSUs). These are coerced to `None` — the account is not dropped.
- **`get_spending` ignores date range and interval.** The API always returns current-period spending for all three interval types (MONTH, WEEK, YEAR), regardless of the `start_date`, `end_date`, or `interval` parameters.
- **Sessions expire.** Typically 1-2 days. Run `pc2 login` again on auth errors.
