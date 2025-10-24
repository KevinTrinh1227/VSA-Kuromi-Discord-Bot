# list_ig_inbox_threads.py
import os
import sys
from typing import Set, Optional
from datetime import datetime, timezone

from instagrapi import Client

# Optional: load .env (INSTAGRAM_USERNAME / INSTAGRAM_PASSWORD / IG_LIST_LIMIT)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ---------- Pretty printing helpers ----------
def line(char: str = "─", width: int = 78) -> str:
    return char * width

def header(title: str) -> str:
    bar = line("═")
    return f"{bar}\n{title}\n{bar}"

def section(title: str) -> str:
    return f"{title}\n{line()}"

def fmt_ts(ts: Optional[datetime]) -> str:
    if not isinstance(ts, datetime):
        return "n/a"
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

def snippet(text: Optional[str], max_len: int = 300) -> str:
    if text is None:
        return ""
    text = text.replace("\r", " ").replace("\n", "\\n")
    return (text[:max_len] + "…") if len(text) > max_len else text

def debug(msg: str) -> None:
    print(f"[DEBUG] {msg}")

# ---------- Main ----------
def main():
    username = os.getenv("INSTAGRAM_USERNAME", "").strip()
    password = os.getenv("INSTAGRAM_PASSWORD", "").strip()
    limit = int(os.getenv("IG_LIST_LIMIT", "20"))

    print(header("Instagram Inbox Threads (Inbox Only)"))
    if not username or not password:
        print("ERROR: Set INSTAGRAM_USERNAME and INSTAGRAM_PASSWORD in your environment or .env file.")
        sys.exit(1)

    print(f"Login user: @{username}")
    print(line())

    cl = Client()

    # Direct login (no session caching/writes)
    try:
        debug("Attempting login…")
        cl.login(username, password)
        debug("Login OK.")
    except Exception as e:
        print(section("Login Failed"))
        print(repr(e))
        sys.exit(1)

    # Fetch inbox threads
    try:
        debug(f"Fetching inbox threads (limit={limit})…")
        threads = cl.direct_threads(limit)
        debug(f"Fetched {len(threads)} thread(s).")
    except Exception as e:
        print(section("Failed to Fetch Inbox Threads"))
        print(repr(e))
        sys.exit(1)

    if not threads:
        print(section("No Threads Found"))
        print("Your inbox appears to be empty.")
        return

    print(section(f"Found {len(threads)} Thread(s)"))
    unique_users: Set[str] = set()

    # Iterate threads
    for idx, t in enumerate(threads, start=1):
        print(line())

        # Basic thread info
        thread_id = getattr(t, "id", None) or getattr(t, "thread_id", None) or "(unknown)"
        title = getattr(t, "thread_title", None) or getattr(t, "title", None) or "(no title)"
        users = getattr(t, "users", []) or []
        usernames = [getattr(u, "username", "?") for u in users]

        # Track unique usernames
        for u in usernames:
            if u:
                unique_users.add(u)

        print(f"[{idx}] Thread")
        print(f"ID:        {thread_id}")
        print(f"Title:     {title}")
        print(f"Members:   {len(usernames)}")
        if usernames:
            for i, name in enumerate(usernames, start=1):
                print(f"  {i:>2}. {name}")
        else:
            print("  (no participants listed)")

        # Fetch recent 5 messages for this thread
        try:
            debug(f"Fetching last 5 messages for thread {thread_id}…")
            msgs = cl.direct_messages(thread_id, amount=5)
            debug(f"Fetched {len(msgs)} message(s) for thread {thread_id}.")
        except Exception as e:
            print("Messages:  (failed to fetch)")
            print(f"  Error: {repr(e)}")
            continue

        if not msgs:
            print("Messages:  (none)")
            continue

        print("Messages (newest → oldest):")
        for m in msgs:
            # Basic fields
            mid = getattr(m, "id", getattr(m, "pk", "")) or "(no id)"
            item_type = getattr(m, "item_type", "unknown")
            ts = getattr(m, "timestamp", None) or getattr(m, "taken_at", None)
            text = getattr(m, "text", None)

            # Resolve author username
            author_id = getattr(m, "user_id", None)
            author_name = None
            for u in users:
                if int(getattr(u, "pk", 0)) == int(author_id or 0):
                    author_name = getattr(u, "username", None)
                    break
            author_disp = author_name or f"user_id:{author_id}"

            print(f"  • [{fmt_ts(ts)}] ({item_type}) {author_disp}")
            if text:
                print(f"    {snippet(text)}")
            else:
                print(f"    (no text) mid={mid}")

    print(line())
    print(section(f"Unique Participants Across Listed Threads: {len(unique_users)}"))
    if unique_users:
        for i, name in enumerate(sorted(unique_users), start=1):
            print(f"  {i:>2}. {name}")
    print(line("═"))

if __name__ == "__main__":
    main()
