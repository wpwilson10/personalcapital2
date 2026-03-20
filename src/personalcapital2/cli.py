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
from pathlib import Path
from typing import NoReturn

from personalcapital2.auth import authenticate
from personalcapital2.client import DEFAULT_SESSION_PATH, EmpowerClient
from personalcapital2.exceptions import EmpowerAPIError, EmpowerAuthError

# Exit codes
EXIT_OK = 0
EXIT_AUTH = 1
EXIT_USAGE = 2  # argparse default
EXIT_API = 3
EXIT_UNEXPECTED = 4

# Pattern for relative date shortcuts: "30d", "mb", "mb-3", "me", "me-1"
_DAYS_AGO_RE = re.compile(r"^(\d+)d$")
_MONTH_BEGIN_RE = re.compile(r"^mb(?:-(\d+))?$")
_MONTH_END_RE = re.compile(r"^me(?:-(\d+))?$")


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

    try:
        return date.fromisoformat(s)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"invalid date '{s}': use YYYY-MM-DD, 'today', Nd, mb[-N], or me[-N]"
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
    """
    if isinstance(obj, Decimal):
        if obj == obj.to_integral_value():
            return int(obj)
        return float(obj)
    return str(obj)


def _serialize_json(items: list[object]) -> str:
    """Serialize a list of dataclass instances to JSON."""
    rows = [dataclasses.asdict(item) for item in items]  # pyright: ignore[reportArgumentType] — items are dataclass instances
    return json.dumps(rows, default=_json_default, indent=2)


def _serialize_csv(items: list[object]) -> str:
    """Serialize a list of dataclass instances to CSV."""
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


def _output(items: list[object], fmt: str) -> None:
    """Write serialized items to stdout."""
    text = _serialize_csv(items) if fmt == "csv" else _serialize_json(items)
    if text:
        sys.stdout.write(text)
        if fmt != "csv" and not text.endswith("\n"):
            sys.stdout.write("\n")


def _error(message: str, error_type: str, exit_code: int) -> NoReturn:
    """Write a structured JSON error to stderr and exit."""
    err = {"error": message, "type": error_type}
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
        )
    # Constructor auto-loads session when session_path is provided
    return EmpowerClient(session_path=session_path)


# --- Auth commands ---


def cmd_login(args: argparse.Namespace) -> None:
    """Authenticate interactively (2FA supported)."""
    session_path = Path(args.session)
    client = authenticate(session_path=session_path)
    client.save_session(session_path)
    print(f"Logged in. Session saved to {session_path}")


def cmd_logout(args: argparse.Namespace) -> None:
    """Delete the session file."""
    session_path = Path(args.session)
    if session_path.exists():
        session_path.unlink()
        print(f"Session deleted: {session_path}")
    else:
        print(f"No session file found at {session_path}")


def cmd_status(args: argparse.Namespace) -> None:
    """Report session status."""
    session_path = Path(args.session)
    if session_path.exists():
        import time

        stat = session_path.stat()
        age_seconds = time.time() - stat.st_mtime
        if age_seconds < 3600:
            age_str = f"{int(age_seconds / 60)}m ago"
        elif age_seconds < 86400:
            age_str = f"{int(age_seconds / 3600)}h ago"
        else:
            age_str = f"{int(age_seconds / 86400)}d ago"
        print(f"Session: {session_path}")
        print(f"Last modified: {age_str}")
    else:
        print(f"No session found at {session_path}")


# --- Data commands ---


def cmd_accounts(args: argparse.Namespace) -> None:
    """List linked accounts."""
    session_path = Path(args.session)
    fmt: str = args.format
    client = _make_client(session_path)
    accounts = client.get_accounts()
    _output(accounts, fmt)  # pyright: ignore[reportArgumentType] — list covariance


def cmd_transactions(args: argparse.Namespace) -> None:
    """Fetch transactions for a date range."""
    session_path = Path(args.session)
    fmt: str = args.format
    start: date = args.start
    end: date = args.end
    client = _make_client(session_path)
    txns = client.get_transactions(start, end)
    _output(txns, fmt)  # pyright: ignore[reportArgumentType] — list covariance


def cmd_categories(args: argparse.Namespace) -> None:
    """Fetch unique transaction categories for a date range."""
    session_path = Path(args.session)
    fmt: str = args.format
    start: date = args.start
    end: date = args.end
    client = _make_client(session_path)
    cats = client.get_categories(start, end)
    _output(cats, fmt)  # pyright: ignore[reportArgumentType] — list covariance


def cmd_holdings(args: argparse.Namespace) -> None:
    """Fetch current investment holdings."""
    session_path = Path(args.session)
    fmt: str = args.format
    client = _make_client(session_path)
    holdings = client.get_holdings()
    _output(holdings, fmt)  # pyright: ignore[reportArgumentType] — list covariance


def cmd_net_worth(args: argparse.Namespace) -> None:
    """Fetch daily net worth history."""
    session_path = Path(args.session)
    fmt: str = args.format
    start: date = args.start
    end: date = args.end
    client = _make_client(session_path)
    entries = client.get_net_worth(start, end)
    _output(entries, fmt)  # pyright: ignore[reportArgumentType] — list covariance


def cmd_balances(args: argparse.Namespace) -> None:
    """Fetch daily account balance history."""
    session_path = Path(args.session)
    fmt: str = args.format
    start: date = args.start
    end: date = args.end
    client = _make_client(session_path)
    balances = client.get_account_balances(start, end)
    _output(balances, fmt)  # pyright: ignore[reportArgumentType] — list covariance


def cmd_performance(args: argparse.Namespace) -> None:
    """Fetch daily investment performance."""
    session_path = Path(args.session)
    fmt: str = args.format
    start: date = args.start
    end: date = args.end
    account_ids: list[int] = args.account_ids
    client = _make_client(session_path)
    perfs = client.get_investment_performance(start, end, account_ids)
    _output(perfs, fmt)  # pyright: ignore[reportArgumentType] — list covariance


def cmd_benchmarks(args: argparse.Namespace) -> None:
    """Fetch daily benchmark performance."""
    session_path = Path(args.session)
    fmt: str = args.format
    start: date = args.start
    end: date = args.end
    account_ids: list[int] = args.account_ids
    client = _make_client(session_path)
    benchmarks = client.get_benchmark_performance(start, end, account_ids)
    _output(benchmarks, fmt)  # pyright: ignore[reportArgumentType] — list covariance


def cmd_portfolio(args: argparse.Namespace) -> None:
    """Fetch daily portfolio vs S&P 500 comparison."""
    session_path = Path(args.session)
    fmt: str = args.format
    start: date = args.start
    end: date = args.end
    client = _make_client(session_path)
    pvb = client.get_portfolio_vs_benchmark(start, end)
    _output(pvb, fmt)  # pyright: ignore[reportArgumentType] — list covariance


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
    """Add required --start and --end date arguments."""
    parser.add_argument(
        "--start",
        type=_parse_date,
        required=True,
        help="start date: YYYY-MM-DD, today, Nd, mb[-N], me[-N]",
    )
    parser.add_argument(
        "--end",
        type=_parse_date,
        required=True,
        help="end date: YYYY-MM-DD, today, Nd, mb[-N], me[-N]",
    )


def _add_account_ids_arg(parser: argparse.ArgumentParser) -> None:
    """Add required --account-ids argument."""
    parser.add_argument(
        "--account-ids",
        type=_parse_account_ids,
        required=True,
        help="comma-separated account IDs (e.g. 100,200,300)",
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="pc2",
        description="CLI for the Empower (Personal Capital) API",
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
        help=f"session file path (default: {DEFAULT_SESSION_PATH})",
    )

    sub = parser.add_subparsers(dest="command")

    # Auth commands
    login_p = sub.add_parser("login", help="authenticate (interactive 2FA)")
    login_p.set_defaults(func=cmd_login)

    logout_p = sub.add_parser("logout", help="delete session file")
    logout_p.set_defaults(func=cmd_logout)

    status_p = sub.add_parser("status", help="show session status")
    status_p.set_defaults(func=cmd_status)

    # Data commands (no date args)
    accounts_p = sub.add_parser("accounts", help="list linked accounts")
    accounts_p.set_defaults(func=cmd_accounts)

    holdings_p = sub.add_parser("holdings", help="current investment holdings")
    holdings_p.set_defaults(func=cmd_holdings)

    # Data commands (with date args)
    transactions_p = sub.add_parser("transactions", help="fetch transactions")
    _add_date_args(transactions_p)
    transactions_p.set_defaults(func=cmd_transactions)

    categories_p = sub.add_parser("categories", help="fetch transaction categories")
    _add_date_args(categories_p)
    categories_p.set_defaults(func=cmd_categories)

    net_worth_p = sub.add_parser("net-worth", help="daily net worth history")
    _add_date_args(net_worth_p)
    net_worth_p.set_defaults(func=cmd_net_worth)

    balances_p = sub.add_parser("balances", help="daily account balance history")
    _add_date_args(balances_p)
    balances_p.set_defaults(func=cmd_balances)

    portfolio_p = sub.add_parser("portfolio", help="portfolio vs S&P 500")
    _add_date_args(portfolio_p)
    portfolio_p.set_defaults(func=cmd_portfolio)

    # Data commands (with date args + account IDs)
    performance_p = sub.add_parser("performance", help="daily investment performance")
    _add_date_args(performance_p)
    _add_account_ids_arg(performance_p)
    performance_p.set_defaults(func=cmd_performance)

    benchmarks_p = sub.add_parser("benchmarks", help="daily benchmark performance")
    _add_date_args(benchmarks_p)
    _add_account_ids_arg(benchmarks_p)
    benchmarks_p.set_defaults(func=cmd_benchmarks)

    # Raw command
    raw_p = sub.add_parser("raw", help="raw API call (always JSON output)")
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
        _error(str(e), "EmpowerAuthError", EXIT_AUTH)
    except EmpowerAPIError as e:
        _error(str(e), "EmpowerAPIError", EXIT_API)
    except KeyboardInterrupt:
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as e:
        _error(str(e), type(e).__name__, EXIT_UNEXPECTED)
