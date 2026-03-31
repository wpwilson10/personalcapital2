# Agent-First CLI Design — Research

## Source

[Writing CLI Tools That AI Agents Actually Want to Use](https://dev.to/uenyioha/writing-cli-tools-that-ai-agents-actually-want-to-use-39no) — 8 rules + 13-item checklist for making CLIs agent-friendly.

## Current CLI Assessment

Evaluated by actually running `pc2` as an agent would: `--help`, subcommand help, error cases, output format, exit codes, stderr/stdout separation.

---

## Rule 1: Structured Output Is Not Optional

**Verdict: Mostly passing, auth commands are the gap**

What works:
- JSON is the default output format (no need for `--json` flag)
- CSV alternative via `--format csv`
- Errors written to stderr as JSON (`{"error": "...", "type": "..."}`)
- Data always goes to stdout
- Consistent types: Decimal → int/float, dates → ISO-8601 strings

Gaps:
- **Auth commands (`login`, `logout`, `status`) output plain text to stdout.** An agent parsing `pc2 status` output gets `"No session found at /path"` or `"Session: /path\nLast modified: 3h ago"` — not structured. These should respect `--format` and output JSON when requested.
- No JSONL streaming (not critical — all commands return finite lists, not streams)

## Rule 2: Exit Codes Are the Agent's Control Flow

**Verdict: Good foundation, needs documentation and consistency**

What works:
- Defined exit codes: `0` (OK), `1` (auth), `2` (usage), `3` (API), `4` (unexpected)
- Custom `_error()` writes structured JSON to stderr and exits with the right code

Gaps:
- **Exit codes are not documented anywhere user-visible** — not in `--help`, not in README
- **Argparse usage errors bypass structured error output.** When an agent passes `--start bad-date`, argparse writes plain text to stderr: `pc2 transactions: error: argument --start: invalid date...`. An agent seeing exit code 2 can infer "usage error" but can't programmatically parse the plain text to understand *what* was wrong.
- No distinction between transient and permanent API errors (both exit 3). A rate limit vs. a bad endpoint are very different recovery paths.

## Rule 3: Make Commands Idempotent

**Verdict: Passing (naturally idempotent)**

- `logout` succeeds even if no session exists (exit 0, no error)
- `login` overwrites any existing session
- All data commands are read-only GET requests
- No create/delete/update operations exist

No changes needed.

## Rule 4: Self-Documenting Beats External Docs

**Verdict: Functional but minimal — an agent has to guess too much**

What works:
- Top-level `--help` lists all subcommands with one-line descriptions
- Per-subcommand `--help` shows flags and date format syntax
- Required vs. optional flags are clear (argparse marks required)

Gaps:
- **No examples in help text.** The module docstring has examples but argparse doesn't expose them. An agent seeing `pc2 transactions --help` gets flag descriptions but no usage patterns.
- **Subcommand help is very sparse.** `pc2 accounts --help` shows only `-h, --help` — no description of what the command returns, what shape the output has, or that `--format` applies.
- **`--format` only appears in top-level help.** An agent exploring `pc2 accounts --help` won't discover it.
- **Exit codes undocumented.**

## Rule 5: Design for Composability

**Verdict: Partially passing — JSON pipes work, but no quiet/filter mode**

What works:
- JSON output pipes cleanly to `jq` (tested: `pc2 accounts | jq '.[] | .name'`)
- CSV output works for spreadsheet/data tools

Gaps:
- **No `--quiet` / `-q` flag.** An agent wanting just account IDs has to pipe through `jq` — `pc2 accounts | jq '.[].user_account_id'`. A `--quiet --field user_account_id` would save a dependency.
- **No built-in filtering.** No `--field` to select columns, no `--filter` to narrow rows. The agent must post-process with `jq` for everything.
- Not critical for a 15-command read-only client, but `--quiet` outputting bare values (one per line) would help composability.

## Rule 6: Provide Dry-Run and Confirmation Bypass

**Verdict: Mostly N/A, one gap**

- Read-only API client: no destructive commands, no dry-run needed.
- `login` is inherently interactive (2FA codes) and can't be bypassed.
- **Gap: No TTY detection.** If `login` is run from a non-interactive context (which an agent would do), it just hangs on `input()`. Should detect non-TTY stdin and fail immediately with a clear error: `"Login requires interactive terminal (2FA). Run from a shell."`

## Rule 7: Errors Should Be Actionable

**Verdict: Good for auth, weak elsewhere**

What works:
- Auth error includes recovery action: `"No session found. Run: pc2 login"`
- Structured JSON errors include type field for programmatic parsing
- Exception type preserved in error output

Gaps:
- **Argparse errors are unstructured plain text to stderr.** The most common agent error — bad arguments — produces the least parseable output.
- **No suggestion field in errors.** Article recommends `"suggestion": "run pc2 accounts to list account IDs"` when `--account-ids` validation fails.
- **No transient vs. permanent error distinction.** An API timeout and a 403 both exit 3. An agent can't decide whether to retry.
- **Generic exception handler truncates messages** to 200 chars. Better than leaking, but loses actionability.

## Rule 8: Consistent Noun-Verb Grammar

**Verdict: Flat nouns, no hierarchy**

Current: `pc2 accounts`, `pc2 transactions`, `pc2 net-worth`

Article recommends: `pc2 account list`, `pc2 transaction list` (noun-verb tree).

Assessment: The tool has ~15 commands and they're all "list/get" operations. Noun-verb would add friction (more typing) for no real benefit — there's only one verb per noun. The flat structure is fine here. If we later add write operations (e.g., `pc2 transaction categorize`), reconsider then.

**No change recommended.**

---

## 13-Item Checklist Summary

| # | Requirement | Status | Notes |
|---|---|---|---|
| 1 | `--json` flag | **PASS** | `--format json` is default |
| 2 | JSON to stdout, messages to stderr | **PARTIAL** | Auth commands print plain text to stdout |
| 3 | Meaningful exit codes | **PARTIAL** | Exist but undocumented; argparse bypasses them |
| 4 | Idempotent operations | **PASS** | Read-only API |
| 5 | Comprehensive `--help` with examples | **PARTIAL** | Help exists, no examples, sparse descriptions |
| 6 | `--dry-run` for destructive commands | **N/A** | Read-only |
| 7 | `--yes`/`--force` to bypass prompts | **PARTIAL** | Only `login` is interactive; needs TTY detection |
| 8 | `--quiet` for pipe-friendly output | **FAIL** | Not implemented |
| 9 | Consistent field names and types | **PASS** | Decimals and dates serialize consistently |
| 10 | Consistent noun-verb hierarchy | **SKIP** | Flat nouns fine for read-only tool |
| 11 | Actionable error messages | **PARTIAL** | Auth errors good, argparse errors unstructured |
| 12 | Batch operations | **N/A** | Commands already return lists |
| 13 | Non-interactive TTY detection | **FAIL** | `login` hangs if not a TTY |

---

## Priority-Ordered Change List

### High Impact (agent can't use the tool reliably without these)

1. **Structured argparse errors** — Wrap argparse error handling so usage errors produce JSON to stderr, not plain text. This is the #1 blocker: the most common agent mistake (wrong flag) produces the least parseable output.

2. **Auth command structured output** — `status`, `login`, `logout` should output JSON to stdout when `--format json`. Status especially: an agent checking "am I logged in?" can't parse `"Last modified: 3h ago"`.

3. **TTY detection for `login`** — Fail fast with a clear structured error when stdin isn't a terminal, instead of hanging.

### Medium Impact (agent experience, not blocking)

4. **Help text examples** — Add `epilog` with realistic examples to each subcommand parser. This is what agents read first.

5. **Document exit codes** — In top-level `--help` epilog and README.

6. **`--quiet` / `-q` flag** — Output bare values, one per line. Useful for piping account IDs, transaction amounts, etc. Requires specifying which field to output (or defaulting to a sensible one per command).

### Low Impact (nice to have)

7. **Error suggestions** — Add a `"suggestion"` field to structured errors where a recovery action is obvious.

8. **Transient vs. permanent error distinction** — Split exit code 3 into separate codes or add a `"retryable": true/false` field to error JSON.
