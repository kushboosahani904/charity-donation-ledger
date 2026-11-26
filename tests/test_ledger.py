import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ledger_logic import (
    check_threshold_warnings,
    export_to_csv,
    generate_next_id,
    get_summary,
    import_from_csv,
    is_valid_amount,
    is_valid_date,
    load_records,
    save_records,
    search_records,
)


def test_amount_validation():
    assert is_valid_amount("500") == 500.0
    assert is_valid_amount("₹1,250.50") == 1250.5
    assert is_valid_amount("-10") is None
    assert is_valid_amount("0") is None
    assert is_valid_amount("abc") is None


def test_date_validation():
    assert is_valid_date("2026-10-15") == "2026-10-15"
    assert is_valid_date("15-10-2026") is None
    assert is_valid_date("2099-01-01") is None
    assert is_valid_date("invalid") is None


def test_generate_next_id():
    sample = [{"id": "DON-101"}, {"id": "DON-105"}]
    assert generate_next_id(sample) == "DON-106"
    assert generate_next_id([]) == "DON-101"


def test_save_and_load_persistence(tmp_path):
    target = tmp_path / "test_donations.json"
    records = [
        {
            "id": "DON-101",
            "donor": "Asha",
            "cause": "Education",
            "amount": 300.0,
            "date": "2026-10-10",
            "method": "UPI",
            "note": "Books",
        }
    ]
    save_records(records, str(target))
    loaded, notice = load_records(str(target))
    assert notice is None
    assert len(loaded) == 1
    assert loaded[0]["donor"] == "Asha"


def test_corrupted_file_recovery(tmp_path):
    broken = tmp_path / "broken.json"
    broken.write_text("{not valid json", encoding="utf-8")
    loaded, notice = load_records(str(broken))
    assert len(loaded) > 0
    assert "corrupted" in notice.lower()


def test_fuzzy_and_regex_search():
    records = [
        {
            "id": "DON-101",
            "donor": "Rohan Verma",
            "cause": "Education",
            "amount": 500.0,
            "date": "2026-10-10",
            "method": "UPI",
            "note": "",
        },
        {
            "id": "DON-102",
            "donor": "Ananya Iyer",
            "cause": "Food Relief",
            "amount": 800.0,
            "date": "2026-10-14",
            "method": "Cash",
            "note": "",
        },
    ]
    fuzzy = search_records(records, keyword="educaton")
    assert len(fuzzy) == 1
    assert fuzzy[0]["id"] == "DON-101"

    regex_hits = search_records(records, keyword=r"\bDON-102\b", use_regex=True)
    assert len(regex_hits) == 1
    assert regex_hits[0]["donor"] == "Ananya Iyer"

def test_summary_and_threshold_alerts():
    records = [
        {
            "id": "DON-101",
            "donor": "A",
            "cause": "Health",
            "amount": 200.0,
            "date": "2026-10-10",
            "method": "UPI",
            "note": "",
        },
        {
            "id": "DON-102",
            "donor": "B",
            "cause": "Health",
            "amount": 6000.0,
            "date": "2026-10-11",
            "method": "Card",
            "note": "",
        },
    ]
    summary = get_summary(records)
    assert summary["count"] == 2
    assert summary["total"] == 6200.0
    assert summary["average"] == 3100.0
    assert summary["high_value_count"] == 1
    assert len(check_threshold_warnings(records[1])) == 1


def test_csv_export_and_import(tmp_path):
    csv_file = tmp_path / "bulk.csv"
    csv_file.write_text(
        "donor,cause,amount,date,method,note\n"
        "Kiran,Clean Water,450,2026-10-12,UPI,Filter\n"
        "BadRow,Clean Water,-50,2026-10-12,UPI,Invalid\n",
        encoding="utf-8",
    )
    records = []
    added, errors = import_from_csv(str(csv_file), records)
    assert added == 1
    assert len(errors) == 1

    out_csv = tmp_path / "out.csv"
    export_to_csv(records, str(out_csv))
    assert out_csv.exists()

def test_sqlite_persistence_and_schema(tmp_path, monkeypatch):
    import ledger_logic

    db_path = tmp_path / "ledger.db"
    monkeypatch.setitem(ledger_logic.CONFIG, "database_file", str(db_path))
    monkeypatch.setitem(ledger_logic.CONFIG, "storage_backend", "sqlite")
    records = [{
        "id": "DON-201", "donor": "Meera", "cause": "Health",
        "amount": 750.0, "date": "2026-10-12", "method": "UPI", "note": "Medicine"
    }]
    save_records(records)
    loaded, notice = load_records()
    assert notice is None
    assert loaded == records

    import sqlite3
    with sqlite3.connect(db_path) as connection:
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(donations)")}
    assert "idx_donations_date" in indexes
    assert "idx_donations_cause" in indexes


def test_sqlite_migrates_legacy_json_once(tmp_path, monkeypatch):
    import ledger_logic

    legacy_path = tmp_path / "legacy.json"
    db_path = tmp_path / "ledger.db"
    records = [{
        "id": "DON-301", "donor": "Arjun", "cause": "Education",
        "amount": 400.0, "date": "2026-10-12", "method": "Cash", "note": "Books"
    }]
    legacy_path.write_text(__import__("json").dumps(records), encoding="utf-8")
    monkeypatch.setitem(ledger_logic.CONFIG, "data_file", str(legacy_path))
    monkeypatch.setitem(ledger_logic.CONFIG, "database_file", str(db_path))
    monkeypatch.setitem(ledger_logic.CONFIG, "storage_backend", "sqlite")
    loaded, notice = load_records()
    assert loaded == records
    assert "migrated" in notice.lower()
    loaded_again, notice_again = load_records()
    assert loaded_again == records
    assert notice_again is None


def test_advanced_insights_rankings_trends_and_duplicates():
    from ledger_logic import get_advanced_insights

    records = [
        {"id": "DON-1", "donor": "Asha", "cause": "Health", "amount": 500.0, "date": "2026-10-10"},
        {"id": "DON-2", "donor": "Asha", "cause": "Health", "amount": 500.0, "date": "2026-10-10"},
        {"id": "DON-3", "donor": "Ravi", "cause": "Education", "amount": 300.0, "date": "2026-11-02"},
    ]
    insights = get_advanced_insights(records)
    assert insights["top_donors"][0]["donor"] == "Asha"
    assert insights["top_donors"][0]["total"] == 1000.0
    assert insights["monthly_totals"] == [
        {"month": "2026-10", "total": 1000.0},
        {"month": "2026-11", "total": 300.0},
    ]
    assert insights["possible_duplicates"] == [["DON-1", "DON-2"]]


def test_advanced_insights_repeat_donor_and_cause_concentration():
    from ledger_logic import get_advanced_insights

    records = [
        {"id": "DON-1", "donor": "Asha", "cause": "Health", "amount": 600.0, "date": "2026-10-10"},
        {"id": "DON-2", "donor": "Asha", "cause": "Education", "amount": 400.0, "date": "2026-11-10"},
        {"id": "DON-3", "donor": "Ravi", "cause": "Health", "amount": 1000.0, "date": "2026-11-11"},
    ]
    result = get_advanced_insights(records)
    assert result["repeat_donor_rate"] == 50.0
    assert result["repeat_donors"][0]["donor"] == "Asha"
    assert result["largest_cause"] == "Health"
    assert result["largest_cause_share"] == 80.0


def test_cli_parser_supports_noninteractive_commands():
    from main import build_parser

    args = build_parser().parse_args(["--summary", "--db", "test.db", "--log-level", "DEBUG"])
    assert args.summary is True
    assert args.db == "test.db"
    assert args.log_level == "DEBUG"


def test_configure_logging_rejects_unknown_level():
    import pytest
    from ledger_logic import configure_logging

    with pytest.raises(ValueError):
        configure_logging("LOUD")
