# Roadmap

Standalone open-source package extracted from financial_tracker. The existing ecosystem (haochi/personalcapital) is abandoned and broken — this client fixes all known issues.

## Phases

- [x] **Phase 1: Scaffold + Extract** — project skeleton, parsers, auth, client, tests
- [x] **Phase 2: Typed models + convenience methods** — frozen dataclasses, `client.get_accounts() -> list[Account]`, HTTP mocking tests
- [x] **Phase 3: CLI** — `pc2` argparse command, `--format json`/`--format csv`, relative date args
- [ ] **Phase 4: Richer data** — Full pass-through of all API fields, summary methods, spending endpoint. See [phase4_plan.md](phase4_plan.md)
- [ ] **Phase 5: MCP server** — FastMCP via `pc2 mcp`
- [ ] **Phase 6: Publish to PyPI** — CI, docs, PyPI account setup (install from GitHub until then)

## Design decisions

- Core dependency: only `requests`. CLI and MCP are optional extras.
- Parsers return `list[dict]` (low-level); typed models wrap them (high-level).
- Install before PyPI: `uv add git+https://github.com/wpwilson10/personalcapital2.git`
