# MCP Server Testing Guide

How to test the MCP tool server during development.

## Prerequisites

1. Install with the MCP extra:
   ```bash
   uv sync  # dev dependencies include mcp
   ```

2. Authenticate (requires interactive terminal for 2FA):
   ```bash
   pc2 login
   ```
   This saves a session to `~/.config/personalcapital2/session.json`. Sessions expire after ~1-2 days.

## Unit tests

The test suite covers all tools with mocked data — no live session needed:

```bash
uv run pytest tests/test_mcp_server.py -v
```

Tests verify: tool registration, input schemas, serialization, error handling (auth/API/network errors), and date validation.

## MCP Inspector

[MCP Inspector](https://github.com/modelcontextprotocol/inspector) is a web UI that connects to your server and lets you call tools interactively. Best for verifying schemas, raw JSON output, and error responses.

```bash
npx @modelcontextprotocol/inspector uv --directory /path/to/personalcapital2 run pc2 mcp
```

This opens a browser UI where you can see all 8 tools, their input schemas, and call them with arbitrary arguments against the live API.

## Testing with Claude Code

Use `--mcp-config` to give a Claude Code session access to the tools without changing your permanent config.

### 1. Create a config file

A `test-mcp.json` is included in the repo root (gitignored):

```json
{
  "mcpServers": {
    "empower": {
      "type": "stdio",
      "command": "uv",
      "args": ["--directory", "/path/to/personalcapital2", "run", "pc2", "mcp"]
    }
  }
}
```

Update the `--directory` path to match your local checkout. The command uses `uv run` so it picks up the project's virtualenv.

### 2. Launch Claude Code with the config

```bash
claude --mcp-config test-mcp.json
```

Claude Code will:
- Read the config at startup
- Spawn `uv run pc2 mcp` as a child process
- Connect over stdio and discover the 8 tools
- Make them available for the model to call

### 3. Test

Ask the model to use the tools:
- "What accounts do I have linked?"
- "Show my transactions for the last 30 days"
- "What's my net worth trend this year?"

The model calls the MCP tools, gets back JSON, and interprets the data.

### 4. Session expiry

When the session expires, tools return:
```
Error: <api error message>

Session is expired or invalid. The user needs to re-authenticate by running: pc2 login
```

Re-run `pc2 login` and restart the Claude Code session.

## Permanent configuration

To always have the tools available, add to `~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "empower": {
      "type": "stdio",
      "command": "pc2",
      "args": ["mcp"],
      "env": {"PC2_SESSION_PATH": "~/.config/personalcapital2/session.json"}
    }
  }
}
```

This requires `pc2` to be on your PATH (e.g. via `pipx install personalcapital2[mcp]` or `uv tool install personalcapital2[mcp]`).
