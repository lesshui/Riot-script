import sqlite3
import hashlib
import os
import getpass

DB_FILE = "users.db"


def setup_database():
    """Create the users table if it doesn't exist."""
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    print(f"Database ready: {DB_FILE}\n")


def hash_password(password: str) -> str:
    """Hash a password using PBKDF2-HMAC-SHA256 with a random salt."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 480_000)
    return salt.hex() + ":" + key.hex()


def verify_password(stored: str, password: str) -> bool:
    """Return True if password matches the stored PBKDF2 hash."""
    salt_hex, key_hex = stored.split(":", 1)
    salt = bytes.fromhex(salt_hex)
    key = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 480_000)
    return key.hex() == key_hex


def validate_inputs(username: str, email: str, password: str) -> list:
    """Return a list of validation error messages (empty list means valid)."""
    errors = []
    if not username:
        errors.append("Username cannot be empty.")
    if "@" not in email or "." not in email.split("@")[-1]:
        errors.append("Email address is not valid.")
    if not password:
        errors.append("Password cannot be empty.")
    return errors


def create_user(username: str, email: str, password: str):
    """Validate inputs then insert a new user into the database."""
    errors = validate_inputs(username, email, password)
    if errors:
        for err in errors:
            print(f"  Error: {err}")
        return

    with sqlite3.connect(DB_FILE) as conn:
        try:
            conn.execute(
                "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                (username, email, hash_password(password)),
            )
            print(f"User '{username}' created successfully!")
        except sqlite3.IntegrityError as e:
            if "username" in str(e):
                print(f"Error: Username '{username}' already exists.")
            elif "email" in str(e):
                print(f"Error: Email '{email}' already exists.")
            else:
                print(f"Error: {e}")


def list_users():
    """Print all users in the database."""
    with sqlite3.connect(DB_FILE) as conn:
        users = conn.execute(
            "SELECT id, username, email, created_at FROM users"
        ).fetchall()

    if not users:
        print("No users found.")
        return

    print(f"\n{'ID':<5} {'Username':<20} {'Email':<30} {'Created At'}")
    print("-" * 75)
    for user in users:
        print(f"{user[0]:<5} {user[1]:<20} {user[2]:<30} {user[3]}")
    print()


def login_user(username: str, password: str):
    """Verify a user's credentials and report success or failure."""
    with sqlite3.connect(DB_FILE) as conn:
        row = conn.execute(
            "SELECT password_hash FROM users WHERE username = ?", (username,)
        ).fetchone()

    if row and verify_password(row[0], password):
        print(f"Login successful. Welcome, {username}!")
    else:
        print("Invalid username or password.")


def main():
    setup_database()

    while True:
        print("What would you like to do?")
        print("  1. Create a new user")
        print("  2. List all users")
        print("  3. Login / verify password")
        print("  4. Exit")
        choice = input("\nEnter choice (1/2/3/4): ").strip()

        if choice == "1":
            print()
            username = input("Username: ").strip()
            email = input("Email: ").strip()
            password = getpass.getpass("Password (hidden): ")
            print()
            create_user(username, email, password)
            print()

        elif choice == "2":
            list_users()

        elif choice == "3":
            print()
            username = input("Username: ").strip()
            password = getpass.getpass("Password (hidden): ")
            print()
            login_user(username, password)
            print()

        elif choice == "4":
            print("Goodbye!")
            break

        else:
            print("Invalid choice, please enter 1, 2, 3, or 4.\n")


if __name__ == "__main__":
    main()
