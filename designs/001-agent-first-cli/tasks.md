# Agent-First CLI — Implementation Tasks

## Tasks

1. **Add AgentArgumentParser with structured JSON errors**
   Override `ArgumentParser.error()` to write `{"error": "...", "type": "UsageError"}` to stderr. Default to `RawDescriptionHelpFormatter`. Replace in `build_parser()`.
   - Done when: `pc2 transactions --start bad-date` writes JSON to stderr, exits 2, nothing to stdout.

2. **Make auth commands output structured JSON**
   Replace `print()` in `cmd_login`, `cmd_logout`, `cmd_status` with JSON to stdout. Always JSON (not tabular, ignore `--format`).
   - `status`: `{"session_path": "...", "exists": bool, "age_seconds": int, "age_human": "3h"}`
   - `login`: `{"session_path": "...", "authenticated": true}`
   - `logout`: `{"session_path": "...", "deleted": bool}`
   - Done when: `pc2 status | jq .exists` returns `true` or `false`.

3. **Add TTY detection to login command**
   Check `sys.stdin.isatty()` at start of `cmd_login`. If not a TTY, exit with structured error, exit code 1.
   - Done when: `echo "" | pc2 login` fails immediately with JSON error, doesn't hang.

4. **Add help text examples and exit code documentation**
   Top-level epilog: exit codes table + usage examples. Per-subcommand epilog: 1-2 examples. Document `snapshot` format-dependent behavior. Use `RawDescriptionHelpFormatter`.
   - Done when: `pc2 --help` shows exit codes. `pc2 transactions --help` shows examples. `pc2 snapshot --help` explains CSV vs JSON difference.

5. **Allow --format and --session after subcommand**
   Create shared parent parser with `default=argparse.SUPPRESS`. Add `parents=[_common]` to every `add_parser()` call. Keep flags on main parser for backward compat.
   - Done when: `pc2 --format csv accounts` and `pc2 accounts --format csv` produce identical results.

6. **Add suggestion field to structured errors**
   Add optional `suggestion` parameter to `_error()`. Auth errors: `"pc2 login"`. Account ID validation: `"List account IDs with: pc2 accounts"`. Only where actionable.
   - Done when: auth error JSON includes `"suggestion"` field with recovery command.

7. **Update tests for all CLI changes**
   Update existing auth command assertions (now JSON). Add tests for structured argparse errors, TTY detection, flag position flexibility, suggestion field, help text content.
   - Done when: `uv run pytest && uv run pyright . && uv run ruff check .` all pass.
