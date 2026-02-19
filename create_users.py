import sqlite3
import os
import random
import string
import datetime

DB_FILE = "users.db"


def setup_database():
    """Create the users table if it doesn't exist."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                email               TEXT    UNIQUE NOT NULL,
                birthday            TEXT    NOT NULL,
                username            TEXT    UNIQUE NOT NULL,
                password            TEXT    NOT NULL,
                icloud_app_password TEXT,
                terms_agreed        INTEGER NOT NULL DEFAULT 1,
                created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    print(f"Database ready: {DB_FILE}\n")


def generate_username() -> str:
    """Return a random 10-character alphanumeric username."""
    chars = string.ascii_letters + string.digits
    return "".join(random.choices(chars, k=10))


def _unique_username(conn) -> str:
    """Generate a username guaranteed to not already exist in the DB."""
    while True:
        candidate = generate_username()
        exists = conn.execute(
            "SELECT 1 FROM users WHERE username = ?", (candidate,)
        ).fetchone()
        if not exists:
            return candidate


def generate_birthday() -> str:
    """Return a random birthday as MM-DD-YYYY with year in [1970, 2004]."""
    while True:
        year = random.randint(1970, 2004)
        month = random.randint(1, 12)
        day = random.randint(1, 31)
        try:
            datetime.date(year, month, day)
            return f"{month:02d}-{day:02d}-{year}"
        except ValueError:
            continue


def validate_inputs(email: str, password: str) -> list:
    """Return a list of validation error messages (empty list means valid)."""
    errors = []
    if not email:
        errors.append("Email cannot be empty.")
    elif "@" not in email or "." not in email.split("@")[-1]:
        errors.append("Email address is not valid.")
    if not password:
        errors.append("Password cannot be empty.")
    return errors


def create_user(email: str, password: str, icloud_app_password: str = ""):
    """Auto-generate username & birthday, then insert a new user into the database."""
    errors = validate_inputs(email, password)
    if errors:
        for err in errors:
            print(f"  Error: {err}")
        return

    birthday = generate_birthday()

    with sqlite3.connect(DB_FILE) as conn:
        username = _unique_username(conn)
        try:
            conn.execute(
                """INSERT INTO users
                   (email, birthday, username, password, icloud_app_password, terms_agreed)
                   VALUES (?, ?, ?, ?, ?, 1)""",
                (email, birthday, username, password, icloud_app_password),
            )
            print(f"User created  email={email}  username={username}  birthday={birthday}")
        except sqlite3.IntegrityError as e:
            if "email" in str(e):
                print(f"Error: Email '{email}' already exists.")
            else:
                print(f"Error: {e}")


def list_users():
    """Print all users in the database."""
    with sqlite3.connect(DB_FILE) as conn:
        users = conn.execute(
            "SELECT id, username, email, birthday, created_at FROM users"
        ).fetchall()

    if not users:
        print("No users found.")
        return

    print(f"\n{'ID':<5} {'Username':<12} {'Email':<35} {'Birthday':<12} {'Created At'}")
    print("-" * 85)
    for user in users:
        print(f"{user[0]:<5} {user[1]:<12} {user[2]:<35} {user[3]:<12} {user[4]}")
    print()


def main():
    setup_database()

    while True:
        print("What would you like to do?")
        print("  1. Create a new user")
        print("  2. List all users")
        print("  3. Exit")
        choice = input("\nEnter choice (1/2/3): ").strip()

        if choice == "1":
            print()
            email = input("Email: ").strip()
            password = input("Password: ")
            icloud_app_password = input("iCloud app-specific password (optional, press Enter to skip): ").strip()
            print()
            create_user(email, password, icloud_app_password)
            print()

        elif choice == "2":
            list_users()

        elif choice == "3":
            print("Goodbye!")
            break

        else:
            print("Invalid choice, please enter 1, 2, or 3.\n")


if __name__ == "__main__":
    main()
