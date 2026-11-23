# CLI Reference

The `pc2` command-line tool outputs structured JSON (data to stdout, errors to stderr), making it usable by both humans and AI agents. Run `pc2 --help` for full usage.

## Commands

```bash
# Authenticate (interactive, supports 2FA)
pc2 login

# Session management
pc2 status          # {"session_path": "...", "exists": true, "age_seconds": 3600, "age_human": "1h"}
                    # reads only the file: "exists" doesn't mean Empower still accepts it
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
pc2 performance --start 365d                  # every investment account
pc2 performance --start 365d --account-ids 100,200
pc2 benchmarks --start 365d --account-ids 100,200

# Output as CSV (--format works before or after the subcommand)
pc2 --format csv transactions --start 30d
pc2 transactions --start 30d --format csv

# Raw API call
pc2 raw /newaccount/getAccounts2

# Start the MCP tool server (requires the [mcp] extra)
pc2 mcp
```

## Output

With `--format json` (the default), every data command prints the full result of its API call: the same container the Python API and MCP tools return, summaries included.

```bash
pc2 accounts      # {"accounts": [...], "summary": {"networth": ..., ...}}
pc2 holdings      # {"holdings": [...], "total_value": ...}
pc2 performance --account-ids 100,200
                  # {"investments": [...], "benchmarks": [...], "account_summaries": [...]}
```

Commands that share an API call print the same JSON and differ only in their CSV table:

| Command | JSON keys | CSV table |
|---|---|---|
| `accounts` | `accounts`, `summary` | accounts |
| `transactions`, `categories` | `transactions`, `categories`, `summary` | transactions / categories |
| `holdings` | `holdings`, `total_value` | holdings |
| `net-worth` | `entries`, `summary` | entries |
| `balances` | `balances`, `summary` | balances |
| `spending` | `intervals` | intervals |
| `performance`, `benchmarks` | `investments`, `benchmarks`, `account_summaries` | investments / benchmarks |
| `portfolio`, `snapshot` | `portfolio_vs_benchmark`, `snapshot`, `market_quotes` | portfolio_vs_benchmark / market_quotes |

So `pc2 categories --start 365d` prints a year of transactions too; use `jq '.categories'` for just the list. `raw`, `status`, `login` and `logout` print their own objects.

## Environment variables

| Variable | Purpose |
|---|---|
| `EMPOWER_EMAIL` | Empower account email (skips the email prompt) |
| `EMPOWER_PASSWORD` | Empower account password (skips the password prompt). Setting both `EMPOWER_EMAIL` and `EMPOWER_PASSWORD` lets stale-session recovery run without prompting mid-command, unless Empower asks for a new SMS code. |
| `EMPOWER_2FA_MODE` | `sms` (case-insensitive) — the only method Empower still offers. Optional: 2FA defaults to SMS when unset. Empower removed email 2FA, so a stale `email` value raises a clear `EmpowerAuthError` pointing to SMS; any other value also raises `EmpowerAuthError`. Read lazily — only consulted when the server actually requires 2FA, so a leftover value doesn't break flows where the device is remembered. |
| `PC2_SESSION_PATH` | Override the default session file path (default: `~/.config/personalcapital2/session.json`). Per-command override: `--session PATH`. |
| `PC2_MCP_MAX_CHARS` | MCP-server-only. Soft cap on tool response size in characters (default: 50,000 ≈ 12,500 tokens). Date-based lists keep the newest whole days, other lists their first rows, and `truncated` reports what was cut plus `next_end_date` for paging back. The newest day is always returned whole, even if it alone exceeds the cap. |

## Stale-session recovery

If the cached session is rejected by Empower mid-command, `pc2` re-authenticates and retries the request once. Set `EMPOWER_EMAIL` and `EMPOWER_PASSWORD` to avoid a mid-command credential prompt during recovery.

Data commands read stdin only when it's a terminal. Without one, a command that needs a new login (no session, an expired one, or an SMS code to enter) fails at once with exit 1, before any SMS is sent. It never blocks on a pipe and never texts a code no one can enter. With the credentials set and a device Empower remembers, recovery still runs without a terminal. A harness that runs commands in a pseudo-terminal counts as a terminal, so there `pc2` prompts as it would for a person.

### Headless login

Without a terminal, `pc2 login` takes the email and password from `EMPOWER_EMAIL`/`EMPOWER_PASSWORD` (it fails at once if either is missing) and reads only the SMS code from stdin. The code exists only after `pc2 login` has asked Empower to send it, so the orchestrator starts `pc2 login` with stdin as a pipe, waits for the SMS, then writes the code and a newline:

```python
import subprocess

# EMPOWER_EMAIL and EMPOWER_PASSWORD are set in the environment.
login = subprocess.Popen(["pc2", "login"], stdin=subprocess.PIPE, text=True)
code = wait_for_sms_code()  # your SMS pickup
login.communicate(code + "\n")
```

If Empower remembers the device, `pc2 login` exits without sending a code.

If stdin closes before a code arrives, `pc2 login` fails with `EmpowerAuthError`. An agent with no way to read the SMS shouldn't run `pc2 login` itself: it should ask the user to run it in a terminal.

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Authentication error (no session, expired, 2FA required) |
| 2 | Usage error (bad arguments, unknown command) |
| 3 | API error (request failed, rate limited, HTTP 4xx/5xx from Empower) |
| 4 | Unexpected error |
| 5 | Network error (transport-level failure reaching Empower) |
| 141 | stdout closed early by the reader (e.g. `pc2 transactions \| head`); nothing is written to stderr |

## Structured errors

All errors are JSON on the last line of stderr with a consistent schema. For example, a data command with no session, no terminal and no `EMPOWER_EMAIL`/`EMPOWER_PASSWORD` prints:

```json
{"error": "No saved session at /home/you/.config/personalcapital2/session.json. Login requires an interactive terminal or EMPOWER_EMAIL/EMPOWER_PASSWORD env vars.", "type": "EmpowerAuthError", "suggestion": "Ask the user to run `pc2 login` in a terminal, then retry."}
```

When a data command needs a login it can't do, `error` starts with what was wrong with the session: `No saved session at ...`, `The saved session at ... has expired.` or `The saved session at ... is unusable.` Then it says why it couldn't sign in, for example `Empower requires an SMS verification code, which needs an interactive terminal. No code was sent.` Every `EmpowerAuthError` suggests the user run `pc2 login` in a terminal; when the session file isn't the default, the suggested command includes `--session <path>`, so the login writes the file the retry reads.

Earlier stderr lines can hold log warnings or a login prompt, so parse the last line.

The `suggestion` field appears when a concrete recovery action is available (auth errors, a malformed `--account-ids`). Account IDs Empower doesn't recognize aren't an error: `performance` and `benchmarks` return empty `investments` and `account_summaries` (benchmarks still come back). Find investment account IDs with `pc2 holdings`.

`"type": "LoginRejectedError"` (exit 1) means Empower rejected the sign-in (the username or the password): `error` starts with Empower's own codes and messages, and there is no `suggestion`, because logging in again with the same credentials fails the same way. Accounts that sign in with a username rather than an email address get code 113 or 207 and aren't supported yet.

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
