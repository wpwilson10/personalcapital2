"""Tests for the history parser."""

from personalcapital2.parsers.history import parse_account_balances, parse_net_worth


def test_parse_net_worth() -> None:
    response = {
        "spData": {
            "networthHistories": [
                {
                    "date": "2026-03-14",
                    "networth": 789760.45,
                    "totalAssets": 791020.76,
                    "totalLiabilities": 1260.32,
                    "totalCash": 16762.64,
                    "totalInvestment": 774258.12,
                    "totalCredit": 1260.32,
                    "totalMortgage": 0.0,
                    "totalLoan": 0.0,
                    "totalOtherAssets": 0.0,
                    "totalOtherLiabilities": 0.0,
                    "oneDayNetworthChange": -2916.69,
                    "oneDayNetworthPercentageChange": -0.37,
                    "totalEmpower": 0.0,
                },
            ]
        }
    }
    rows = parse_net_worth(response, "2026-03-14T10:00:00")
    assert len(rows) == 1
    row = rows[0]
    assert row["date"] == "2026-03-14"
    assert row["networth"] == 789760.45
    assert row["total_assets"] == 791020.76
    assert row["total_liabilities"] == 1260.32
    assert row["total_cash"] == 16762.64
    assert row["total_investment"] == 774258.12
    assert row["synced_at"] == "2026-03-14T10:00:00"


def test_parse_account_balances_filters_annotations() -> None:
    response = {
        "spData": {
            "histories": [
                {
                    "date": "2026-03-14",
                    "aggregateBalance": 100000.0,
                    "balances": {
                        "305886794": 50000.0,
                        "305886753": 25000.0,
                        "305886753Annotation": "Accurate data unavailable for this day",
                        "aggregateAnnotation": "Balances are approximate",
                    },
                },
            ]
        }
    }
    rows = parse_account_balances(response, "2026-03-14T10:00:00")
    assert len(rows) == 2

    ids = {r["user_account_id"] for r in rows}
    assert ids == {305886794, 305886753}

    for row in rows:
        assert row["date"] == "2026-03-14"
        assert row["synced_at"] == "2026-03-14T10:00:00"
        assert isinstance(row["balance"], float)


def test_malformed_balance_entry_skipped_not_crash() -> None:
    """A balance entry with a non-numeric value is skipped, not crash."""
    response = {
        "spData": {
            "histories": [
                {
                    "date": "2026-03-14",
                    "balances": {
                        "305886794": "not_a_number",
                    },
                },
                {
                    "date": "2026-03-14",
                    "balances": {
                        "305886753": 25000.0,
                    },
                },
            ]
        }
    }
    rows = parse_account_balances(response, "2026-03-14T10:00:00")
    # The entry with non-numeric balance should be skipped, the valid one kept
    assert len(rows) == 1
    assert rows[0]["user_account_id"] == 305886753
    assert rows[0]["balance"] == 25000.0


def test_empty_histories() -> None:
    response: dict[str, object] = {"spData": {"networthHistories": [], "histories": []}}
    assert parse_net_worth(response, "2026-03-14T10:00:00") == []
    assert parse_account_balances(response, "2026-03-14T10:00:00") == []
