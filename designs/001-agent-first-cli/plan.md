# Agent-First CLI Design — Plan

## What we're building

Updates to `pc2` CLI so AI agents (Claude Code, etc.) can use it reliably without
human-oriented workarounds. The CLI's foundation is solid — JSON default output,
data/error stream separation, typed exit codes. The gaps are in consistency:
auth commands break the structured output contract, argparse errors bypass our
error handler, and help text doesn't give agents enough to work with.

## Requirements

1. Every command produces structured (JSON) output to stdout — no plain text
2. Every error produces structured JSON to stderr with a consistent schema
3. Exit codes are documented and meaningful
4. Help text includes examples and describes output shape
5. Interactive commands fail fast in non-interactive contexts
6. Global flags (`--format`, `--session`) work in any position (before or after subcommand)
7. Changes are backward-compatible for human users (JSON is already the default)

## Approach

### 1. Structured argparse errors

Override `ArgumentParser.error()` to write JSON to stderr instead of argparse's
default plain-text format.

```python
class AgentArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        err = {"error": message, "type": "UsageError"}
        sys.stderr.write(json.dumps(err) + "\n")
        sys.exit(EXIT_USAGE)
```

Replace `argparse.ArgumentParser` with `AgentArgumentParser` in `build_parser()`.
Subparsers inherit the class, so this covers all commands.

**Acceptance:** `pc2 transactions --start bad-date` writes JSON to stderr, exits 2,
writes nothing to stdout.

### 2. Auth commands output structured JSON

Replace `print()` calls in `cmd_login`, `cmd_logout`, `cmd_status` with structured
JSON output to stdout.

**`status`** output:
```json
{"session_path": "/path/to/session.json", "exists": true, "age_seconds": 10800, "age_human": "3h"}
```
```json
{"session_path": "/path/to/session.json", "exists": false}
```

**`login`** output:
```json
{"session_path": "/path/to/session.json", "authenticated": true}
```

**`logout`** output:
```json
{"session_path": "/path/to/session.json", "deleted": true}
```
```json
{"session_path": "/path/to/session.json", "deleted": false}
```

These commands ignore `--format` since they aren't tabular data — always JSON.

**Acceptance:** `pc2 status | jq .exists` returns `true` or `false`.

### 3. TTY detection for `login`

Check `sys.stdin.isatty()` at the start of `cmd_login`. If not a TTY, exit
immediately with a structured error:

```json
{"error": "Login requires interactive terminal for 2FA. Run from a shell.", "type": "EmpowerAuthError"}
```

Exit code: 1 (auth).

**Acceptance:** `echo "" | pc2 login` fails immediately with JSON error, exit 1.

### 4. Help text with examples and exit codes

**Top-level parser epilog** — document exit codes and show examples:
```
exit codes:
  0  success
  1  authentication error (no session, expired, 2FA required)
  2  usage error (bad arguments, unknown command)
  3  API error (request failed, rate limited)
  4  unexpected error

examples:
  pc2 accounts                              list all linked accounts
  pc2 transactions --start 90d              last 90 days of transactions
  pc2 net-worth --start yb --format csv     YTD net worth as CSV
  pc2 performance --start mb-6 --account-ids 123,456
  pc2 raw /newaccount/getAccounts2          raw API call
```

**Per-subcommand epilog** — add 1-2 examples plus output description where helpful.
Use `RawDescriptionHelpFormatter` to preserve formatting.

**Acceptance:** `pc2 --help` shows exit codes. `pc2 transactions --help` shows examples.

### 5. Allow `--format` and `--session` after the subcommand

**Problem:** `pc2 accounts --format csv` fails — argparse only recognizes
`--format` before the subcommand. An agent will try the natural word order
(`command --flag`) and hit a wall. Same for `--session`.

**Fix:** Keep `--format` and `--session` on the main parser (preserves current
behavior). Additionally add them to each subparser via a shared parent parser,
using `default=argparse.SUPPRESS` so the subparser doesn't override the main
parser's value when the flag isn't explicitly passed at the subcommand level.

```python
_common = argparse.ArgumentParser(add_help=False)
_common.add_argument("--format", choices=["json", "csv"], default=argparse.SUPPRESS)
_common.add_argument("--session", type=Path, default=argparse.SUPPRESS)
```

Then use `parents=[_common]` in each `add_parser()` call.

Verified behavior:
- `pc2 --format csv accounts` → csv (main parser sets it)
- `pc2 accounts --format csv` → csv (subparser sets it)
- `pc2 accounts` → json (main parser default, subparser doesn't override)

Keep `--version` on the main parser only.

**Acceptance:** Both `pc2 --format csv accounts` and `pc2 accounts --format csv`
produce identical results. `pc2 accounts --help` shows `--format` and `--session`.

### 6. Error suggestions

Add a `"suggestion"` field to structured errors where a recovery action is obvious.
Low effort, meaningful for agent recovery loops.

Examples:
```json
{"error": "No session found", "type": "EmpowerAuthError", "suggestion": "pc2 login"}
```
```json
{"error": "...", "type": "EmpowerAPIError", "suggestion": "Check account IDs with: pc2 accounts"}
```

Only add suggestions where we have a concrete, actionable next step — not on every
error. Auth errors and account-id validation are the clearest cases.

**Acceptance:** `pc2 accounts 2>/dev/null || pc2 accounts 2>&1 | jq -r .suggestion`
returns a usable recovery command.

### 7. Document `snapshot` format-dependent behavior

The `snapshot` command outputs different data depending on `--format`:
- JSON: combined object with `"snapshot"` + `"market_quotes"` keys
- CSV: market quotes table only (snapshot is a single summary row)

This must be documented in the subcommand's help text / epilog so agents don't get
confused when the output shape changes with format.

**Acceptance:** `pc2 snapshot --help` explains the format-dependent behavior.

## What's NOT in scope

- **Noun-verb restructuring** — flat nouns are fine for ~15 read-only commands
- **`--quiet` flag** — agents can pipe to `jq`; adds complexity for marginal gain
- **Built-in `--field`/`--filter`** — same; `jq` is ubiquitous
- **Dry-run** — nothing destructive to preview
- **JSONL streaming** — all responses are finite lists
- **Transient vs. permanent error split** — would require changes to the HTTP client
  error model; revisit when we have real retry scenarios

## Files changed

- `src/personalcapital2/cli.py` — all changes are here
- `tests/test_cli.py` — update/add tests for new behavior

## Risks

- **Argparse subparser class inheritance**: Need to verify that `add_parser()` calls
  use our custom class. May need to pass `parser_class=AgentArgumentParser` to
  `add_subparsers()`.
- **Existing tests**: Many tests assert on current stdout/stderr strings. Auth command
  changes will require updating those assertions.
- **Parent parser + main parser interaction**: Resolved — using
  `default=argparse.SUPPRESS` on the subparser parent avoids the known argparse
  bug where subparser defaults overwrite main parser values. Tested and confirmed
  all three cases work correctly.
