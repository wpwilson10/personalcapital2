"""Tests for EmpowerClient convenience methods using HTTP mocking."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
import responses

from personalcapital2.client import API_URL, EmpowerClient
from personalcapital2.exceptions import EmpowerAPIError
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
    Transaction,
    TransactionsResult,
    TransactionsSummary,
)


def _api_url(endpoint: str) -> str:
    return f"{API_URL}{endpoint}"


def _success_response(sp_data: dict[str, Any]) -> dict[str, Any]:
    return {"spHeader": {"success": True, "csrf": "test-csrf"}, "spData": sp_data}


def _error_response(message: str) -> dict[str, Any]:
    return {"spHeader": {"success": False, "errors": [{"message": message}]}}


def _make_client() -> EmpowerClient:
    client = EmpowerClient()
    client._csrf = "test-csrf"
    return client


# --- get_accounts ---


@responses.activate
def test_get_accounts_happy_path() -> None:
    responses.post(
        _api_url("/newaccount/getAccounts2"),
        json=_success_response(
            {
                "accounts": [
                    {
                        "userAccountId": 100,
                        "accountId": "A-1",
                        "name": "Checking",
                        "firmName": "Big Bank",
                        "accountTypeNew": "BANK",
                        "accountTypeGroup": "CASH",
                        "productType": "CHECKING",
                        "currency": "USD",
                        "isAsset": True,
                        "createdDate": 1700000000000,
                        "balance": 5000.0,
                    }
                ],
                "networth": 100000.0,
                "assets": 120000.0,
                "liabilities": 20000.0,
                "cashAccountsTotal": 5000.0,
                "investmentAccountsTotal": 115000.0,
                "creditCardAccountsTotal": 2000.0,
                "mortgageAccountsTotal": 18000.0,
                "loanAccountsTotal": 0.0,
                "otherAssetAccountsTotal": 0.0,
                "otherLiabilitiesAccountsTotal": 0.0,
            }
        ),
    )
    client = _make_client()
    result = client.get_accounts()

    assert isinstance(result, AccountsResult)
    assert len(result.accounts) == 1
    assert isinstance(result.accounts[0], Account)
    assert result.accounts[0].user_account_id == 100
    assert result.accounts[0].name == "Checking"
    assert result.accounts[0].is_asset is True
    assert result.accounts[0].is_closed is False
    assert isinstance(result.accounts[0].created_at, date)
    assert result.accounts[0].balance == Decimal("5000")

    assert isinstance(result.summary, AccountsSummary)
    assert result.summary.networth == Decimal("100000")
    assert result.summary.assets == Decimal("120000")


@responses.activate
def test_get_accounts_empty() -> None:
    responses.post(
        _api_url("/newaccount/getAccounts2"),
        json=_success_response({"accounts": []}),
    )
    client = _make_client()
    result = client.get_accounts()
    assert result.accounts == ()


@responses.activate
def test_get_accounts_api_error() -> None:
    responses.post(
        _api_url("/newaccount/getAccounts2"),
        json=_error_response("Rate limited"),
    )
    client = _make_client()
    with pytest.raises(EmpowerAPIError, match="Rate limited"):
        client.get_accounts()


# --- get_transactions ---


@responses.activate
def test_get_transactions_happy_path() -> None:
    responses.post(
        _api_url("/transaction/getUserTransactions"),
        json=_success_response(
            {
                "transactions": [
                    {
                        "userTransactionId": 500,
                        "userAccountId": 100,
                        "transactionDate": "2026-01-15",
                        "amount": 42.50,
                        "isCashIn": False,
                        "isIncome": False,
                        "isSpending": True,
                        "description": "Coffee Shop",
                        "originalDescription": "COFFEE SHOP #99",
                        "simpleDescription": "Coffee",
                        "categoryId": 3,
                        "categoryName": "Food",
                        "categoryType": "EXPENSE",
                        "merchant": "Java Joe",
                        "transactionType": "Purchase",
                        "status": "posted",
                        "currency": "USD",
                    }
                ],
                "moneyIn": 1000.0,
                "moneyOut": 500.0,
                "netCashflow": 500.0,
                "averageIn": 1000.0,
                "averageOut": 500.0,
                "startDate": "2026-01-01",
                "endDate": "2026-01-31",
            }
        ),
    )
    client = _make_client()
    result = client.get_transactions(date(2026, 1, 1), date(2026, 1, 31))

    assert isinstance(result, TransactionsResult)
    assert len(result.transactions) == 1
    assert isinstance(result.transactions[0], Transaction)
    assert result.transactions[0].date == date(2026, 1, 15)
    assert result.transactions[0].amount == Decimal("42.5")
    assert result.transactions[0].merchant == "Java Joe"

    assert len(result.categories) == 1
    assert isinstance(result.categories[0], Category)
    assert result.categories[0].name == "Food"

    assert isinstance(result.summary, TransactionsSummary)
    assert result.summary.money_in == Decimal("1000")
    assert result.summary.net_cashflow == Decimal("500")


@responses.activate
def test_get_transactions_sends_date_params() -> None:
    responses.post(
        _api_url("/transaction/getUserTransactions"),
        json=_success_response(
            {
                "transactions": [],
                "moneyIn": 0,
                "moneyOut": 0,
                "netCashflow": 0,
                "averageIn": 0,
                "averageOut": 0,
                "startDate": "2026-03-01",
                "endDate": "2026-03-31",
            }
        ),
    )
    client = _make_client()
    client.get_transactions(date(2026, 3, 1), date(2026, 3, 31))

    body = str(responses.calls[0].request.body)
    assert "startDate=2026-03-01" in body
    assert "endDate=2026-03-31" in body


@responses.activate
def test_get_transactions_empty() -> None:
    responses.post(
        _api_url("/transaction/getUserTransactions"),
        json=_success_response(
            {
                "transactions": [],
                "moneyIn": 0,
                "moneyOut": 0,
                "netCashflow": 0,
                "averageIn": 0,
                "averageOut": 0,
                "startDate": "2026-01-01",
                "endDate": "2026-01-31",
            }
        ),
    )
    client = _make_client()
    result = client.get_transactions(date(2026, 1, 1), date(2026, 1, 31))
    assert result.transactions == ()
    assert result.categories == ()


# --- get_holdings ---


@responses.activate
def test_get_holdings_happy_path() -> None:
    responses.post(
        _api_url("/invest/getHoldings"),
        json=_success_response(
            {
                "holdings": [
                    {
                        "userAccountId": 200,
                        "ticker": "VTI",
                        "cusip": "922908769",
                        "description": "Vanguard Total Stock Mkt ETF",
                        "quantity": 50.0,
                        "price": 250.00,
                        "value": 12500.00,
                        "holdingType": "etf",
                        "securityType": "equity",
                        "holdingPercentage": 0.75,
                        "source": "broker",
                    }
                ],
                "holdingsTotalValue": 12500.00,
            }
        ),
    )
    client = _make_client()
    result = client.get_holdings()

    assert isinstance(result, HoldingsResult)
    assert len(result.holdings) == 1
    assert isinstance(result.holdings[0], Holding)
    assert result.holdings[0].ticker == "VTI"
    assert result.holdings[0].value == Decimal("12500")
    assert isinstance(result.holdings[0].snapshot_date, date)
    assert result.total_value == Decimal("12500")


@responses.activate
def test_get_holdings_empty() -> None:
    responses.post(
        _api_url("/invest/getHoldings"),
        json=_success_response({"holdings": [], "holdingsTotalValue": 0}),
    )
    client = _make_client()
    result = client.get_holdings()
    assert result.holdings == ()
    assert result.total_value == Decimal("0")


# --- get_net_worth ---


@responses.activate
def test_get_net_worth_happy_path() -> None:
    responses.post(
        _api_url("/account/getHistories"),
        json=_success_response(
            {
                "networthHistories": [
                    {
                        "date": "2026-03-01",
                        "networth": 150000.0,
                        "totalAssets": 200000.0,
                        "totalLiabilities": 50000.0,
                        "totalCash": 30000.0,
                        "totalInvestment": 170000.0,
                        "totalCredit": 5000.0,
                        "totalMortgage": 40000.0,
                        "totalLoan": 5000.0,
                        "totalOtherAssets": 0.0,
                        "totalOtherLiabilities": 0.0,
                    }
                ],
                "networthSummary": {
                    "dateRangeChange": 5000.0,
                    "dateRangePercentageChange": 3.45,
                    "dateRangeCashChange": 1000.0,
                    "dateRangeCashPercentageChange": 2.0,
                    "dateRangeInvestmentChange": 4000.0,
                    "dateRangeInvestmentPercentageChange": 2.5,
                    "dateRangeCreditChange": 0.0,
                    "dateRangeCreditPercentageChange": 0.0,
                    "dateRangeMortgageChange": 0.0,
                    "dateRangeMortgagePercentageChange": 0.0,
                    "dateRangeLoanChange": 0.0,
                    "dateRangeLoanPercentageChange": 0.0,
                    "dateRangeOtherAssetsChange": 0.0,
                    "dateRangeOtherAssetsPercentageChange": 0.0,
                    "dateRangeOtherLiabilitiesChange": 0.0,
                    "dateRangeOtherLiabilitiesPercentageChange": 0.0,
                },
            }
        ),
    )
    client = _make_client()
    result = client.get_net_worth(date(2026, 3, 1), date(2026, 3, 31))

    assert isinstance(result, NetWorthResult)
    assert len(result.entries) == 1
    assert isinstance(result.entries[0], NetWorthEntry)
    assert result.entries[0].date == date(2026, 3, 1)
    assert result.entries[0].networth == Decimal("150000")

    assert isinstance(result.summary, NetWorthSummary)
    assert result.summary.date_range_change == Decimal("5000")


@responses.activate
def test_get_net_worth_sends_date_params() -> None:
    responses.post(
        _api_url("/account/getHistories"),
        json=_success_response({"networthHistories": [], "networthSummary": {}}),
    )
    client = _make_client()
    client.get_net_worth(date(2026, 1, 1), date(2026, 12, 31))

    body = str(responses.calls[0].request.body)
    assert "startDate=2026-01-01" in body
    assert "endDate=2026-12-31" in body


# --- get_account_balances ---


@responses.activate
def test_get_account_balances_happy_path() -> None:
    responses.post(
        _api_url("/account/getHistories"),
        json=_success_response(
            {
                "histories": [
                    {
                        "date": "2026-03-15",
                        "balances": {"789": 5432.10, "annotation": "skip"},
                    }
                ]
            }
        ),
    )
    client = _make_client()
    result = client.get_account_balances(date(2026, 3, 1), date(2026, 3, 31))

    assert isinstance(result, AccountBalancesResult)
    assert len(result.balances) == 1
    assert isinstance(result.balances[0], AccountBalance)
    assert result.balances[0].date == date(2026, 3, 15)
    assert result.balances[0].user_account_id == 789
    assert result.balances[0].balance == Decimal("5432.1")


@responses.activate
def test_get_account_balances_empty() -> None:
    responses.post(
        _api_url("/account/getHistories"),
        json=_success_response({"histories": []}),
    )
    client = _make_client()
    result = client.get_account_balances(date(2026, 1, 1), date(2026, 1, 31))
    assert result.balances == ()


# --- get_performance ---


@responses.activate
def test_get_performance_happy_path() -> None:
    responses.post(
        _api_url("/account/getPerformanceHistories"),
        json=_success_response(
            {
                "performanceHistory": [
                    {
                        "date": "2026-03-15",
                        "300": 0.0823,
                        "aggregatePerformance": 0.09,
                    }
                ],
                "benchmarkPerformanceHistory": [
                    {
                        "date": "2026-03-15",
                        "^INX": 0.1245,
                    }
                ],
                "accountSummaries": [
                    {
                        "userAccountId": 300,
                        "accountName": "IRA",
                        "siteName": "Fidelity",
                        "currentBalance": 50000.0,
                        "percentOfTotal": 100.0,
                        "income": 0.0,
                        "expense": 0.0,
                        "cashFlow": 0.0,
                        "oneDayBalanceValueChange": 100.0,
                        "oneDayBalancePercentageChange": 0.2,
                        "dateRangeBalanceValueChange": 5000.0,
                        "dateRangeBalancePercentageChange": 11.1,
                        "dateRangePerformanceValueChange": 5500.0,
                        "oneDayPerformanceValueChange": 100.0,
                        "balanceAsOfEndDate": 50000.0,
                        "closedDate": "",
                    }
                ],
            }
        ),
    )
    client = _make_client()
    result = client.get_performance(date(2026, 1, 1), date(2026, 3, 31), [300])

    assert isinstance(result, PerformanceResult)

    # Only one API call
    assert len(responses.calls) == 1

    assert len(result.investments) == 1
    assert isinstance(result.investments[0], InvestmentPerformance)
    assert result.investments[0].performance == Decimal("0.0823")

    assert len(result.benchmarks) == 1
    assert isinstance(result.benchmarks[0], BenchmarkPerformance)
    assert result.benchmarks[0].benchmark == "^INX"
    assert result.benchmarks[0].performance == Decimal("0.1245")

    assert len(result.account_summaries) == 1
    assert isinstance(result.account_summaries[0], AccountPerformanceSummary)
    assert result.account_summaries[0].user_account_id == 300
    assert result.account_summaries[0].current_balance == Decimal("50000")


@responses.activate
def test_get_performance_sends_account_ids() -> None:
    responses.post(
        _api_url("/account/getPerformanceHistories"),
        json=_success_response(
            {
                "performanceHistory": [],
                "benchmarkPerformanceHistory": [],
                "accountSummaries": [],
            }
        ),
    )
    client = _make_client()
    client.get_performance(date(2026, 1, 1), date(2026, 3, 31), [100, 200])

    body = str(responses.calls[0].request.body)
    assert "userAccountIds" in body
    assert "100" in body
    assert "200" in body


@responses.activate
def test_get_performance_empty() -> None:
    responses.post(
        _api_url("/account/getPerformanceHistories"),
        json=_success_response(
            {
                "performanceHistory": [],
                "benchmarkPerformanceHistory": [],
                "accountSummaries": [],
            }
        ),
    )
    client = _make_client()
    result = client.get_performance(date(2026, 1, 1), date(2026, 3, 31), [300])
    assert result.investments == ()
    assert result.benchmarks == ()
    assert result.account_summaries == ()


# --- get_quotes ---


@responses.activate
def test_get_quotes_happy_path() -> None:
    responses.post(
        _api_url("/invest/getQuotes"),
        json=_success_response(
            {
                "histories": [
                    {
                        "date": "2026-03-15",
                        "YOU": 105.5,
                        "^INX": 103.2,
                    }
                ],
                "latestPortfolio": {
                    "last": 780000.0,
                    "change": -4500.0,
                    "percentChange": -0.58,
                },
                "latestQuotes": [
                    {
                        "ticker": "^INX",
                        "last": 6624.7,
                        "change": -91.39,
                        "percentChange": -1.36,
                        "longName": "S&P 500",
                        "date": "2026-03-15",
                    }
                ],
            }
        ),
    )
    client = _make_client()
    result = client.get_quotes(date(2026, 1, 1), date(2026, 3, 31))

    assert isinstance(result, QuotesResult)

    assert len(result.portfolio_vs_benchmark) == 1
    assert isinstance(result.portfolio_vs_benchmark[0], PortfolioVsBenchmark)
    assert result.portfolio_vs_benchmark[0].date == date(2026, 3, 15)
    assert result.portfolio_vs_benchmark[0].portfolio_value == Decimal("105.5")

    assert isinstance(result.snapshot, PortfolioSnapshot)
    assert result.snapshot.last == Decimal("780000")
    assert result.snapshot.change == Decimal("-4500")

    assert len(result.market_quotes) == 1
    assert isinstance(result.market_quotes[0], MarketQuote)
    assert result.market_quotes[0].ticker == "^INX"
    assert result.market_quotes[0].last == Decimal("6624.7")


@responses.activate
def test_get_quotes_sends_date_params() -> None:
    responses.post(
        _api_url("/invest/getQuotes"),
        json=_success_response(
            {
                "histories": [],
                "latestPortfolio": {"last": 0, "change": 0, "percentChange": 0},
                "latestQuotes": [],
            }
        ),
    )
    client = _make_client()
    client.get_quotes(date(2026, 1, 1), date(2026, 6, 30))

    body = str(responses.calls[0].request.body)
    assert "startDate=2026-01-01" in body
    assert "endDate=2026-06-30" in body


@responses.activate
def test_get_quotes_missing_snapshot() -> None:
    """get_quotes should not crash when latestPortfolio is missing."""
    responses.post(
        _api_url("/invest/getQuotes"),
        json=_success_response(
            {
                "histories": [],
                "latestQuotes": [],
            }
        ),
    )
    client = _make_client()
    result = client.get_quotes(date(2026, 1, 1), date(2026, 3, 31))

    assert result.snapshot.last == Decimal("0")
    assert result.snapshot.change == Decimal("0")
    assert result.snapshot.percent_change == Decimal("0")


@responses.activate
def test_get_quotes_api_error() -> None:
    responses.post(
        _api_url("/invest/getQuotes"),
        json=_error_response("Invalid request"),
    )
    client = _make_client()
    with pytest.raises(EmpowerAPIError, match="Invalid request"):
        client.get_quotes(date(2026, 1, 1), date(2026, 3, 31))


# --- get_spending ---


@responses.activate
def test_get_spending_happy_path() -> None:
    responses.post(
        _api_url("/account/getUserSpending"),
        json=_success_response(
            {
                "intervals": [
                    {
                        "type": "MONTH",
                        "average": 3683.74,
                        "current": 3673.54,
                        "target": 2836.88,
                        "details": [
                            {"date": "2026-03-01", "amount": 516.88},
                        ],
                    }
                ]
            }
        ),
    )
    client = _make_client()
    from personalcapital2.models import SpendingResult, SpendingSummary

    result = client.get_spending(date(2026, 1, 1), date(2026, 3, 31))

    assert isinstance(result, SpendingResult)
    assert len(result.intervals) == 1
    assert isinstance(result.intervals[0], SpendingSummary)
    assert result.intervals[0].type == "MONTH"
    assert result.intervals[0].average == Decimal("3683.74")
    assert result.intervals[0].current == Decimal("3673.54")
    assert len(result.intervals[0].details) == 1
    assert result.intervals[0].details[0].amount == Decimal("516.88")


@responses.activate
def test_get_spending_empty() -> None:
    responses.post(
        _api_url("/account/getUserSpending"),
        json=_success_response({"intervals": []}),
    )
    client = _make_client()
    assert client.get_spending(date(2026, 1, 1), date(2026, 3, 31)).intervals == ()


@responses.activate
def test_get_spending_sends_interval_param() -> None:
    responses.post(
        _api_url("/account/getUserSpending"),
        json=_success_response({"intervals": []}),
    )
    client = _make_client()
    client.get_spending(date(2026, 1, 1), date(2026, 3, 31), "WEEK")

    body = str(responses.calls[0].request.body)
    assert "intervalType=WEEK" in body


def test_get_spending_rejects_invalid_interval() -> None:
    client = _make_client()
    with pytest.raises(ValueError, match="Invalid interval"):
        client.get_spending(date(2026, 1, 1), date(2026, 3, 31), "month")

    with pytest.raises(ValueError, match="Invalid interval"):
        client.get_spending(date(2026, 1, 1), date(2026, 3, 31), "DAY")
