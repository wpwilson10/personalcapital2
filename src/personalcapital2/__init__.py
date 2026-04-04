"""personalcapital2 — Python client for the Empower (Personal Capital) unofficial API."""

from importlib.metadata import version as _version

__version__: str = _version("personalcapital2")

from personalcapital2.auth import authenticate
from personalcapital2.client import EmpowerClient
from personalcapital2.exceptions import EmpowerAPIError, EmpowerAuthError, TwoFactorRequiredError
from personalcapital2.models import (
    Account,
    AccountBalance,
    AccountBalancesResult,
    AccountPerformanceSummary,
    AccountsResult,
    AccountsSummary,
    BenchmarkPerformance,
    Category,
    Holding,
    HoldingsResult,
    InvestmentPerformance,
    MarketQuote,
    NetWorthEntry,
    NetWorthResult,
    NetWorthSummary,
    PerformanceResult,
    PortfolioSnapshot,
    PortfolioVsBenchmark,
    QuotesResult,
    SpendingDetail,
    SpendingResult,
    SpendingSummary,
    Transaction,
    TransactionsResult,
    TransactionsSummary,
)
from personalcapital2.types import TwoFactorMode

__all__ = [
    "Account",
    "AccountBalance",
    "AccountBalancesResult",
    "AccountPerformanceSummary",
    "AccountsResult",
    "AccountsSummary",
    "BenchmarkPerformance",
    "Category",
    "EmpowerAPIError",
    "EmpowerAuthError",
    "EmpowerClient",
    "Holding",
    "HoldingsResult",
    "InvestmentPerformance",
    "MarketQuote",
    "NetWorthEntry",
    "NetWorthResult",
    "NetWorthSummary",
    "PerformanceResult",
    "PortfolioSnapshot",
    "PortfolioVsBenchmark",
    "QuotesResult",
    "SpendingDetail",
    "SpendingResult",
    "SpendingSummary",
    "Transaction",
    "TransactionsResult",
    "TransactionsSummary",
    "TwoFactorMode",
    "TwoFactorRequiredError",
    "__version__",
    "authenticate",
]
