# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
