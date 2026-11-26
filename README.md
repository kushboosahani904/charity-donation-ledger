# Charity Donation Ledger

A Python command-line application for recording, validating and analysing charity donations. The core program uses the Python standard library and SQLite, so the ledger can run without installing third-party packages. Matplotlib is optional and is only needed for chart generation.

## Features
- Record, list, search and filter donation entries.
- Validate donor details, donation amounts and dates.
- Persist records in SQLite with transactions, integrity constraints, indexes, WAL mode and a busy timeout.
- Automatically migrate legacy `donations.json` data into SQLite when the database is first initialized.
- Search using normal text, fuzzy matching or regular expressions.
- Import and export CSV files with row-level validation feedback.
- Produce summary statistics, cause-wise totals, top donors and monthly donation trends.
- Analyse repeat donors, repeat-donor rate and the share represented by the largest cause.
- Flag possible duplicate donations for manual review; no records are deleted automatically.
- Write operational events to `ledger.log` with configurable log severity.
- Support both an interactive menu and non-interactive command-line operations.

## Requirements
- Python 3.9 or later.
- No third-party package is required for the core ledger.
- Optional: Matplotlib for charts.

Install optional chart support when internet access is available:

```bash
python -m pip install -r requirements-optional.txt
```

## Run the interactive menu

```bash
python main.py
```

## Non-interactive commands

```bash
python main.py --summary
python main.py --search "education" --cause Education
python main.py --export-csv donations_export.csv
python main.py --import-csv donations_to_import.csv
python main.py --chart
```

Common options:

```bash
python main.py --summary --db data/charity.db --log-level DEBUG
python main.py --search "DON-10" --regex --log-level INFO
```

Available log levels: `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL`.

## Configuration

Edit `config.json` to change the database filename, CSV/chart output filenames, validation limits and high-donation alert threshold. The default database is `charity_ledger.db`.

## CSV import format

The header must contain `donor,cause,amount,date`. The `method` and `note` columns are optional. Dates must use `YYYY-MM-DD`; future dates and invalid amounts are rejected with a row-specific message.

## Run tests

```bash
python -m pip install pytest
python -m pytest -q
```

The test suite covers validation, persistence, legacy JSON migration, fuzzy/regex search, summaries, CSV operations, SQLite indexes, advanced donor insights and CLI argument parsing.
