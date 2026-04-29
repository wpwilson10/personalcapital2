# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
