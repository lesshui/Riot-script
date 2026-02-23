"""
email_2fa.py — Single iCloud inbox helper for Riot 2FA codes.

All Riot verification emails arrive at one shared iCloud inbox.
This module logs in once with stored credentials and matches each
2FA email to the specific Riot account email being signed up.

Setup (run once):
    python email_2fa.py --setup

Usage in code:
    from email_2fa import fetch_riot_2fa_code

    code = fetch_riot_2fa_code("newaccount@gmail.com")
    if code:
        print(f"Got 2FA code: {code}")
    else:
        print("Timed out waiting for 2FA email.")

Requirements:
    - An Apple app-specific password (not your regular Apple ID password).
      Generate one at: appleid.apple.com → Security → App-Specific Passwords
    - iCloud IMAP must be enabled on the account (it is on by default).
    - Credentials are saved in icloud_creds.json (gitignored).
"""

import imaplib
import email
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ICLOUD_IMAP_HOST = "imap.mail.me.com"
ICLOUD_IMAP_PORT = 993

CREDS_FILE = Path(__file__).parent / "icloud_creds.json"

# Riot sends verification emails from riotgames.com domains
RIOT_SENDER_RE = re.compile(r"riotgames\.com", re.IGNORECASE)

# Extract the first 6-digit number from the email body
CODE_RE = re.compile(r"\b(\d{6})\b")

# ---------------------------------------------------------------------------
# Persistent IMAP connection (module-level singleton)
# ---------------------------------------------------------------------------

_imap_conn: imaplib.IMAP4_SSL | None = None


def _get_imap() -> imaplib.IMAP4_SSL:
    """Return the shared IMAP connection, (re)connecting if needed."""
    global _imap_conn
    if _imap_conn is not None:
        # NOOP keeps the session alive and detects a dropped connection
        try:
            _imap_conn.noop()
            return _imap_conn
        except Exception:
            _imap_conn = None  # connection is dead; fall through to reconnect

    icloud_email, app_password = load_credentials()
    conn = imaplib.IMAP4_SSL(ICLOUD_IMAP_HOST, ICLOUD_IMAP_PORT)
    conn.login(icloud_email, app_password)
    _imap_conn = conn
    return _imap_conn


def close_imap() -> None:
    """Explicitly close the shared IMAP connection (call when fully done)."""
    global _imap_conn
    if _imap_conn is not None:
        try:
            _imap_conn.logout()
        except Exception:
            pass
        _imap_conn = None


# ---------------------------------------------------------------------------
# Credential management
# ---------------------------------------------------------------------------

def save_credentials(icloud_email: str, app_password: str) -> None:
    """Persist iCloud IMAP credentials to icloud_creds.json."""
    CREDS_FILE.write_text(
        json.dumps({"email": icloud_email, "app_password": app_password}, indent=2),
        encoding="utf-8",
    )
    print(f"Credentials saved to {CREDS_FILE}")


def load_credentials() -> tuple[str, str]:
    """Load iCloud credentials from icloud_creds.json.

    Returns (icloud_email, app_password).
    Raises FileNotFoundError if setup has not been run yet.
    """
    if not CREDS_FILE.exists():
        raise FileNotFoundError(
            "iCloud credentials not found. Run  python email_2fa.py --setup  first."
        )
    data = json.loads(CREDS_FILE.read_text(encoding="utf-8"))
    return data["email"], data["app_password"]


def setup_icloud() -> None:
    """Interactive prompt to save iCloud IMAP credentials."""
    print("=== iCloud IMAP setup ===")
    print("Enter the iCloud account that receives ALL Riot 2FA emails.")
    print("Use an app-specific password (appleid.apple.com → Security → App-Specific Passwords).\n")
    icloud_email = input("iCloud email address: ").strip()
    app_password = input("App-specific password (xxxx-xxxx-xxxx-xxxx): ").strip()
    save_credentials(icloud_email, app_password)
    print("\nSetup complete. Test with:  python email_2fa.py <riot_account_email>")


# ---------------------------------------------------------------------------
# IMAP helpers
# ---------------------------------------------------------------------------

def _decode_payload(msg) -> str:
    """Extract plain-text body from an email.message.Message object."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                charset = part.get_content_charset() or "utf-8"
                try:
                    body += part.get_payload(decode=True).decode(charset, errors="replace")
                except Exception:
                    pass
    else:
        charset = msg.get_content_charset() or "utf-8"
        try:
            body = msg.get_payload(decode=True).decode(charset, errors="replace")
        except Exception:
            pass
    return body


# ---------------------------------------------------------------------------
# Main public function
# ---------------------------------------------------------------------------

def fetch_riot_2fa_code(
    target_email: str,
    timeout: int = 60,
    poll_interval: int = 3,
) -> str | None:
    """
    Wait for a Riot 2FA email addressed to *target_email* in the shared inbox.

    Credentials are loaded automatically from icloud_creds.json.

    Parameters
    ----------
    target_email   : The Riot account email being signed up (used to match
                     the right 2FA email when multiple accounts are in flight).
    timeout        : Seconds to wait before giving up (default 60).
    poll_interval  : Seconds between inbox checks (default 3).

    Returns
    -------
    The 6-digit code as a string, or None if timed out.
    """
    start = datetime.now(timezone.utc)
    since_date = start.strftime("%d-%b-%Y")

    try:
        mail = _get_imap()
    except FileNotFoundError as exc:
        print(f"[2FA] {exc}")
        return None
    except imaplib.IMAP4.error as exc:
        print(f"[2FA] IMAP login failed: {exc}")
        return None

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            mail.select("INBOX")
            # Fetch all unseen Riot emails received today
            status, data = mail.search(
                None, f'(UNSEEN SINCE "{since_date}" FROM "riotgames.com")'
            )
        except imaplib.IMAP4.abort:
            # Connection dropped mid-run; reconnect once and retry
            try:
                mail = _get_imap()
                continue
            except Exception:
                return None

        if status == "OK" and data and data[0]:
            for msg_id in data[0].split():
                status2, msg_data = mail.fetch(msg_id, "(RFC822)")
                if status2 != "OK":
                    continue

                msg = email.message_from_bytes(msg_data[0][1])

                # Confirm it's actually from Riot
                sender = msg.get("From", "")
                if not RIOT_SENDER_RE.search(sender):
                    continue

                # Match against the target Riot account email
                body = _decode_payload(msg)
                subject = msg.get("Subject", "")
                if target_email.lower() not in body.lower() and \
                   target_email.lower() not in subject.lower():
                    # This 2FA email is for a different account; leave it unread
                    continue

                code_match = CODE_RE.search(body)
                if code_match:
                    code = code_match.group(1)
                    mail.store(msg_id, "+FLAGS", "\\Seen")
                    return code

        time.sleep(poll_interval)

    return None


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--setup":
        setup_icloud()
        sys.exit(0)

    if len(sys.argv) == 2:
        target = sys.argv[1]
        print(f"Waiting for Riot 2FA email addressed to {target} ...")
        result = fetch_riot_2fa_code(target)
        if result:
            print(f"2FA code: {result}")
        else:
            print("No 2FA code received within the timeout.")
        sys.exit(0 if result else 1)

    print("Usage:")
    print("  python email_2fa.py --setup              # save iCloud credentials")
    print("  python email_2fa.py <riot_account_email> # wait for 2FA code")
    sys.exit(1)
