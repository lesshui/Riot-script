"""
email_2fa.py — iCloud IMAP helper for Riot 2FA codes.

Usage:
    from email_2fa import fetch_riot_2fa_code

    code = fetch_riot_2fa_code("you@icloud.com", "abcd-efgh-ijkl-mnop")
    if code:
        print(f"Got 2FA code: {code}")
    else:
        print("Timed out waiting for 2FA email.")

Requirements:
    - An Apple app-specific password (not your regular Apple ID password).
      Generate one at: appleid.apple.com → Security → App-Specific Passwords
    - iCloud IMAP must be enabled on the account (it is on by default).
"""

import imaplib
import email
import re
import time
from datetime import datetime, timezone

ICLOUD_IMAP_HOST = "imap.mail.me.com"
ICLOUD_IMAP_PORT = 993

# Riot sends verification emails from this address (adjust if needed)
RIOT_SENDER_PATTERN = re.compile(r"riotgames\.com", re.IGNORECASE)

# Regex to extract the first 6-digit number from an email body
CODE_PATTERN = re.compile(r"\b(\d{6})\b")


def _decode_payload(msg) -> str:
    """Extract plain-text body from a email.message.Message object."""
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


def fetch_riot_2fa_code(
    email_address: str,
    app_password: str,
    timeout: int = 60,
    poll_interval: int = 3,
) -> str | None:
    """
    Connect to iCloud IMAP and wait for a Riot 2FA verification email.

    Parameters
    ----------
    email_address   : iCloud address of the account (e.g. you@icloud.com)
    app_password    : Apple app-specific password for IMAP access
    timeout         : How many seconds to wait before giving up (default 60)
    poll_interval   : Seconds between inbox checks (default 3)

    Returns
    -------
    The 6-digit code as a string, or None if timed out.
    """
    start = datetime.now(timezone.utc)
    # IMAP date format: DD-Mon-YYYY  (used to filter emails received today)
    since_date = start.strftime("%d-%b-%Y")

    try:
        mail = imaplib.IMAP4_SSL(ICLOUD_IMAP_HOST, ICLOUD_IMAP_PORT)
        mail.login(email_address, app_password)
    except imaplib.IMAP4.error as exc:
        print(f"[2FA] IMAP login failed: {exc}")
        return None

    try:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            mail.select("INBOX")
            # Search for unseen emails from Riot received on or after today
            status, data = mail.search(
                None, f'(UNSEEN SINCE "{since_date}" FROM "riotgames.com")'
            )
            if status == "OK" and data and data[0]:
                msg_ids = data[0].split()
                for msg_id in msg_ids:
                    status2, msg_data = mail.fetch(msg_id, "(RFC822)")
                    if status2 != "OK":
                        continue
                    raw = msg_data[0][1]
                    msg = email.message_from_bytes(raw)

                    # Confirm sender contains riotgames.com
                    sender = msg.get("From", "")
                    if not RIOT_SENDER_PATTERN.search(sender):
                        continue

                    body = _decode_payload(msg)
                    match = CODE_PATTERN.search(body)
                    if match:
                        code = match.group(1)
                        # Mark as read so we don't pick it up again
                        mail.store(msg_id, "+FLAGS", "\\Seen")
                        return code

            time.sleep(poll_interval)
    finally:
        try:
            mail.logout()
        except Exception:
            pass

    return None


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        print("Usage: python email_2fa.py <icloud_email> <app_password>")
        sys.exit(1)

    result = fetch_riot_2fa_code(sys.argv[1], sys.argv[2])
    if result:
        print(f"2FA code: {result}")
    else:
        print("No 2FA code received within the timeout.")
