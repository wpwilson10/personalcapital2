# CLI Reference

The `pc2` command-line tool outputs structured JSON (data to stdout, errors to stderr), making it usable by both humans and AI agents. Run `pc2 --help` for full usage.

## Commands

```bash
# Authenticate (interactive, supports 2FA)
pc2 login

# Session management
pc2 status          # {"session_path": "...", "exists": true, "age_seconds": 3600, "age_human": "1h"}
pc2 logout          # {"session_path": "...", "deleted": true}

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
```

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Authentication error (no session, expired, 2FA required) |
| 2 | Usage error (bad arguments, unknown command) |
| 3 | API error (request failed, rate limited) |
| 4 | Unexpected error |

## Structured errors

All errors are JSON to stderr with a consistent schema:

```json
{"error": "No session found. Run: pc2 login", "type": "EmpowerAuthError", "suggestion": "pc2 login"}
```

The `suggestion` field appears when a concrete recovery action is available (auth errors, invalid account IDs).

## Date shortcuts

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

## Available endpoints for `pc2 raw`

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
