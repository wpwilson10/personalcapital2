# Model Reference

All convenience methods return frozen dataclasses. Dates are `datetime.date`, financial values are `decimal.Decimal`, and optional fields are `None` when absent.

## Response Containers

Methods return container objects that group related data from a single API call.

### AccountsResult

Returned by `client.get_accounts()`.

| Field | Type |
|---|---|
| `accounts` | `tuple[Account, ...]` |
| `summary` | `AccountsSummary` |

### TransactionsResult

Returned by `client.get_transactions(start, end)`.

| Field | Type |
|---|---|
| `transactions` | `tuple[Transaction, ...]` |
| `categories` | `tuple[Category, ...]` |
| `summary` | `TransactionsSummary` |

### HoldingsResult

Returned by `client.get_holdings()`.

| Field | Type |
|---|---|
| `holdings` | `tuple[Holding, ...]` |
| `total_value` | `Decimal` |

### NetWorthResult

Returned by `client.get_net_worth(start, end)`.

| Field | Type |
|---|---|
| `entries` | `tuple[NetWorthEntry, ...]` |
| `summary` | `NetWorthSummary` |

### AccountBalancesResult

Returned by `client.get_account_balances(start, end)`.

| Field | Type |
|---|---|
| `balances` | `tuple[AccountBalance, ...]` |
| `summary` | `AccountBalancesSummary` |

### PerformanceResult

Returned by `client.get_performance(start, end, account_ids)`.

| Field | Type |
|---|---|
| `investments` | `tuple[InvestmentPerformance, ...]` |
| `benchmarks` | `tuple[BenchmarkPerformance, ...]` |
| `account_summaries` | `tuple[AccountPerformanceSummary, ...]` |

### QuotesResult

Returned by `client.get_quotes(start, end)`.

| Field | Type |
|---|---|
| `portfolio_vs_benchmark` | `tuple[PortfolioVsBenchmark, ...]` |
| `snapshot` | `PortfolioSnapshot` |
| `market_quotes` | `tuple[MarketQuote, ...]` |

### SpendingResult

Returned by `client.get_spending(start, end, interval)`.

| Field | Type |
|---|---|
| `intervals` | `tuple[SpendingSummary, ...]` |

## Data Models

### Account

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
| `balance` | `Decimal \| None` |
| `available_cash` | `Decimal \| None` |
| `account_type_subtype` | `str \| None` |
| `last_refreshed` | `date \| None` |
| `oldest_transaction_date` | `date \| None` |
| `advisory_fee_percentage` | `Decimal \| None` |
| `fees_per_year` | `Decimal \| None` |
| `fund_fees` | `Decimal \| None` |
| `total_fee` | `Decimal \| None` |

### Transaction

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
| `merchant_id` | `str \| None` |
| `merchant_type` | `str \| None` |
| `transaction_type` | `str \| None` |
| `sub_type` | `str \| None` |
| `status` | `str \| None` |
| `currency` | `str` |
| `is_duplicate` | `bool` |

### Category

| Field | Type |
|---|---|
| `category_id` | `int` |
| `name` | `str` |
| `type` | `str` |

### Holding

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
| `cost_basis` | `Decimal \| None` |
| `one_day_percent_change` | `Decimal \| None` |
| `one_day_value_change` | `Decimal \| None` |
| `fees_per_year` | `Decimal \| None` |
| `fund_fees` | `Decimal \| None` |

### NetWorthEntry

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

### AccountBalance

Returned via `AccountBalancesResult.balances` from `client.get_account_balances(start, end)`.

| Field | Type |
|---|---|
| `date` | `date` |
| `user_account_id` | `int` |
| `balance` | `Decimal` |

### InvestmentPerformance

| Field | Type |
|---|---|
| `date` | `date` |
| `user_account_id` | `int` |
| `performance` | `Decimal \| None` |

### BenchmarkPerformance

| Field | Type |
|---|---|
| `date` | `date` |
| `benchmark` | `str` |
| `performance` | `Decimal` |

### PortfolioVsBenchmark

| Field | Type |
|---|---|
| `date` | `date` |
| `portfolio_value` | `Decimal \| None` |
| `sp500_value` | `Decimal \| None` |

## Summary Models

### AccountsSummary

| Field | Type |
|---|---|
| `networth` | `Decimal` |
| `assets` | `Decimal` |
| `liabilities` | `Decimal` |
| `cash_total` | `Decimal` |
| `investment_total` | `Decimal` |
| `credit_card_total` | `Decimal` |
| `mortgage_total` | `Decimal` |
| `loan_total` | `Decimal` |
| `other_asset_total` | `Decimal` |
| `other_liabilities_total` | `Decimal` |

### TransactionsSummary

| Field | Type |
|---|---|
| `money_in` | `Decimal` |
| `money_out` | `Decimal` |
| `net_cashflow` | `Decimal` |
| `average_in` | `Decimal` |
| `average_out` | `Decimal` |
| `start_date` | `date` |
| `end_date` | `date` |

### AccountBalancesSummary

Computed from parsed balance data (the API does not provide a pre-computed summary for this endpoint).

| Field | Type |
|---|---|
| `account_count` | `int` |
| `latest_date` | `date \| None` |
| `latest_total` | `Decimal` |

### NetWorthSummary

| Field | Type |
|---|---|
| `date_range_change` | `Decimal` |
| `date_range_percentage_change` | `Decimal` |
| `cash_change` | `Decimal` |
| `cash_percentage_change` | `Decimal` |
| `investment_change` | `Decimal` |
| `investment_percentage_change` | `Decimal` |
| `credit_change` | `Decimal` |
| `credit_percentage_change` | `Decimal` |
| `mortgage_change` | `Decimal` |
| `mortgage_percentage_change` | `Decimal` |
| `loan_change` | `Decimal` |
| `loan_percentage_change` | `Decimal` |
| `other_assets_change` | `Decimal` |
| `other_assets_percentage_change` | `Decimal` |
| `other_liabilities_change` | `Decimal` |
| `other_liabilities_percentage_change` | `Decimal` |

### AccountPerformanceSummary

| Field | Type |
|---|---|
| `user_account_id` | `int` |
| `account_name` | `str` |
| `site_name` | `str` |
| `current_balance` | `Decimal` |
| `percent_of_total` | `Decimal` |
| `income` | `Decimal` |
| `expense` | `Decimal` |
| `cash_flow` | `Decimal` |
| `one_day_balance_value_change` | `Decimal` |
| `one_day_balance_percentage_change` | `Decimal` |
| `date_range_balance_value_change` | `Decimal` |
| `date_range_balance_percentage_change` | `Decimal` |
| `date_range_performance_value_change` | `Decimal` |
| `one_day_performance_value_change` | `Decimal` |
| `balance_as_of_end_date` | `Decimal` |
| `closed_date` | `date \| None` |

### PortfolioSnapshot

| Field | Type |
|---|---|
| `last` | `Decimal` |
| `change` | `Decimal` |
| `percent_change` | `Decimal` |

### MarketQuote

| Field | Type |
|---|---|
| `ticker` | `str` |
| `last` | `Decimal` |
| `change` | `Decimal` |
| `percent_change` | `Decimal` |
| `long_name` | `str` |
| `date` | `date` |

### SpendingDetail

| Field | Type |
|---|---|
| `date` | `date` |
| `amount` | `Decimal` |

### SpendingSummary

Returned by `client.get_spending(start, end, interval)`.

| Field | Type |
|---|---|
| `type` | `str` |
| `average` | `Decimal \| None` |
| `current` | `Decimal` |
| `target` | `Decimal` |
| `details` | `tuple[SpendingDetail, ...]` |
