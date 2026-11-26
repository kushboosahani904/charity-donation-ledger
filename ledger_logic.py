import csv
import json
import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from difflib import SequenceMatcher

DEFAULT_CONFIG = {
    "data_file": "donations.json",
    "database_file": "charity_ledger.db",
    "storage_backend": "sqlite",
    "csv_export_file": "summary_report.csv",
    "chart_file": "donations_chart.png",
    "log_file": "ledger.log",
    "min_amount": 1.0,
    "max_amount": 1000000.0,
    "high_donation_threshold": 5000.0,
}


def load_config(config_path="config.json"):
    config = DEFAULT_CONFIG.copy()
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
            if isinstance(user_cfg, dict):
                config.update(user_cfg)
        except (OSError, json.JSONDecodeError):
            pass
    return config


CONFIG = load_config()


def setup_logger(log_file=None, level=None):
    """Configure one reusable application logger with a selectable severity level."""
    target_log = log_file or CONFIG["log_file"]
    app_logger = logging.getLogger("charity_ledger")
    selected_level = getattr(logging, str(level or CONFIG.get("log_level", "INFO")).upper(), logging.INFO)
    app_logger.setLevel(selected_level)
    app_logger.propagate = False
    if not app_logger.handlers:
        handler = logging.FileHandler(target_log, encoding="utf-8")
        formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        handler.setFormatter(formatter)
        app_logger.addHandler(handler)
    return app_logger


def configure_logging(level="INFO", log_file=None):
    """Change the log level at runtime; accepted values are DEBUG, INFO, WARNING, ERROR."""
    global logger
    normalized = str(level).upper()
    if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("Invalid log level. Choose DEBUG, INFO, WARNING, ERROR, or CRITICAL.")
    logger = setup_logger(log_file=log_file, level=normalized)
    return logger


logger = setup_logger()


@contextmanager
def file_lock(target_path):
    """Lightweight lock file context manager to prevent concurrent write collisions."""
    lock_path = f"{target_path}.lock"
    acquired = False
    try:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            acquired = True
        except FileExistsError:
            # Stale lock fallback if a previous run crashed
            acquired = False
        yield
    finally:
        if acquired and os.path.exists(lock_path):
            try:
                os.remove(lock_path)
            except OSError:
                pass


def sanitize_filename(filename, default_name, allow_subdir=False):
    """Sanitize a filename while optionally keeping a safe directory path for tests/exports."""
    raw = str(filename).strip()
    if not raw:
        return default_name
    if allow_subdir:
        normalized = os.path.normpath(raw)
        if normalized in {"", ".", ".."}:
            return default_name
        return normalized
    cleaned = os.path.basename(raw)
    if not cleaned or cleaned in {".", ".."}:
        return default_name
    return cleaned


def get_sample_data():
    return [
        {
            "id": "DON-101",
            "donor": "Rohan Verma",
            "cause": "Education",
            "amount": 500.0,
            "date": "2026-10-10",
            "method": "UPI",
            "note": "Notebook drive",
        },
        {
            "id": "DON-102",
            "donor": "Ananya Iyer",
            "cause": "Food Relief",
            "amount": 800.0,
            "date": "2026-10-14",
            "method": "Cash",
            "note": "Lunch packets",
        },
        {
            "id": "DON-103",
            "donor": "Karthik Reddy",
            "cause": "Clean Water",
            "amount": 1200.0,
            "date": "2026-10-20",
            "method": "Card",
            "note": "Water filters",
        },
        {
            "id": "DON-104",
            "donor": "Sneha Gupta",
            "cause": "Education",
            "amount": 350.0,
            "date": "2026-11-02",
            "method": "UPI",
            "note": "",
        },
        {
            "id": "DON-105",
            "donor": "Vikram Rao",
            "cause": "Medical Aid",
            "amount": 1500.0,
            "date": "2026-11-11",
            "method": "Bank Transfer",
            "note": "First-aid kits",
        },
        {
            "id": "DON-106",
            "donor": "Pooja Nair",
            "cause": "Food Relief",
            "amount": 450.0,
            "date": "2026-11-18",
            "method": "UPI",
            "note": "Grain bags",
        },
    ]


def is_valid_amount(text, min_amt=None, max_amt=None):
    low = CONFIG["min_amount"] if min_amt is None else min_amt
    high = CONFIG["max_amount"] if max_amt is None else max_amt

    cleaned = str(text).strip().replace(",", "").replace("₹", "").replace("$", "")
    try:
        value = float(cleaned)
    except ValueError:
        return None

    if value != value or value < low or value > high:
        return None

    return round(value, 2)


def is_valid_date(date_text):
    text = str(date_text).strip()
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None

    if parsed > datetime.today().date():
        return None

    return parsed.strftime("%Y-%m-%d")


def generate_next_id(records):
    highest = 100
    for item in records:
        rec_id = str(item.get("id", ""))
        if rec_id.startswith("DON-"):
            num_part = rec_id[4:]
            if num_part.isdigit():
                num = int(num_part)
                if num > highest:
                    highest = num
    return f"DON-{highest + 1}"


def check_threshold_warnings(record, threshold=None):
    limit = CONFIG["high_donation_threshold"] if threshold is None else threshold
    warnings = []
    if record["amount"] >= limit:
        warnings.append(
            f"High-value donation alert: {record['id']} is {record['amount']:.2f} (threshold: {limit:.2f})."
        )
    return warnings


def _connect_database(database_path=None):
    """Open the SQLite store and ensure its schema and indexes exist."""
    target = database_path or CONFIG.get("database_file", "charity_ledger.db")
    connection = sqlite3.connect(target, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 10000")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("""CREATE TABLE IF NOT EXISTS donations (
        id TEXT PRIMARY KEY,
        donor TEXT NOT NULL CHECK(length(trim(donor)) > 0),
        cause TEXT NOT NULL CHECK(length(trim(cause)) > 0),
        amount REAL NOT NULL CHECK(amount > 0 AND amount <= 1000000),
        date TEXT NOT NULL,
        method TEXT NOT NULL DEFAULT 'Cash',
        note TEXT NOT NULL DEFAULT ''
    )""")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_donations_date ON donations(date)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_donations_cause ON donations(cause)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_donations_donor ON donations(donor COLLATE NOCASE)")
    return connection


def _save_sqlite(records, database_path=None):
    target = database_path or CONFIG.get("database_file", "charity_ledger.db")
    with _connect_database(target) as connection:
        connection.execute("DELETE FROM donations")
        connection.executemany(
            """INSERT INTO donations(id, donor, cause, amount, date, method, note)
               VALUES(:id, :donor, :cause, :amount, :date, :method, :note)""",
            records,
        )
    logger.info("Saved %d records to SQLite database %s", len(records), target)


def _load_sqlite(database_path=None):
    target = database_path or CONFIG.get("database_file", "charity_ledger.db")
    with _connect_database(target) as connection:
        rows = connection.execute(
            "SELECT id, donor, cause, amount, date, method, note FROM donations ORDER BY date, id"
        ).fetchall()
    return [dict(row) for row in rows]


def save_records(records, filename=None):
    # Explicit filenames retain the JSON interface used by imports and tests.
    if filename is None and CONFIG.get("storage_backend", "sqlite").lower() == "sqlite":
        _save_sqlite(records)
        return
    target = filename or CONFIG["data_file"]
    temp_file = f"{target}.tmp"
    with file_lock(target):
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(records, f, indent=2)
        os.replace(temp_file, target)
    logger.info("Saved %d records to %s", len(records), target)


def load_records(filename=None):
    if filename is None and CONFIG.get("storage_backend", "sqlite").lower() == "sqlite":
        database_path = CONFIG.get("database_file", "charity_ledger.db")
        try:
            existing = _load_sqlite(database_path)
            if existing:
                return existing, None
            # One-time migration: import the legacy JSON file when the database is empty.
            legacy_path = CONFIG.get("data_file", "donations.json")
            if os.path.exists(legacy_path):
                legacy_records, notice = load_records(legacy_path)
                if legacy_records:
                    _save_sqlite(legacy_records, database_path)
                    return legacy_records, "Migrated existing JSON donation records to SQLite."
            sample = get_sample_data()
            _save_sqlite(sample, database_path)
            return sample, "Initialized the SQLite database with sample donation records."
        except (sqlite3.Error, OSError) as exc:
            logger.exception("SQLite storage could not be loaded")
            return [], f"Database error: {exc}. Check database permissions and try again."
    target = filename or CONFIG["data_file"]
    if not os.path.exists(target):
        sample = get_sample_data()
        save_records(sample, target)
        logger.warning("Data file '%s' missing; initialized sample records.", target)
        return sample, "No save file found. Created a new file with sample records."

    try:
        with open(target, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        sample = get_sample_data()
        save_records(sample, target)
        logger.error("Corrupted data file '%s' (%s); reset to sample records.", target, exc)
        return sample, "Data file was unreadable or corrupted. Loaded fresh sample records."

    if not isinstance(data, list):
        sample = get_sample_data()
        save_records(sample, target)
        logger.error("Invalid JSON root in '%s'; reset to sample records.", target)
        return sample, "Data format was invalid. Loaded fresh sample records."

    valid_records = []
    skipped = 0

    for item in data:
        if not isinstance(item, dict):
            skipped += 1
            continue

        donor = str(item.get("donor", "")).strip()
        cause = str(item.get("cause", "")).strip()
        method = str(item.get("method", "Cash")).strip() or "Cash"
        note = str(item.get("note", "")).strip()
        rec_id = str(item.get("id", "")).strip()

        amt = is_valid_amount(str(item.get("amount", "")))
        dt = is_valid_date(str(item.get("date", "")))

        if donor and cause and rec_id and amt is not None and dt is not None:
            valid_records.append(
                {
                    "id": rec_id,
                    "donor": donor,
                    "cause": cause,
                    "amount": amt,
                    "date": dt,
                    "method": method,
                    "note": note,
                }
            )
        else:
            skipped += 1

    msg = None
    if skipped > 0:
        logger.warning("Skipped %d invalid entries while loading '%s'.", skipped, target)
        msg = f"Loaded {len(valid_records)} records (skipped {skipped} invalid entries)."
    else:
        logger.info("Loaded %d valid records from '%s'.", len(valid_records), target)
    return valid_records, msg


def _is_fuzzy_match(query, text, cutoff=0.65):
    if not query:
        return True
    if query in text:
        return True
    for word in text.split():
        if query in word or word in query:
            return True
        if SequenceMatcher(None, query, word).ratio() >= cutoff:
            return True
    return False


def search_records(records, keyword="", cause="", use_regex=False):
    kw = keyword.strip()
    cs = cause.strip().lower()
    matches = []

    compiled_pattern = None
    if kw and use_regex:
        try:
            compiled_pattern = re.compile(kw, re.IGNORECASE)
        except re.error:
            logger.warning("Invalid regex pattern '%s'; falling back to text search.", kw)
            compiled_pattern = None

    for item in records:
        if cs and item["cause"].lower() != cs:
            continue

        if kw:
            combined = (
                f"{item['id']} {item['donor']} {item['cause']} "
                f"{item['method']} {item['note']}"
            )
            if compiled_pattern is not None:
                if not compiled_pattern.search(combined):
                    continue
            else:
                if not _is_fuzzy_match(kw.lower(), combined.lower()):
                    continue

        matches.append(item)

    return matches


def import_from_csv(csv_path, existing_records):
    """Bulk import rows from CSV with row-by-row validation error reporting."""
    if not os.path.exists(csv_path):
        return 0, [f"File not found: '{csv_path}'"]

    added = 0
    errors = []

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row_num, row in enumerate(reader, start=2):
            donor = str(row.get("donor", "")).strip()
            cause = str(row.get("cause", "")).strip()
            amt = is_valid_amount(str(row.get("amount", "")))
            dt = is_valid_date(str(row.get("date", "")))
            method = str(row.get("method", "UPI")).strip() or "UPI"
            note = str(row.get("note", "")).strip()

            if not donor or not cause or amt is None or dt is None:
                errors.append(f"Row {row_num}: invalid donor, cause, amount, or date.")
                continue

            new_rec = {
                "id": generate_next_id(existing_records),
                "donor": donor,
                "cause": cause,
                "amount": amt,
                "date": dt,
                "method": method,
                "note": note,
            }
            existing_records.append(new_rec)
            added += 1

    logger.info("Bulk CSV import from '%s': %d added, %d errors.", csv_path, added, len(errors))
    return added, errors


def get_summary(records):
    count = len(records)
    total = 0.0
    cause_totals = {}
    cause_counts = {}
    high_value_records = []

    highest_item = None
    lowest_item = None
    threshold = CONFIG["high_donation_threshold"]

    for item in records:
        amt = item["amount"]
        cause = item["cause"]

        total += amt
        cause_totals[cause] = cause_totals.get(cause, 0.0) + amt
        cause_counts[cause] = cause_counts.get(cause, 0) + 1

        if amt >= threshold:
            high_value_records.append(item)

        if highest_item is None or amt > highest_item["amount"]:
            highest_item = item
        if lowest_item is None or amt < lowest_item["amount"]:
            lowest_item = item

    average = total / count if count > 0 else 0.0
    sorted_causes = sorted(cause_totals.items(), key=lambda pair: pair[1], reverse=True)

    cause_rows = []
    for cause_name, cause_sum in sorted_causes:
        share = (cause_sum / total * 100) if total > 0 else 0.0
        cause_rows.append(
            {
                "cause": cause_name,
                "count": cause_counts[cause_name],
                "total": round(cause_sum, 2),
                "share": round(share, 1),
            }
        )

    return {
        "count": count,
        "total": round(total, 2),
        "average": round(average, 2),
        "highest": highest_item,
        "lowest": lowest_item,
        "causes": cause_rows,
        "high_value_count": len(high_value_records),
    }


def get_advanced_insights(records):
    """Return donor rankings, monthly totals, and possible duplicate groups."""
    donor_totals = {}
    monthly_totals = {}
    duplicate_map = {}
    for item in records:
        donor_key = item["donor"].strip().casefold()
        donor_totals[donor_key] = donor_totals.get(donor_key, {"donor": item["donor"], "count": 0, "total": 0.0})
        donor_totals[donor_key]["count"] += 1
        donor_totals[donor_key]["total"] += float(item["amount"])
        month = item["date"][:7]
        monthly_totals[month] = monthly_totals.get(month, 0.0) + float(item["amount"])
        duplicate_key = (donor_key, item["cause"].strip().casefold(), round(float(item["amount"]), 2), item["date"])
        duplicate_map.setdefault(duplicate_key, []).append(item["id"])

    top_donors = sorted(donor_totals.values(), key=lambda row: row["total"], reverse=True)[:5]
    for row in top_donors:
        row["total"] = round(row["total"], 2)
    possible_duplicates = [ids for ids in duplicate_map.values() if len(ids) > 1]
    repeat_donors = [row for row in donor_totals.values() if row["count"] >= 2]
    repeat_donors.sort(key=lambda row: (row["count"], row["total"]), reverse=True)
    donor_count = len(donor_totals)
    repeat_rate = (len(repeat_donors) / donor_count * 100) if donor_count else 0.0
    cause_totals = {}
    for item in records:
        cause_totals[item["cause"]] = cause_totals.get(item["cause"], 0.0) + float(item["amount"])
    total_raised = sum(cause_totals.values())
    largest_cause = max(cause_totals, key=cause_totals.get) if cause_totals else None
    concentration = (cause_totals[largest_cause] / total_raised * 100) if total_raised and largest_cause else 0.0
    return {
        "top_donors": top_donors,
        "monthly_totals": [{"month": month, "total": round(total, 2)} for month, total in sorted(monthly_totals.items())],
        "possible_duplicates": possible_duplicates,
        "repeat_donors": [{**row, "total": round(row["total"], 2)} for row in repeat_donors],
        "repeat_donor_rate": round(repeat_rate, 1),
        "largest_cause": largest_cause,
        "largest_cause_share": round(concentration, 1),
    }


def export_to_csv(records, filename=None):
    allow_custom_path = filename is not None
    target = sanitize_filename(
        filename or CONFIG["csv_export_file"],
        CONFIG["csv_export_file"],
        allow_subdir=allow_custom_path,
    )
    parent_dir = os.path.dirname(target)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    columns = ["id", "date", "donor", "cause", "amount", "method", "note"]
    with open(target, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        for item in records:
            writer.writerow(item)
    logger.info("Exported %d records to CSV '%s'.", len(records), target)
    return target


def create_cause_chart(records, filename=None):
    target = sanitize_filename(filename or CONFIG["chart_file"], CONFIG["chart_file"])
    if not records:
        return False, "No records available to plot."

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("matplotlib missing when generating chart.")
        return False, "matplotlib is not installed. Run: pip install matplotlib"

    summary = get_summary(records)
    labels = [row["cause"] for row in summary["causes"]]
    values = [row["total"] for row in summary["causes"]]

    plt.figure(figsize=(7, 4))
    bars = plt.bar(labels, values, color="#2b6cb0")
    plt.title("Donations by Cause")
    plt.xlabel("Cause")
    plt.ylabel("Total Amount")
    plt.xticks(rotation=20)
    plt.tight_layout()

    for bar, val in zip(bars, values):
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            f"{val:.0f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    plt.savefig(target, dpi=150)
    plt.close()
    logger.info("Generated chart at '%s'.", target)
    return True, f"Chart saved as '{target}'."
