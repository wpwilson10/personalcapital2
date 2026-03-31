"""Command-line interface for the Empower (Personal Capital) API.

Usage:
    pc2 login                           # authenticate (interactive 2FA)
    pc2 accounts                        # list linked accounts
    pc2 transactions --start 30d --end today
    pc2 net-worth --start mb-12 --end today --format csv
    pc2 raw /newaccount/getAccounts2    # raw API call
"""

from __future__ import annotations

import argparse
import calendar
import csv
import dataclasses
import io
import json
import re
import sys
from datetime import date, timedelta
from decimal import Decimal
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn

if TYPE_CHECKING:
    from collections.abc import Sequence

from personalcapital2.auth import authenticate
from personalcapital2.client import DEFAULT_SESSION_PATH, EmpowerClient
from personalcapital2.exceptions import EmpowerAPIError, EmpowerAuthError

_VERSION = _pkg_version("personalcapital2")

# Exit codes
EXIT_OK = 0
EXIT_AUTH = 1
EXIT_USAGE = 2  # argparse default
EXIT_API = 3
EXIT_UNEXPECTED = 4


class AgentArgumentParser(argparse.ArgumentParser):
    """ArgumentParser that writes structured JSON errors to stderr.

    Default argparse writes human-readable messages to stderr and calls sys.exit(2).
    This override preserves the exit code but emits JSON so agents can parse errors.
    Defaults to RawDescriptionHelpFormatter to preserve epilog formatting.
    """

    def __init__(self, **kwargs: object) -> None:
        if "formatter_class" not in kwargs:
            kwargs["formatter_class"] = argparse.RawDescriptionHelpFormatter
        super().__init__(**kwargs)  # pyright: ignore[reportArgumentType] — kwargs forwarded to ArgumentParser

    def error(self, message: str) -> NoReturn:
        err: dict[str, str] = {"error": message, "type": "UsageError"}
        if "account-ids" in message:
            err["suggestion"] = "List account IDs with: pc2 accounts"
        sys.stderr.write(json.dumps(err) + "\n")
        sys.exit(EXIT_USAGE)


# Pattern for relative date shortcuts: "30d", "mb", "mb-3", "me", "me-1", "yb", "yb-2", "ye", "ye-1"
_DAYS_AGO_RE = re.compile(r"^(\d+)d$")
_MONTH_BEGIN_RE = re.compile(r"^mb(?:-(\d+))?$")
_MONTH_END_RE = re.compile(r"^me(?:-(\d+))?$")
_YEAR_BEGIN_RE = re.compile(r"^yb(?:-(\d+))?$")
_YEAR_END_RE = re.compile(r"^ye(?:-(\d+))?$")


def _month_offset(months_back: int) -> tuple[int, int]:
    """Calculate (year, month) after subtracting months_back from today."""
    today = date.today()
    total_months = (today.month - 1) - months_back
    year_offset, month_zero = divmod(total_months, 12)
    return today.year + year_offset, month_zero + 1


def _parse_date(s: str) -> date:
    """Parse a date string: YYYY-MM-DD, 'today', Nd, mb[-N], me[-N]."""
    if s == "today":
        return date.today()

    m = _DAYS_AGO_RE.match(s)
    if m:
        return date.today() - timedelta(days=int(m.group(1)))

    m = _MONTH_BEGIN_RE.match(s)
    if m:
        months_back = int(m.group(1)) if m.group(1) else 0
        year, month = _month_offset(months_back)
        return date(year, month, 1)

    m = _MONTH_END_RE.match(s)
    if m:
        months_back = int(m.group(1)) if m.group(1) else 0
        year, month = _month_offset(months_back)
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, last_day)

    m = _YEAR_BEGIN_RE.match(s)
    if m:
        years_back = int(m.group(1)) if m.group(1) else 0
        return date(date.today().year - years_back, 1, 1)

    m = _YEAR_END_RE.match(s)
    if m:
        years_back = int(m.group(1)) if m.group(1) else 0
        return date(date.today().year - years_back, 12, 31)

    try:
        return date.fromisoformat(s)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid date '{s}': use YYYY-MM-DD, 'today', Nd, mb[-N], me[-N], yb[-N], or ye[-N]"
        ) from None


def _parse_account_ids(s: str) -> list[int]:
    """Parse comma-separated account IDs: '100,200,300'."""
    parts = [p.strip() for p in s.split(",") if p.strip()]
    if not parts:
        raise argparse.ArgumentTypeError("account-ids must not be empty")
    try:
        return [int(p) for p in parts]
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid account-ids '{s}': must be comma-separated integers"
        ) from None


def _json_default(obj: object) -> int | float | str:
    """JSON serializer for Decimal and date objects.

    Decimals that are exact integers serialize as int (e.g. 150000 not 150000.0).
    All other Decimals serialize as float, which is lossless for values within
    float64 range - sufficient for financial data (IEEE 754 has 15-17 significant
    digits, far exceeding any dollar amount or percentage the API returns).

    Dates serialize as ISO-8601 strings.

    Raises TypeError for any other type to avoid silently masking bugs.
    """
    if isinstance(obj, Decimal):
        if obj == obj.to_integral_value():
            return int(obj)
        return float(obj)
    if isinstance(obj, date):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _serialize_json(items: Sequence[object]) -> str:
    """Serialize a sequence of dataclass instances to JSON."""
    rows = [dataclasses.asdict(item) for item in items]  # pyright: ignore[reportArgumentType] — items are dataclass instances
    return json.dumps(rows, default=_json_default, indent=2)


def _serialize_csv(items: Sequence[object]) -> str:
    """Serialize a sequence of dataclass instances to CSV."""
    if not items:
        return ""
    fields = [f.name for f in dataclasses.fields(items[0])]  # pyright: ignore[reportArgumentType] — items are dataclass instances
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fields)
    writer.writeheader()
    for item in items:
        row = dataclasses.asdict(item)  # pyright: ignore[reportArgumentType] — items are dataclass instances
        writer.writerow(row)
    return buf.getvalue()


def _output(items: Sequence[object], fmt: str) -> None:
    """Write serialized items to stdout."""
    text = _serialize_csv(items) if fmt == "csv" else _serialize_json(items)
    if text:
        sys.stdout.write(text)
        if fmt != "csv" and not text.endswith("\n"):
            sys.stdout.write("\n")


def _error(
    message: str,
    error_type: str,
    exit_code: int,
    *,
    suggestion: str | None = None,
) -> NoReturn:
    """Write a structured JSON error to stderr and exit."""
    err: dict[str, str] = {"error": message, "type": error_type}
    if suggestion is not None:
        err["suggestion"] = suggestion
    sys.stderr.write(json.dumps(err) + "\n")
    sys.exit(exit_code)


def _make_client(session_path: Path) -> EmpowerClient:
    """Create an EmpowerClient with session loaded.

    If the session file doesn't exist, exits with an auth error.
    If the session is stale/invalid, the first API call will raise
    EmpowerAuthError or EmpowerAPIError, caught by main().
    """
    if not session_path.exists():
        _error(
            "No session found. Run: pc2 login",
            "EmpowerAuthError",
            EXIT_AUTH,
            suggestion="pc2 login",
        )
    # Constructor auto-loads session when session_path is provided
    return EmpowerClient(session_path=session_path)


# --- Auth commands ---


def cmd_login(args: argparse.Namespace) -> None:
    """Authenticate interactively (2FA supported)."""
    session_path = Path(args.session)
    if not sys.stdin.isatty():
        _error(
            "Login requires interactive terminal for 2FA. Run from a shell.",
            "EmpowerAuthError",
            EXIT_AUTH,
            suggestion="Run 'pc2 login' from an interactive terminal",
        )
    client = authenticate(session_path=session_path)
    client.save_session(session_path)
    result = {"session_path": str(session_path), "authenticated": True}
    sys.stdout.write(json.dumps(result) + "\n")


def cmd_logout(args: argparse.Namespace) -> None:
    """Delete the session file."""
    session_path = Path(args.session)
    deleted = False
    if session_path.exists():
        session_path.unlink()
        deleted = True
    result = {"session_path": str(session_path), "deleted": deleted}
    sys.stdout.write(json.dumps(result) + "\n")


def cmd_status(args: argparse.Namespace) -> None:
    """Report session status."""
    import time

    session_path = Path(args.session)
    result: dict[str, str | bool | int] = {
        "session_path": str(session_path),
        "exists": session_path.exists(),
    }
    if session_path.exists():
        stat = session_path.stat()
        age_seconds = int(time.time() - stat.st_mtime)
        if age_seconds < 3600:
            age_human = f"{age_seconds // 60}m"
        elif age_seconds < 86400:
            age_human = f"{age_seconds // 3600}h"
        else:
            age_human = f"{age_seconds // 86400}d"
        result["age_seconds"] = age_seconds
        result["age_human"] = age_human
    sys.stdout.write(json.dumps(result) + "\n")


# --- Data commands ---


def cmd_accounts(args: argparse.Namespace) -> None:
    """List linked accounts."""
    session_path = Path(args.session)
    fmt: str = args.format
    client = _make_client(session_path)
    result = client.get_accounts()
    _output(result.accounts, fmt)


def cmd_transactions(args: argparse.Namespace) -> None:
    """Fetch transactions for a date range."""
    session_path = Path(args.session)
    fmt: str = args.format
    start: date = args.start
    end: date = args.end
    client = _make_client(session_path)
    result = client.get_transactions(start, end)
    _output(result.transactions, fmt)


def cmd_categories(args: argparse.Namespace) -> None:
    """Fetch unique transaction categories for a date range."""
    session_path = Path(args.session)
    fmt: str = args.format
    start: date = args.start
    end: date = args.end
    client = _make_client(session_path)
    result = client.get_transactions(start, end)
    _output(result.categories, fmt)


def cmd_holdings(args: argparse.Namespace) -> None:
    """Fetch current investment holdings."""
    session_path = Path(args.session)
    fmt: str = args.format
    client = _make_client(session_path)
    result = client.get_holdings()
    _output(result.holdings, fmt)


def cmd_net_worth(args: argparse.Namespace) -> None:
    """Fetch daily net worth history."""
    session_path = Path(args.session)
    fmt: str = args.format
    start: date = args.start
    end: date = args.end
    client = _make_client(session_path)
    result = client.get_net_worth(start, end)
    _output(result.entries, fmt)


def cmd_balances(args: argparse.Namespace) -> None:
    """Fetch daily account balance history."""
    session_path = Path(args.session)
    fmt: str = args.format
    start: date = args.start
    end: date = args.end
    client = _make_client(session_path)
    balances = client.get_account_balances(start, end)
    _output(balances, fmt)


def cmd_spending(args: argparse.Namespace) -> None:
    """Fetch spending summary."""
    session_path = Path(args.session)
    fmt: str = args.format
    start: date = args.start
    end: date = args.end
    interval: str = args.interval
    client = _make_client(session_path)
    result = client.get_spending(start, end, interval)
    _output(result.intervals, fmt)


def cmd_performance(args: argparse.Namespace) -> None:
    """Fetch daily investment performance."""
    session_path = Path(args.session)
    fmt: str = args.format
    start: date = args.start
    end: date = args.end
    account_ids: list[int] = args.account_ids
    client = _make_client(session_path)
    result = client.get_performance(start, end, account_ids)
    _output(result.investments, fmt)


def cmd_benchmarks(args: argparse.Namespace) -> None:
    """Fetch daily benchmark performance."""
    session_path = Path(args.session)
    fmt: str = args.format
    start: date = args.start
    end: date = args.end
    account_ids: list[int] = args.account_ids
    client = _make_client(session_path)
    result = client.get_performance(start, end, account_ids)
    _output(result.benchmarks, fmt)


def cmd_portfolio(args: argparse.Namespace) -> None:
    """Fetch daily portfolio vs S&P 500 comparison."""
    session_path = Path(args.session)
    fmt: str = args.format
    start: date = args.start
    end: date = args.end
    client = _make_client(session_path)
    result = client.get_quotes(start, end)
    _output(result.portfolio_vs_benchmark, fmt)


def cmd_snapshot(args: argparse.Namespace) -> None:
    """Output portfolio snapshot and market quotes."""
    session_path = Path(args.session)
    fmt: str = args.format
    start: date = args.start
    end: date = args.end
    client = _make_client(session_path)
    result = client.get_quotes(start, end)
    if fmt == "csv":
        # CSV outputs the market quotes table (snapshot is a single summary row,
        # not useful as a standalone CSV — use JSON for the combined view)
        _output(result.market_quotes, fmt)
    else:
        output = {
            "snapshot": dataclasses.asdict(result.snapshot),
            "market_quotes": [dataclasses.asdict(q) for q in result.market_quotes],
        }
        sys.stdout.write(json.dumps(output, default=_json_default, indent=2) + "\n")


def cmd_raw(args: argparse.Namespace) -> None:
    """Make a raw API call and output the response JSON."""
    session_path = Path(args.session)
    endpoint: str = args.endpoint
    data_pairs: list[str] | None = args.data
    client = _make_client(session_path)
    data: dict[str, str] | None = None
    if data_pairs:
        data = {}
        for pair in data_pairs:
            if "=" not in pair:
                _error(
                    f"invalid --data format '{pair}': use key=value",
                    "UsageError",
                    EXIT_USAGE,
                )
            key, _, value = pair.partition("=")
            data[key] = value
    response = client.fetch(endpoint, data)
    sys.stdout.write(json.dumps(response, default=str, indent=2) + "\n")


# --- Parser ---


def _add_date_args(parser: argparse.ArgumentParser) -> None:
    """Add --start and --end date arguments with sensible defaults."""
    parser.add_argument(
        "--start",
        type=_parse_date,
        default=_parse_date("30d"),
        help="start date (default: 30d). YYYY-MM-DD, today, Nd, mb[-N], me[-N], yb[-N], ye[-N]",
    )
    parser.add_argument(
        "--end",
        type=_parse_date,
        default=_parse_date("today"),
        help="end date (default: today). YYYY-MM-DD, today, Nd, mb[-N], me[-N], yb[-N], ye[-N]",
    )


def _add_account_ids_arg(parser: argparse.ArgumentParser) -> None:
    """Add required --account-ids argument."""
    parser.add_argument(
        "--account-ids",
        type=_parse_account_ids,
        required=True,
        help="comma-separated account IDs (e.g. 100,200,300)",
    )


def build_parser() -> AgentArgumentParser:
    """Build the CLI argument parser."""
    # Shared parent parser so --format and --session work after the subcommand too.
    # Uses SUPPRESS so subparser defaults don't overwrite main parser values.
    _common = AgentArgumentParser(add_help=False)
    _common.add_argument(
        "--format",
        choices=["json", "csv"],
        default=argparse.SUPPRESS,
        help="output format (default: json)",
    )
    _common.add_argument(
        "--session",
        type=Path,
        default=argparse.SUPPRESS,
        help=f"session file path (env: PC2_SESSION_PATH, default: {DEFAULT_SESSION_PATH})",
    )

    parser = AgentArgumentParser(
        prog="pc2",
        description="CLI for the Empower (Personal Capital) API",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
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
  pc2 raw /newaccount/getAccounts2          raw API call""",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"pc2 {_VERSION}",
    )
    parser.add_argument(
        "--format",
        choices=["json", "csv"],
        default="json",
        help="output format (default: json)",
    )
    parser.add_argument(
        "--session",
        type=Path,
        default=DEFAULT_SESSION_PATH,
        help=f"session file path (env: PC2_SESSION_PATH, default: {DEFAULT_SESSION_PATH})",
    )

    sub = parser.add_subparsers(dest="command")

    # Auth commands
    login_p = sub.add_parser(
        "login",
        parents=[_common],
        help="authenticate (interactive 2FA)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  pc2 login                        start interactive 2FA login
  pc2 login --session ./my.json    save session to custom path""",
    )
    login_p.set_defaults(func=cmd_login)

    logout_p = sub.add_parser(
        "logout",
        parents=[_common],
        help="delete session file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  pc2 logout                       delete default session file""",
    )
    logout_p.set_defaults(func=cmd_logout)

    status_p = sub.add_parser(
        "status",
        parents=[_common],
        help="show session status",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  pc2 status                       check if session exists and its age
  pc2 status | jq .exists          machine-readable session check""",
    )
    status_p.set_defaults(func=cmd_status)

    # Data commands (no date args)
    accounts_p = sub.add_parser(
        "accounts",
        parents=[_common],
        help="list linked accounts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  pc2 accounts                     list all linked accounts as JSON
  pc2 accounts --format csv        list accounts as CSV""",
    )
    accounts_p.set_defaults(func=cmd_accounts)

    holdings_p = sub.add_parser(
        "holdings",
        parents=[_common],
        help="current investment holdings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  pc2 holdings                     list current holdings
  pc2 holdings --format csv        export holdings as CSV""",
    )
    holdings_p.set_defaults(func=cmd_holdings)

    # Data commands (with date args)
    transactions_p = sub.add_parser(
        "transactions",
        parents=[_common],
        help="fetch transactions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  pc2 transactions                         last 30 days (default)
  pc2 transactions --start 90d             last 90 days
  pc2 transactions --start 2026-01-01 --end 2026-01-31""",
    )
    _add_date_args(transactions_p)
    transactions_p.set_defaults(func=cmd_transactions)

    categories_p = sub.add_parser(
        "categories",
        parents=[_common],
        help="fetch transaction categories",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  pc2 categories --start mb --end today    categories from this month""",
    )
    _add_date_args(categories_p)
    categories_p.set_defaults(func=cmd_categories)

    net_worth_p = sub.add_parser(
        "net-worth",
        parents=[_common],
        help="daily net worth history",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  pc2 net-worth --start yb                 YTD net worth
  pc2 net-worth --start mb-12 --format csv year of net worth as CSV""",
    )
    _add_date_args(net_worth_p)
    net_worth_p.set_defaults(func=cmd_net_worth)

    balances_p = sub.add_parser(
        "balances",
        parents=[_common],
        help="daily account balance history",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  pc2 balances --start mb --end today      this month's daily balances""",
    )
    _add_date_args(balances_p)
    balances_p.set_defaults(func=cmd_balances)

    portfolio_p = sub.add_parser(
        "portfolio",
        parents=[_common],
        help="portfolio vs S&P 500",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  pc2 portfolio --start mb-6               6-month portfolio vs S&P 500""",
    )
    _add_date_args(portfolio_p)
    portfolio_p.set_defaults(func=cmd_portfolio)

    snapshot_p = sub.add_parser(
        "snapshot",
        parents=[_common],
        help="portfolio snapshot + market quotes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
output varies by format:
  --format json (default)  combined object with "snapshot" and "market_quotes" keys
  --format csv             market quotes table only (snapshot is a single summary
                           row, not useful as standalone CSV — use JSON for the
                           combined view)

examples:
  pc2 snapshot --start mb --end today
  pc2 snapshot --format csv                market quotes as CSV""",
    )
    _add_date_args(snapshot_p)
    snapshot_p.set_defaults(func=cmd_snapshot)

    spending_p = sub.add_parser(
        "spending",
        parents=[_common],
        help="spending summary",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  pc2 spending --start mb-6 --end today --interval MONTH""",
    )
    _add_date_args(spending_p)
    spending_p.add_argument(
        "--interval",
        choices=["MONTH", "WEEK", "YEAR"],
        default="MONTH",
        help="interval type (default: MONTH)",
    )
    spending_p.set_defaults(func=cmd_spending)

    # Data commands (with date args + account IDs)
    performance_p = sub.add_parser(
        "performance",
        parents=[_common],
        help="daily investment performance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  pc2 performance --start mb-6 --account-ids 123,456""",
    )
    _add_date_args(performance_p)
    _add_account_ids_arg(performance_p)
    performance_p.set_defaults(func=cmd_performance)

    benchmarks_p = sub.add_parser(
        "benchmarks",
        parents=[_common],
        help="daily benchmark performance",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  pc2 benchmarks --start mb-6 --account-ids 123,456""",
    )
    _add_date_args(benchmarks_p)
    _add_account_ids_arg(benchmarks_p)
    benchmarks_p.set_defaults(func=cmd_benchmarks)

    # Raw command
    raw_p = sub.add_parser(
        "raw",
        parents=[_common],
        help="raw API call (always JSON output)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  pc2 raw /newaccount/getAccounts2
  pc2 raw /transaction/getUserTransactions --data startDate=2026-01-01 --data endDate=2026-01-31""",
    )
    raw_p.add_argument("endpoint", help="API endpoint (e.g. /newaccount/getAccounts2)")
    raw_p.add_argument(
        "--data",
        action="append",
        metavar="KEY=VALUE",
        help="request data (repeatable)",
    )
    raw_p.set_defaults(func=cmd_raw)

    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(EXIT_USAGE)

    try:
        func = args.func
        func(args)
    except EmpowerAuthError as e:
        _error(str(e), "EmpowerAuthError", EXIT_AUTH, suggestion="pc2 login")
    except EmpowerAPIError as e:
        _error(str(e), "EmpowerAPIError", EXIT_API)
    except KeyboardInterrupt:
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as e:
        # Avoid leaking potentially sensitive details (e.g., request bodies in HTTP errors).
        # Include exception type and a sanitized message.
        msg = type(e).__name__
        err_str = str(e)
        # Only include the message if it doesn't look like it contains request/response data
        if len(err_str) < 200 and "\n" not in err_str:
            msg = err_str
        _error(msg, type(e).__name__, EXIT_UNEXPECTED)
