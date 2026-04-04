# personalcapital2

Typed Python client for the Empower (formerly Personal Capital) API. Authenticate, fetch your financial data, and get back clean dataclasses. Based on [haochi/personalcapital](https://github.com/haochi/personalcapital) and [traviscook21/personalcapital](https://github.com/traviscook21/personalcapital) (both MIT), rewritten with type safety, structured error handling, and a typed model layer.

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
| `PC2_SESSION_PATH` | Custom session file location (default: `~/.config/personalcapital2/session.json`) |

Sessions are saved and reused until they expire (typically 1-2 days). The session path can also be overridden per-command with `--session`.

## CLI

A command-line tool is included as `pc2`. All output is structured JSON — data to stdout, errors to stderr. Run `pc2 --help` for full usage.

```bash
pc2 login                                   # authenticate (interactive 2FA)
pc2 accounts                                # list linked accounts
pc2 transactions --start 90d                # last 90 days
pc2 net-worth --start yb --format csv       # YTD net worth as CSV
pc2 performance --start mb-6 --account-ids 123,456
```

See [CLI Reference](docs/cli.md) for all commands, date shortcuts, exit codes, and error format.

## Python API

| Method | Returns | Description |
|---|---|---|
| `get_accounts()` | `AccountsResult` | Linked accounts + aggregate summary |
| `get_transactions(start, end)` | `TransactionsResult` | Transactions + categories + cashflow summary |
| `get_holdings()` | `HoldingsResult` | Investment holdings + total value |
| `get_net_worth(start, end)` | `NetWorthResult` | Daily net worth + change summary |
| `get_account_balances(start, end)` | `AccountBalancesResult` | Daily account balances |
| `get_performance(start, end, account_ids)` | `PerformanceResult` | Investment + benchmark performance |
| `get_quotes(start, end)` | `QuotesResult` | Portfolio vs benchmark + market quotes |
| `get_spending(start, end, interval)` | `SpendingResult` | Current spending (all intervals, see quirks) |

All dates are `datetime.date`, financial values are `decimal.Decimal`, models are frozen dataclasses. See [Python API docs](docs/api.md) for response containers and examples, [Model Reference](docs/models.md) for every field and type.

## MCP Server

An MCP tool server exposes all data methods to AI agents (Claude Code, Claude Desktop, etc.) over stdio. Requires the `[mcp]` extra:

```bash
pip install "personalcapital2[mcp]"
```

Start the server (requires a valid session from `pc2 login`):

```bash
pc2 mcp
```

### Client configuration

Add to your MCP client config (Claude Code `settings.json`, Claude Desktop `claude_desktop_config.json`, etc.):

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

All 8 data tools are available: `get_accounts`, `get_transactions`, `get_holdings`, `get_net_worth`, `get_account_balances`, `get_performance`, `get_quotes`, `get_spending`. Tools return JSON strings and handle errors gracefully — expired sessions return a message telling the agent to ask the user to re-run `pc2 login`.

See [MCP Testing Guide](docs/mcp-testing.md) for how to test the server during development.

## Known API quirks

This library uses Empower's unofficial internal web API, which is not affiliated with Empower and may change without notice.

- **`is_spending` is unreliable on refunds.** Use `transaction_type` (e.g. `"Refund"`) instead.
- **`performance` and `benchmarks` share one API call.** `get_performance()` returns both in a single `PerformanceResult`.
- **`get_accounts` may not list all accounts with holdings.** Some accounts (employer 401k plans, crypto exchanges) can appear in `get_holdings`, `get_account_balances`, and `get_performance` but not in `get_accounts`. Use `get_holdings` to discover investment account IDs.
- **`get_spending` ignores date range and interval.** The API always returns current-period spending for all three interval types (MONTH, WEEK, YEAR), regardless of the `start_date`, `end_date`, or `interval` parameters.
- **Sessions expire.** Typically 1-2 days. Run `pc2 login` again on auth errors.

## Development

```bash
uv sync
uv run pytest
uv run pyright .
uv run ruff check .
```
