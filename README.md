# personalcapital2

[![PyPI](https://img.shields.io/pypi/v/personalcapital2)](https://pypi.org/project/personalcapital2/)
[![Python](https://img.shields.io/pypi/pyversions/personalcapital2)](https://pypi.org/project/personalcapital2/)
[![License](https://img.shields.io/pypi/l/personalcapital2)](LICENSE)

Typed Python client for the Empower (formerly Personal Capital) API. Authenticate, fetch your financial data, and get back clean dataclasses — frozen dataclasses with `Decimal` values, not raw JSON.

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

A command-line tool is included as `pc2`. All output is structured JSON. See [CLI Reference](docs/cli.md) for commands, date shortcuts, and examples.

```bash
pc2 accounts                                # list linked accounts
pc2 transactions --start 90d                # last 90 days
pc2 net-worth --start yb --format csv       # YTD as CSV
```

## Python API

All methods return frozen dataclasses with `datetime.date` and `decimal.Decimal` fields. See [API Reference](docs/api.md) for methods, response containers, and examples, and [Model Reference](docs/models.md) for every field and type.

## MCP Server

An MCP tool server exposes all data methods to AI agents (Claude Code, Claude Desktop, etc.). Requires the `[mcp]` extra:

```bash
pip install "personalcapital2[mcp]"
```

Start the server (requires a valid session from `pc2 login`):

```bash
pc2 mcp
```

See [MCP Testing Guide](docs/mcp-testing.md) for client configuration and testing.

## Known API quirks

This library uses Empower's unofficial internal web API, which is not affiliated with Empower and may change without notice.

- **`is_spending` is unreliable on refunds.** Use `transaction_type` (e.g. `"Refund"`) instead.
- **`performance` and `benchmarks` share one API call.** `get_performance()` returns both in a single `PerformanceResult`.
- **`get_accounts` may not list all accounts with holdings.** Some accounts (employer 401k plans, crypto exchanges) can appear in `get_holdings`, `get_account_balances`, and `get_performance` but not in `get_accounts`. Use `get_holdings` to discover investment account IDs.
- **Fee fields can be `NaN`.** The API returns `"NaN"` for `fees_per_year`, `fund_fees`, `total_fee`, and `advisory_fee_percentage` on some investment accounts (401k plans, crypto, RSUs). These are coerced to `None` — the account is not dropped.
- **`get_spending` ignores date range and interval.** The API always returns current-period spending for all three interval types (MONTH, WEEK, YEAR), regardless of the `start_date`, `end_date`, or `interval` parameters.
- **Sessions expire.** Typically 1-2 days. Run `pc2 login` again on auth errors.
