"""
import_users.py — Bulk-import accounts from a CSV file into the local SQLite database.

CSV format (header required):
    email,password

    - email    : the Riot account email address
    - password : the Riot account plain-text password

Username and birthday are auto-generated for every row.
iCloud 2FA credentials are stored once via:  python email_2fa.py --setup

Usage:
    python import_users.py                  # reads users_to_import.csv
    python import_users.py myaccounts.csv   # reads a custom CSV file
"""

import csv
import sys
import sqlite3

from create_users import (
    DB_FILE,
    setup_database,
    validate_inputs,
    generate_birthday,
    _unique_username,
)

DEFAULT_CSV = "users_to_import.csv"
REQUIRED_COLUMNS = {"email", "password"}


def import_from_csv(csv_path: str):
    setup_database()

    inserted = 0
    skipped = 0
    failed = 0

    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        if reader.fieldnames is None:
            print("Error: CSV file is empty or missing a header row.")
            return

        missing = REQUIRED_COLUMNS - {col.strip() for col in reader.fieldnames}
        if missing:
            print(f"Error: CSV is missing required columns: {', '.join(missing)}")
            return

        with sqlite3.connect(DB_FILE) as conn:
            for line_num, row in enumerate(reader, start=2):
                email = row.get("email", "").strip()
                password = row.get("password", "").strip()

                errors = validate_inputs(email, password)
                if errors:
                    for err in errors:
                        print(f"  Line {line_num}: {err}")
                    failed += 1
                    continue

                birthday = generate_birthday()
                username = _unique_username(conn)

                try:
                    conn.execute(
                        """INSERT INTO users
                           (email, birthday, username, password, terms_agreed)
                           VALUES (?, ?, ?, ?, 1)""",
                        (email, birthday, username, password),
                    )
                    print(f"  Inserted  email={email}  username={username}  birthday={birthday}")
                    inserted += 1
                except Exception as e:
                    err_str = str(e)
                    if "UNIQUE" in err_str or "unique" in err_str:
                        print(f"  Skipped   email={email}  (already exists)")
                        skipped += 1
                    else:
                        print(f"  Error     email={email}  {e}")
                        failed += 1

    print(f"\nDone. Inserted: {inserted}  Skipped (duplicate): {skipped}  Failed: {failed}")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV
    import_from_csv(path)
