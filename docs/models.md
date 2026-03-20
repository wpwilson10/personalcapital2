# Model Reference

All convenience methods return frozen dataclasses. Dates are `datetime.date`, financial values are `decimal.Decimal`, and optional fields are `None` when absent.

## Account

Returned by `client.get_accounts()`.

| Field | Type |
|---|---|
| `user_account_id` | `int` |
| `account_id` | `str` |
| `name` | `str` |
| `firm_name` | `str` |
| `account_type` | `str` |
| `account_type_group` | `str \| None` |
| `product_type` | `str` |
| `currency` | `str` |
| `is_asset` | `bool` |
| `is_closed` | `bool` |
| `created_at` | `date \| None` |

## Transaction

Returned by `client.get_transactions(start, end)`.

| Field | Type |
|---|---|
| `user_transaction_id` | `int` |
| `user_account_id` | `int` |
| `date` | `date` |
| `amount` | `Decimal` |
| `is_cash_in` | `bool` |
| `is_income` | `bool` |
| `is_spending` | `bool` |
| `description` | `str` |
| `original_description` | `str \| None` |
| `simple_description` | `str \| None` |
| `category_id` | `int \| None` |
| `merchant` | `str \| None` |
| `transaction_type` | `str \| None` |
| `status` | `str \| None` |
| `currency` | `str` |

## Category

Returned by `client.get_categories(start, end)`.

| Field | Type |
|---|---|
| `category_id` | `int` |
| `name` | `str` |
| `type` | `str` |

## Holding

Returned by `client.get_holdings()`.

| Field | Type |
|---|---|
| `snapshot_date` | `date` |
| `user_account_id` | `int` |
| `ticker` | `str \| None` |
| `cusip` | `str \| None` |
| `description` | `str` |
| `quantity` | `Decimal` |
| `price` | `Decimal` |
| `value` | `Decimal` |
| `holding_type` | `str \| None` |
| `security_type` | `str \| None` |
| `holding_percentage` | `Decimal \| None` |
| `source` | `str \| None` |

## NetWorthEntry

Returned by `client.get_net_worth(start, end)`.

| Field | Type |
|---|---|
| `date` | `date` |
| `networth` | `Decimal` |
| `total_assets` | `Decimal` |
| `total_liabilities` | `Decimal` |
| `total_cash` | `Decimal` |
| `total_investment` | `Decimal` |
| `total_credit` | `Decimal` |
| `total_mortgage` | `Decimal` |
| `total_loan` | `Decimal` |
| `total_other_assets` | `Decimal` |
| `total_other_liabilities` | `Decimal` |

## AccountBalance

Returned by `client.get_account_balances(start, end)`.

| Field | Type |
|---|---|
| `date` | `date` |
| `user_account_id` | `int` |
| `balance` | `Decimal` |

## InvestmentPerformance

Returned by `client.get_investment_performance(start, end, account_ids)`.

| Field | Type |
|---|---|
| `date` | `date` |
| `user_account_id` | `int` |
| `performance` | `Decimal \| None` |

## BenchmarkPerformance

Returned by `client.get_benchmark_performance(start, end, account_ids)`.

| Field | Type |
|---|---|
| `date` | `date` |
| `benchmark` | `str` |
| `performance` | `Decimal` |

## PortfolioVsBenchmark

Returned by `client.get_portfolio_vs_benchmark(start, end)`.

| Field | Type |
|---|---|
| `date` | `date` |
| `portfolio_value` | `Decimal \| None` |
| `sp500_value` | `Decimal \| None` |
