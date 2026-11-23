# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed

- **Account balances cover every account.** `get_account_balances`, `pc2
  balances` and the MCP `get_account_balances` tool returned only investment
  accounts, because Empower leaves bank and credit-card accounts out of a
  balances-only request. They now return every account, so responses are
  larger. The MCP tool's default `limit` is now 1000, so a month still fits
  in one call. `summary.latest_total` is now
  the sum over every account, which equals Empower's `aggregateBalance`.
  Amounts owed count as positive, so it is not net worth. Before, it was the
  investment total.

### Documentation

- Per-account `performance` is a cumulative percent and can be badly wrong,
  even with the wrong sign, when money moved in or out of the account. Check it
  against `date_range_performance_value_change`.

## [0.6.1] — 2026-11-22

### Fixed

- **`pc2` no longer blocks on stdin without a terminal.** A data command that
  needed a new login, or `pc2 login` without `EMPOWER_EMAIL`/`EMPOWER_PASSWORD`,
  read the email and password from stdin. With stdin as an open pipe, as many
  agent harnesses leave it, the command waited forever. It now fails at once
  with exit 1.
- **Data commands no longer send an SMS no one can enter.** With credentials
  set and no terminal, re-authenticating after an expired session sent the SMS
  code, then waited for it on stdin or failed. Each retry sent another. Now the
  command fails before sending, and says `No code was sent.`
- **MCP: an abandoned 2FA challenge no longer hides a terminal login.** While a
  challenge from `start_authentication` was pending, data tools stopped
  reloading the session file, so a session saved by `pc2 login` was never
  picked up. The challenge now lives on its own client, and data tools always
  reload.
- **Headless `pc2 login`: a failed code's JSON error is on its own line.** A
  piped code isn't echoed, so the error was appended to the
  `Enter verification code:` prompt and the last stderr line wasn't valid JSON.

### Changed

- **CLI auth errors say what was wrong with the session.** When a data command
  needs a login it can't do, `error` starts with `No saved session at ...`,
  `The saved session at ... has expired.` or `The saved session at ... is
  unusable.`, then says why it couldn't sign in. The `type` is still
  `EmpowerAuthError`. Library callers of `run_authenticated()` get the same
  prefix on `InteractiveAuthRequired`.
- **The `suggestion` for CLI auth errors** is now
  ``Ask the user to run `pc2 login` in a terminal, then retry.`` (was
  `pc2 login`). An agent that runs `pc2 login` itself, without a way to read the
  SMS, can't finish it. When the session file isn't the default, the command
  includes `--session <path>`; the MCP server's messages do the same for its
  session file.
- **`pc2 login` without a terminal reads only the SMS code from stdin.** The
  email and password must come from `EMPOWER_EMAIL`/`EMPOWER_PASSWORD`. Reading
  them from piped stdin was never documented and no longer works.
- **Data commands without a terminal no longer read credentials from stdin
  either.** Set `EMPOWER_EMAIL`/`EMPOWER_PASSWORD` instead.
- **`--account-ids` is optional** for `pc2 performance` and `pc2 benchmarks`,
  and `account_ids` is optional for the MCP `get_performance` tool. Leaving it
  out returns every investment account, as an empty list already did.
- **`pc2 login`, `logout` and `status` print `session_path` as an absolute
  path**, matching the auth errors.
- **MCP: a failed SMS send says not to retry right away.** For example, when
  Empower has locked text-message codes after several in a row, each
  `start_authentication` call would send another.
- **MCP auth errors give one next step that can work.** With credentials set,
  they point to `start_authentication` as before. Without them, they ask the
  user to run `pc2 login` in a terminal. The `start_authentication`
  missing-credentials error offers the same.

### Added

- `interactive` keyword argument on `authenticate()` and `run_authenticated()`
  (default `True`, the old behavior). With `False`, nothing is read from stdin
  and a login that needs an SMS code raises `InteractiveAuthRequired` before
  the code is sent; a stale session file is kept rather than deleted. Test
  doubles that replace `authenticate` need to accept the new keyword.

### Documentation

- MCP tool descriptions no longer say every expired session leads to
  `start_authentication`; without credentials, the next step is asking the
  user to run `pc2 login`. The `limit` descriptions say the response size cap
  often stops a list first, so agents page back instead of raising `limit`.
- Empower remembers a device through the session file's cookies, so a login
  to a new `--session` file always sends an SMS code.
- A rejected password also ends the saved session on Empower's side (a new
  known quirk), so data calls fail until a login with the right password.
- The headless login example works: it started `pc2 login` with the
  credentials applied to `printf` instead, and piped a code that couldn't exist
  yet.
- Stale-session recovery is described as working only when Empower doesn't ask
  for a new SMS code.
- `pc2 status` reads only the session file; `"exists": true` doesn't mean the
  session is still valid.

## [0.6.0] — 2026-11-21

### Breaking

- **CLI JSON output is the full result**, the same container the Python API
  and MCP tools return, instead of a bare list of rows. Summaries that were
  dropped before (net worth totals, `total_value`, the cashflow summary,
  `account_summaries`) are now included. Update scripts from
  `pc2 accounts | jq '.[]'` to `jq '.accounts[]'` (see the key table in
  `docs/cli.md`). Commands that share an API call (`transactions`/`categories`,
  `performance`/`benchmarks`, `portfolio`/`snapshot`) print the same JSON.
  `--format csv` is unchanged.
- **MCP tool errors set `isError: true`.** They were returned as ordinary
  results starting with `Error:`. The text now reads
  `Error executing tool <name>: <message>` (the MCP SDK's prefix; ours is gone).
  `start_authentication` and `complete_authentication` failures work the same way.
- **MCP truncation keeps the newest days.** Date-based lists (transactions, net
  worth, balances, performance, portfolio vs benchmark) used to keep their
  first rows. Empower currently returns them oldest-first, so the most recent
  data was cut, and balances lost whole accounts. Now the newest whole days are
  kept, with one cutoff shared by every list in the response, and
  `truncated.next_end_date` says where to page back from. `limit` is a soft
  maximum: the newest day is always returned whole.
- **MCP responses are compact JSON** (no indentation), so 23–36% more rows fit
  under `PC2_MCP_MAX_CHARS`.

### Fixed

- An out-of-range date shortcut (`--start 1000000d`) is a usage error (exit 2)
  instead of a traceback with exit 1.
- Piping into a reader that closes early (`pc2 transactions | head`) exits
  quietly with 141 instead of printing a `BrokenPipeError` and exiting 4.
- The `--account-ids` usage error suggests `pc2 holdings`, which lists every
  investment account; `pc2 accounts` can miss some.
- `pc2 mcp --help` shows `EMPOWER_EMAIL`/`EMPOWER_PASSWORD` in the client
  config (needed for in-chat re-authentication) and quotes the install command.

### Documentation

- Known API quirks: benchmarks are Empower's `^PC_*` blended indexes;
  `portfolio_vs_benchmark` values are cumulative percent changes; histories
  start with a baseline row; unknown account IDs return empty results; row
  order isn't guaranteed.

## [0.5.0] — 2026-11-21

### Changed

- **The `[mcp]` extra now requires the MCP Python SDK 2.x** (`mcp>=2.1,<3.0`).
  The server keeps working with clients on earlier protocol versions, and the
  MCP tools are unchanged. When upgrading, upgrade the extra as well
  (`uv tool upgrade personalcapital2` or `pip install -U "personalcapital2[mcp]"`);
  upgrading `personalcapital2` alone leaves mcp 1.x installed, and `pc2 mcp`
  now says so.
- **Tested on Python 3.12 through 3.15.**
- The README recommends `uv tool install "personalcapital2[mcp]"` for the MCP
  server.
- **CLI: a rejected sign-in now reports `"type": "LoginRejectedError"`**
  (previously `"EmpowerAuthError"`) with no `suggestion`. The exit code is
  still 1. Scripts matching on `type` should accept both. `start_authentication` in the MCP server returns
  `Error: Empower rejected the sign-in (...)` for these instead of
  `Error: authentication failed: ...`.

### Added

- **`LoginRejectedError`** (subclass of `EmpowerAuthError`), raised when
  Empower rejects the sign-in (the username, or a wrong password) and says why. Its message leads with
  Empower's own error codes and messages, replacing the generic
  "rate-limited or invalid credentials" guess. Its `errors`, `codes`,
  `login_url` and `destination_url` fields carry what the server sent. Accounts
  that sign in with a username rather than an email address (codes 113/207)
  are told they aren't supported yet (#9).

### Fixed

- A rejected sign-in no longer deletes the cached session file or retries the
  login. Previously any login error with a session file present was treated as
  a stale session. Other login failures still retry once as before, and their
  messages now include what Empower said.
- **A wrong password no longer forgets the device.** It raises
  `LoginRejectedError` instead of being treated as a stale session, which
  deleted the cached session, retried with a fresh client (sending a new SMS)
  and failed the password a second time.
- "Session is no longer valid" (Empower's exact wording) is recognised as an
  expired session.
- MCP `complete_authentication` with a wrong code no longer repeats "2FA
  verification failed", and it says to call `start_authentication` for a new
  code.
- Without a terminal, a login prompt that hits end-of-input no longer shares a
  line with the CLI's JSON error, so the last line of stderr is always valid
  JSON.
- Under mcp 2.1+, an unexpected API response shape reaches the agent as a
  readable error instead of "Error executing tool <name>".
- The MCP server reports the package version in `serverInfo`.

## [0.4.0] — 2026-05-30

### Breaking

- **Removed `TwoFactorMode.EMAIL`.** Empower no longer offers email as a 2FA
  delivery method — the login screen presents only SMS (and voice call), and
  the legacy `challengeEmail` endpoint returns success while dispatching no
  email. `TwoFactorMode` now has a single member, `SMS`. Code that referenced
  `TwoFactorMode.EMAIL` must use `TwoFactorMode.SMS`.

### Fixed

- **Spurious "Session not authenticated" on the first request after a
  successful login.** Sessions were saved as a domain-less `{name: value}`
  cookie dump, so a reloaded cookie no longer collided with the fresh cookie
  the server set during the next login — both ended up in the jar and the
  stale one shadowed the fresh one, which Empower rejected. Cookies are now
  persisted with their `domain`/`path`/`expires`, so the fresh login cookie
  overwrites the stale one by key. This also lets a remembered device survive
  across runs instead of re-triggering 2FA every time.
- **Email 2FA failed silently.** Selecting email dispatched a challenge that
  never arrived and then blocked waiting for a code; it now errors clearly
  (see below) instead of hanging.

### Changed

- **`EMPOWER_2FA_MODE` accepts `sms` only and is now optional** — 2FA defaults
  to SMS when unset (there is no longer a method to choose). A stale `email`
  value raises a clear `EmpowerAuthError` pointing to SMS rather than a generic
  "invalid mode" error. The interactive 2FA-method prompt has been removed.
- **Session file format.** Cookies are stored as a list of objects with full
  attributes (schema `version: 2`). Pre-0.4.0 files are ignored on load and the
  client re-authenticates once, rewriting the file in the new format — the
  session file is a short-lived cache, so no migration is performed.
- Documentation no longer claims a fixed "6-digit" verification code length
  (Empower's SMS code is shorter); wording is now length-agnostic.

## [0.3.0] — 2026-04-29

### Added

- **`EMPOWER_2FA_MODE` environment variable** — `sms` or `email` (case-insensitive)
  skips the interactive 2FA-method prompt in `pc2 login` and stale-session
  recovery. Read lazily — only consulted when the server actually requires
  2FA, so a leftover value doesn't break flows where the device is remembered.
  Empty/whitespace is treated as unset; an invalid value raises
  `EmpowerAuthError`. Combined with stdin-piped verification codes, this makes
  fully headless invocation possible:
  ```bash
  EMPOWER_EMAIL=... EMPOWER_PASSWORD=... EMPOWER_2FA_MODE=sms \
      printf '%s\n' "$CODE" | pc2 login
  ```
- **`start_authentication` and `complete_authentication` MCP tools** — when
  the cached session expires mid-conversation, the agent recovers in chat:
  `start_authentication` reads credentials from the MCP server's env block
  and dispatches the 2FA challenge; `complete_authentication` submits the
  6-digit code. No terminal context-switch required.
- **`docs/api.md` "Headless library use" section** — concrete example showing
  direct `client.login` / `send_2fa_challenge` / `verify_2fa_and_login` usage
  for library callers wanting full control over credential sourcing and 2FA
  pickup.

### Changed

- **`pc2 mcp` no longer fails to start when no session file exists.** The
  lifespan now logs a warning and starts with an unauthenticated client, so
  agents can bootstrap by calling `start_authentication`. Data tools called
  before authentication return an error string directing the agent at the
  new auth tools.
- **`EmpowerAuthError` tool message updated** to reference
  `start_authentication` / `complete_authentication` instead of `pc2 login`.

Closes [#5](https://github.com/wpwilson10/personalcapital2/issues/5).

## [0.2.2] — 2026-04-28

### Added

- **`EmpowerClient.has_loaded_session`** — boolean property that reports
  whether the client successfully loaded session state from disk. Snapshot
  taken at `load_session()` time, not live state — so a failed fetch that
  picks up server-set tracking cookies does not flip the value.

### Fixed

- **`pc2 raw` against an unknown endpoint now exits 3, not 4.** A 4xx/5xx
  from `raise_for_status` was leaking to `EXIT_UNEXPECTED` with
  `type=HTTPError`. Agents that pin behavior to exit codes saw "unexpected"
  for what is actually an API problem; now routed through `EXIT_API` with
  `type=EmpowerAPIError` and an `HTTP {status}: ...` message.
- **Stale-session recovery log line is now accurate.** When the cached
  session file is empty/malformed (no cookies ever loaded), recovery now
  logs `"Cached session unusable, re-authenticating"` instead of the
  misleading `"Session is stale, re-authenticating"` — there was nothing
  to go stale.

### Documentation

- `docs/cli.md`: added `pc2 mcp` command, environment variables table,
  stale-session recovery behavior, and exit code 5 (was missing — exit 5
  shipped in v0.2.0 but only documented in the README).
- `docs/api.md`: added a `run_authenticated()` section and a typed
  exceptions reference table covering `EmpowerAuthError`,
  `InteractiveAuthRequired`, `TwoFactorRequiredError`, `EmpowerAPIError`,
  and `EmpowerNetworkError`.
- `README.md`: softened session-lifetime claim from "1-2 days" to
  "~24 hours, sometimes sooner" to reflect observed behavior; clarified
  that exit 3 also covers HTTP 4xx/5xx from Empower.

## [0.2.1] — 2026-04-28

### Fixed

- **Credential prompts no longer corrupt stdout.** During stale-session
  recovery, `authenticate()` is invoked mid-command from `run_authenticated`.
  Python's `input(prompt)` writes the prompt to stdout, which broke the CLI's
  JSON-on-stdout contract for agents and `pc2 ... | jq` pipelines. All
  prompts (email, 2FA method, verification code) and `getpass` now write to
  stderr explicitly.
- **`pc2 mcp` with a missing session now reports a useful error.** Previously
  the FastMCP lifespan's `FileNotFoundError` was wrapped by anyio into a
  `BaseExceptionGroup` and surfaced as
  `{"error": "unhandled errors in a TaskGroup (1 sub-exception)", "type": "ExceptionGroup"}`
  at exit code 4. The lifespan now raises `EmpowerAuthError`, and `main()`
  unwraps singleton exception groups so the typed-handler chain produces
  `{"error": "No session file at ...", "type": "EmpowerAuthError", "suggestion": "pc2 login"}`
  at exit code 1.
- **Cold-start data commands skip a wasted API round-trip.** When no session
  file exists, `run_authenticated` now calls `authenticate()` up front
  instead of letting the operation fail with "Session not authenticated"
  first. Also removes a misleading "Session is stale, re-authenticating" log
  line for an absent (rather than expired) session.

## [0.2.0] — 2026-04-28

### Added

- **Stale-session recovery** ([closes #4](https://github.com/wpwilson10/personalcapital2/issues/4)):
  `pc2 login` and every data command now self-heal from a stale cached
  session instead of exiting hard. Recovery is a one-shot retry; set
  `EMPOWER_EMAIL` / `EMPOWER_PASSWORD` to avoid a mid-command password prompt.
- **`EmpowerNetworkError`** — typed exception for transport-level failures
  (connection, timeout, DNS), distinct from auth and API errors.
- **`InteractiveAuthRequired`** — typed exception (subclass of
  `EmpowerAuthError`) raised when a credential or 2FA prompt would block on
  EOFError. Lets library callers distinguish "no TTY" from "bad credentials".
- **`run_authenticated(operation, session_path)`** — new public helper that
  wraps any `EmpowerClient` operation with stale-session recovery. The
  operation must be idempotent.
- **CLI exit code `5`** — network error (`EmpowerNetworkError`).

### Changed

- **CLI:** the `_make_client` indirection is gone; data commands now go through
  `run_authenticated` so missing-session and stale-session paths converge on a
  single recovery primitive. Removed the preemptive non-TTY check in
  `cmd_login` — `authenticate()` raises `InteractiveAuthRequired` on EOFError
  and `main()` formats it as structured JSON.
- Corrupt or empty session files now log a clear `WARNING` instead of
  silently producing an unauthenticated client that fails later with
  "Session is no longer valid".

### Breaking

- **Library users only:** `authenticate()` no longer raises `SystemExit`.
  EOFError on credential/2FA prompts now raises `InteractiveAuthRequired`
  (subclass of `EmpowerAuthError`); login failures raise `EmpowerAuthError`
  directly. CLI users see no behavior change — `main()` formats both as
  structured-JSON stderr.

## [0.1.6] — 2026-04-15

Pre-changelog releases — see git history.
