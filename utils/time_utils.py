# utils/time_utils.py

from datetime import datetime
from zoneinfo import ZoneInfo
import re

CST = ZoneInfo("America/Chicago")

def parse_cst_timestamp(ts: str) -> datetime:
    """
    Parse a timestamp like "2025-08-02 22:52:27 CDT" into a tz-aware datetime in CST.
    """
    m = re.match(r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", ts)
    if not m:
        raise ValueError(f"Unrecognized timestamp format: {ts!r}")
    dt_naive = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
    return dt_naive.replace(tzinfo=CST)

def format_cst(ts: str) -> str:
    """
    Convert a CST timestamp string into:
        M/D/YYYY, H:MM AM/PM CST
    (no leading zeros on month, day, or hour; minutes remain two-digit)
    """
    dt = parse_cst_timestamp(ts)
    month  = dt.month
    day    = dt.day
    year   = dt.year
    hour24 = dt.hour
    hour12 = hour24 % 12 or 12
    minute = f"{dt.minute:02d}"
    ampm   = dt.strftime("%p")
    # changed " at " → ", "
    return f"{month}/{day}/{year}, {hour12}:{minute} {ampm} CST"

def time_ago(dt: datetime) -> str:
    """
    Given a datetime, returns a human-readable "time ago"...
    """
    now = datetime.now(CST)
    diff = now - dt
    days    = diff.days
    hours   = diff.seconds // 3600
    minutes = (diff.seconds % 3600) // 60
    seconds = diff.seconds % 60

    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}hr")
    if (not parts or len(parts) == 1) and minutes:
        parts.append(f"{minutes}m")
    if not parts and seconds:
        parts.append(f"{seconds}s")
    if not parts:
        return "JUST NOW"
    return " ".join(parts[:2]) + " ago"


def parse_iso_to_cst(ts: str) -> datetime:
    """
    Parse an ISO‐8601 timestamp (with offset) into a tz‐aware datetime in CST.
    """
    dt = datetime.fromisoformat(ts)
    return dt.astimezone(CST)

def format_datetime_cst(dt: datetime) -> str:
    """
    Format a tz‐aware datetime (assumed in CST) as:
        M/D/YYYY, H:MM AM/PM CST
    (no leading zeros on month/day/hour; minute stays two‐digit)
    """
    # ensure it's in CST
    dt = dt.astimezone(CST)
    month  = dt.month
    day    = dt.day
    year   = dt.year
    hour24 = dt.hour
    hour12 = hour24 % 12 or 12
    minute = f"{dt.minute:02d}"
    ampm   = dt.strftime("%p")
    return f"{month}/{day}/{year}, {hour12}:{minute} {ampm} CST"