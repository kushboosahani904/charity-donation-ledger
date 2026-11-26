from datetime import datetime
import argparse
import sys

from ledger_logic import (
    CONFIG,
    check_threshold_warnings,
    configure_logging,
    create_cause_chart,
    export_to_csv,
    generate_next_id,
    get_summary,
    get_advanced_insights,
    import_from_csv,
    is_valid_amount,
    is_valid_date,
    load_records,
    logger,
    save_records,
    search_records,
)


def ask_non_empty(prompt_text):
    while True:
        user_input = input(prompt_text).strip()
        if user_input != "":
            return user_input
        print("This field cannot be empty. Please try again.")


def ask_amount(prompt_text):
    min_amt = CONFIG["min_amount"]
    max_amt = CONFIG["max_amount"]
    while True:
        user_input = input(prompt_text)
        amt = is_valid_amount(user_input)
        if amt is not None:
            return amt
        print(f"Please enter a valid number between {min_amt} and {max_amt}.")


def ask_date(prompt_text):
    while True:
        user_input = input(prompt_text).strip()
        if user_input == "":
            return datetime.today().strftime("%Y-%m-%d")
        dt = is_valid_date(user_input)
        if dt is not None:
            return dt
        print("Invalid date. Use YYYY-MM-DD format and do not enter a future date.")


def display_records(records):
    if len(records) == 0:
        print("\nNo donation records found.")
        return

    print("\n" + "=" * 86)
    print(f"{'ID':<9} {'Date':<12} {'Donor':<18} {'Cause':<15} {'Amount':>10} {'Method':<12}")
    print("=" * 86)

    for item in records:
        print(
            f"{item['id']:<9} "
            f"{item['date']:<12} "
            f"{item['donor'][:17]:<18} "
            f"{item['cause'][:14]:<15} "
            f"{item['amount']:>10.2f} "
            f"{item['method'][:11]:<12}"
        )

    print("=" * 86)
    print(f"Total records shown: {len(records)}")


def add_donation(records):
    print("\n--- Add New Donation ---")
    donor = ask_non_empty("Donor name: ")
    cause = ask_non_empty("Cause (e.g., Education, Food Relief, Clean Water): ")
    amount = ask_amount("Donation amount: ")
    rec_date = ask_date("Date (YYYY-MM-DD, press Enter for today): ")
    method = input("Payment method (Cash/UPI/Card/Bank Transfer) [UPI]: ").strip()
    if method == "":
        method = "UPI"
    note = input("Short note (optional): ").strip()

    new_record = {
        "id": generate_next_id(records),
        "donor": donor,
        "cause": cause,
        "amount": amount,
        "date": rec_date,
        "method": method,
        "note": note,
    }

    records.append(new_record)
    save_records(records)
    logger.info("Added donation %s (%s: %.2f)", new_record["id"], cause, amount)
    print(f"\nSaved {new_record['id']} for {new_record['cause']} ({new_record['amount']:.2f}).")

    for warning in check_threshold_warnings(new_record):
        print(f"[ALERT] {warning}")


def find_donations(records):
    print("\n--- Search & Filter (Supports Fuzzy & Regex) ---")
    keyword = input("Search keyword or regex (leave blank to skip): ").strip()
    cause = input("Filter by exact cause (leave blank to skip): ").strip()
    regex_choice = input("Treat keyword as regex? (y/n) [n]: ").strip().lower()
    use_regex = regex_choice == "y"

    results = search_records(records, keyword=keyword, cause=cause, use_regex=use_regex)
    display_records(results)


def bulk_import(records):
    print("\n--- Bulk Import from CSV ---")
    csv_path = ask_non_empty("Enter CSV file path (columns: donor,cause,amount,date,method,note): ")
    added, errors = import_from_csv(csv_path, records)
    if added > 0:
        save_records(records)
    print(f"\nImported {added} valid records.")
    if errors:
        print("Skipped rows:")
        for err in errors:
            print(f"  - {err}")


def show_summary(records):
    summary = get_summary(records)
    print("\n--- Summary Report ---")
    print(f"Number of Donations : {summary['count']}")
    print(f"Total Amount Raised : {summary['total']:.2f}")
    print(f"Average Donation    : {summary['average']:.2f}")
    print(f"High-Value Alerts   : {summary['high_value_count']}")

    if summary["highest"] is not None:
        h = summary["highest"]
        print(f"Highest Donation    : {h['amount']:.2f} by {h['donor']} ({h['cause']})")

    if summary["lowest"] is not None:
        l = summary["lowest"]
        print(f"Lowest Donation     : {l['amount']:.2f} by {l['donor']} ({l['cause']})")

    if len(summary["causes"]) > 0:
        print("\nCause-wise Breakdown:")
        print(f"{'Cause':<18} {'Count':>6} {'Total':>12} {'Share (%)':>10}")
        print("-" * 50)
        for row in summary["causes"]:
            print(
                f"{row['cause']:<18} "
                f"{row['count']:>6} "
                f"{row['total']:>12.2f} "
                f"{row['share']:>9.1f}%"
            )

    insights = get_advanced_insights(records)
    if insights["top_donors"]:
        print("\nTop Donors:")
        for rank, donor in enumerate(insights["top_donors"], start=1):
            print(f"{rank}. {donor['donor']} — {donor['total']:.2f} ({donor['count']} donations)")
    if insights["monthly_totals"]:
        print("\nMonthly Donation Trend:")
        for row in insights["monthly_totals"]:
            print(f"{row['month']}: {row['total']:.2f}")
    if insights["repeat_donors"]:
        print(f"\nRepeat Donor Rate: {insights['repeat_donor_rate']:.1f}%")
        for donor in insights["repeat_donors"]:
            print(f"- {donor['donor']}: {donor['count']} donations, total {donor['total']:.2f}")
    if insights["largest_cause"] is not None:
        print(
            f"Largest Cause Share: {insights['largest_cause']} "
            f"({insights['largest_cause_share']:.1f}% of total donations)"
        )
    if insights["possible_duplicates"]:
        print("\n[REVIEW] Possible duplicate donations:")
        for ids in insights["possible_duplicates"]:
            print("  " + ", ".join(ids))


def show_menu():
    print("\n===============================")
    print("   CHARITY DONATION LEDGER")
    print("===============================")
    print("1. Record a donation")
    print("2. View all donations")
    print("3. Search / filter donations")
    print("4. View summary report")
    print("5. Export summary to CSV")
    print("6. Generate cause bar chart")
    print("7. Bulk import donations from CSV")
    print("8. Exit")


def build_parser():
    """Build the command-line interface; no option starts the interactive menu."""
    parser = argparse.ArgumentParser(
        description="Charity Donation Ledger — record, search and analyse donations."
    )
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--summary", action="store_true", help="print a summary and donor insights")
    actions.add_argument("--export-csv", metavar="PATH", help="export all donations to a CSV file")
    actions.add_argument("--import-csv", metavar="PATH", help="import validated donations from a CSV file")
    actions.add_argument("--chart", action="store_true", help="generate the cause-wise bar chart")
    actions.add_argument("--search", metavar="TEXT", help="search donations by donor, cause, ID or note")
    parser.add_argument("--cause", default="", help="optional exact cause filter for --search")
    parser.add_argument("--regex", action="store_true", help="treat --search text as a regular expression")
    parser.add_argument("--db", metavar="PATH", help="use a specific SQLite database file")
    parser.add_argument(
        "--log-level", default="INFO", choices=("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"),
        help="logging verbosity (default: INFO)",
    )
    return parser


def run_cli(args):
    """Execute a non-interactive action. Returns an exit status."""
    if args.db:
        CONFIG["database_file"] = args.db
    configure_logging(args.log_level)
    records, notice = load_records()
    if notice:
        print(notice)

    if args.summary:
        show_summary(records)
    elif args.export_csv:
        output = export_to_csv(records, args.export_csv)
        print(f"Exported {len(records)} records to '{output}'.")
    elif args.import_csv:
        added, errors = import_from_csv(args.import_csv, records)
        if added:
            save_records(records)
        print(f"Imported {added} valid records.")
        for error in errors:
            print(f"- {error}")
        return 1 if errors and not added else 0
    elif args.chart:
        ok, message = create_cause_chart(records)
        print(message)
        return 0 if ok else 1
    elif args.search is not None:
        results = search_records(records, keyword=args.search, cause=args.cause, use_regex=args.regex)
        display_records(results)
    else:
        return None
    return 0


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        status = run_cli(args)
        if status is not None:
            return status
        records, notice = load_records()
        if notice:
            print(notice)

        while True:
            show_menu()
            choice = input("Enter your choice (1-8): ").strip()

            if choice == "1":
                add_donation(records)
            elif choice == "2":
                display_records(records)
            elif choice == "3":
                find_donations(records)
            elif choice == "4":
                show_summary(records)
            elif choice == "5":
                out = export_to_csv(records)
                print(f"\nExported records to '{out}'.")
            elif choice == "6":
                ok, msg = create_cause_chart(records)
                print(f"\n{msg}")
            elif choice == "7":
                bulk_import(records)
            elif choice == "8":
                save_records(records)
                print("\nData saved. Goodbye!")
                break
            else:
                print("Invalid choice. Please enter a number from 1 to 8.")
        return 0
    except (OSError, ValueError) as exc:
        logger.exception("Application action failed")
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
