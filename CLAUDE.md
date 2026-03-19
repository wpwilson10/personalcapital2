# personalcapital2

Python client for the Empower (Personal Capital) unofficial API.

## Development

```bash
uv sync
uv run pytest
uv run pyright .
uv run ruff check .
```

## Project Structure

- `src/personalcapital2/client.py` — HTTP client, auth, session persistence
- `src/personalcapital2/parsers/` — transform raw API responses into normalized dicts
- `src/personalcapital2/auth.py` — interactive 2FA login flow
- `tests/` — pytest suite (parsers, validation, client)

## Key Conventions

- Parsers are faithful pass-throughs: type coercion and key renaming only, no data manipulation
- Known API quirks are documented in docstrings and README, not silently corrected
- pyright strict mode, no untyped code
- Auth requires interactive terminal for 2FA — scripts needing auth must be run by the user

## Test Data

Cached raw API responses in `data/raw_responses/` (gitignored). Refresh with:
```bash
cd ~/Documents/Claude/financial_tracker && op run --env-file .env -- uv run python ~/Documents/Claude/personalcapital2/scripts/dump_raw_responses.py
```
