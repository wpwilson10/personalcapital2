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
    BenchmarkPerformance,
    Category,
    Holding,
    InvestmentPerformance,
    NetWorthEntry,
    PortfolioVsBenchmark,
    Transaction,
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
                    }
                ]
            }
        ),
    )
    client = _make_client()
    accounts = client.get_accounts()

    assert len(accounts) == 1
    assert isinstance(accounts[0], Account)
    assert accounts[0].user_account_id == 100
    assert accounts[0].name == "Checking"
    assert accounts[0].is_asset is True
    assert accounts[0].is_closed is False
    assert isinstance(accounts[0].created_at, date)


@responses.activate
def test_get_accounts_empty() -> None:
    responses.post(
        _api_url("/newaccount/getAccounts2"),
        json=_success_response({"accounts": []}),
    )
    client = _make_client()
    assert client.get_accounts() == []


@responses.activate
def test_get_accounts_api_error() -> None:
    responses.post(
        _api_url("/newaccount/getAccounts2"),
        json=_error_response("Session expired"),
    )
    client = _make_client()
    with pytest.raises(EmpowerAPIError, match="Session expired"):
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
                        "merchant": "Java Joe",
                        "transactionType": "Purchase",
                        "status": "posted",
                        "currency": "USD",
                    }
                ]
            }
        ),
    )
    client = _make_client()
    txns = client.get_transactions(date(2026, 1, 1), date(2026, 1, 31))

    assert len(txns) == 1
    assert isinstance(txns[0], Transaction)
    assert txns[0].date == date(2026, 1, 15)
    assert txns[0].amount == Decimal("42.5")
    assert txns[0].merchant == "Java Joe"


@responses.activate
def test_get_transactions_sends_date_params() -> None:
    responses.post(
        _api_url("/transaction/getUserTransactions"),
        json=_success_response({"transactions": []}),
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
        json=_success_response({"transactions": []}),
    )
    client = _make_client()
    assert client.get_transactions(date(2026, 1, 1), date(2026, 1, 31)) == []


# --- get_categories ---


@responses.activate
def test_get_categories_happy_path() -> None:
    responses.post(
        _api_url("/transaction/getUserTransactions"),
        json=_success_response(
            {
                "transactions": [
                    {
                        "userTransactionId": 1,
                        "userAccountId": 1,
                        "transactionDate": "2026-01-15",
                        "amount": 10.0,
                        "categoryId": 7,
                        "categoryName": "Groceries",
                        "categoryType": "EXPENSE",
                    },
                    {
                        "userTransactionId": 2,
                        "userAccountId": 1,
                        "transactionDate": "2026-01-16",
                        "amount": 20.0,
                        "categoryId": 7,
                        "categoryName": "Groceries",
                        "categoryType": "EXPENSE",
                    },
                ]
            }
        ),
    )
    client = _make_client()
    cats = client.get_categories(date(2026, 1, 1), date(2026, 1, 31))

    assert len(cats) == 1
    assert isinstance(cats[0], Category)
    assert cats[0].category_id == 7
    assert cats[0].name == "Groceries"
    assert cats[0].type == "EXPENSE"


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
                ]
            }
        ),
    )
    client = _make_client()
    holdings = client.get_holdings()

    assert len(holdings) == 1
    assert isinstance(holdings[0], Holding)
    assert holdings[0].ticker == "VTI"
    assert holdings[0].value == Decimal("12500")
    assert isinstance(holdings[0].snapshot_date, date)


@responses.activate
def test_get_holdings_empty() -> None:
    responses.post(
        _api_url("/invest/getHoldings"),
        json=_success_response({"holdings": []}),
    )
    client = _make_client()
    assert client.get_holdings() == []


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
                ]
            }
        ),
    )
    client = _make_client()
    nw = client.get_net_worth(date(2026, 3, 1), date(2026, 3, 31))

    assert len(nw) == 1
    assert isinstance(nw[0], NetWorthEntry)
    assert nw[0].date == date(2026, 3, 1)
    assert nw[0].networth == Decimal("150000")
    assert nw[0].total_assets == Decimal("200000")


@responses.activate
def test_get_net_worth_sends_date_params() -> None:
    responses.post(
        _api_url("/account/getHistories"),
        json=_success_response({"networthHistories": []}),
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
    bals = client.get_account_balances(date(2026, 3, 1), date(2026, 3, 31))

    assert len(bals) == 1
    assert isinstance(bals[0], AccountBalance)
    assert bals[0].date == date(2026, 3, 15)
    assert bals[0].user_account_id == 789
    assert bals[0].balance == Decimal("5432.1")


@responses.activate
def test_get_account_balances_empty() -> None:
    responses.post(
        _api_url("/account/getHistories"),
        json=_success_response({"histories": []}),
    )
    client = _make_client()
    assert client.get_account_balances(date(2026, 1, 1), date(2026, 1, 31)) == []


# --- get_investment_performance ---


@responses.activate
def test_get_investment_performance_happy_path() -> None:
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
                ]
            }
        ),
    )
    client = _make_client()
    perfs = client.get_investment_performance(date(2026, 1, 1), date(2026, 3, 31), [300])

    assert len(perfs) == 1
    assert isinstance(perfs[0], InvestmentPerformance)
    assert perfs[0].date == date(2026, 3, 15)
    assert perfs[0].user_account_id == 300
    assert perfs[0].performance == Decimal("0.0823")


@responses.activate
def test_get_investment_performance_sends_account_ids() -> None:
    responses.post(
        _api_url("/account/getPerformanceHistories"),
        json=_success_response({"performanceHistory": []}),
    )
    client = _make_client()
    client.get_investment_performance(date(2026, 1, 1), date(2026, 3, 31), [100, 200])

    body = str(responses.calls[0].request.body)
    # URL-encoded JSON array
    assert "userAccountIds" in body
    assert "100" in body
    assert "200" in body


# --- get_benchmark_performance ---


@responses.activate
def test_get_benchmark_performance_happy_path() -> None:
    responses.post(
        _api_url("/account/getPerformanceHistories"),
        json=_success_response(
            {
                "benchmarkPerformanceHistory": [
                    {
                        "date": "2026-03-15",
                        "^INX": 0.1245,
                    }
                ]
            }
        ),
    )
    client = _make_client()
    benchmarks = client.get_benchmark_performance(date(2026, 1, 1), date(2026, 3, 31), [300])

    assert len(benchmarks) == 1
    assert isinstance(benchmarks[0], BenchmarkPerformance)
    assert benchmarks[0].date == date(2026, 3, 15)
    assert benchmarks[0].benchmark == "^INX"
    assert benchmarks[0].performance == Decimal("0.1245")


@responses.activate
def test_get_benchmark_performance_empty() -> None:
    responses.post(
        _api_url("/account/getPerformanceHistories"),
        json=_success_response({"benchmarkPerformanceHistory": []}),
    )
    client = _make_client()
    assert client.get_benchmark_performance(date(2026, 1, 1), date(2026, 3, 31), [300]) == []


# --- get_performance_and_benchmarks (combined) ---


@responses.activate
def test_get_performance_and_benchmarks_single_call() -> None:
    """Combined method should fetch both from a single API call."""
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
            }
        ),
    )
    client = _make_client()
    perfs, benchmarks = client.get_performance_and_benchmarks(
        date(2026, 1, 1), date(2026, 3, 31), [300]
    )

    # Only one API call should have been made
    assert len(responses.calls) == 1

    assert len(perfs) == 1
    assert perfs[0].performance == Decimal("0.0823")

    assert len(benchmarks) == 1
    assert benchmarks[0].benchmark == "^INX"
    assert benchmarks[0].performance == Decimal("0.1245")


# --- get_portfolio_vs_benchmark ---


@responses.activate
def test_get_portfolio_vs_benchmark_happy_path() -> None:
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
                ]
            }
        ),
    )
    client = _make_client()
    pvb = client.get_portfolio_vs_benchmark(date(2026, 1, 1), date(2026, 3, 31))

    assert len(pvb) == 1
    assert isinstance(pvb[0], PortfolioVsBenchmark)
    assert pvb[0].date == date(2026, 3, 15)
    assert pvb[0].portfolio_value == Decimal("105.5")
    assert pvb[0].sp500_value == Decimal("103.2")


@responses.activate
def test_get_portfolio_vs_benchmark_sends_date_params() -> None:
    responses.post(
        _api_url("/invest/getQuotes"),
        json=_success_response({"histories": []}),
    )
    client = _make_client()
    client.get_portfolio_vs_benchmark(date(2026, 1, 1), date(2026, 6, 30))

    body = str(responses.calls[0].request.body)
    assert "startDate=2026-01-01" in body
    assert "endDate=2026-06-30" in body


@responses.activate
def test_get_portfolio_vs_benchmark_api_error() -> None:
    responses.post(
        _api_url("/invest/getQuotes"),
        json=_error_response("Invalid request"),
    )
    client = _make_client()
    with pytest.raises(EmpowerAPIError, match="Invalid request"):
        client.get_portfolio_vs_benchmark(date(2026, 1, 1), date(2026, 3, 31))
