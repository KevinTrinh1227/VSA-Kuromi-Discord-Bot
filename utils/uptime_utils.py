# utils/uptime_utils.py

import json
import atexit
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

# ─── Load config & determine LOG_PATH ────────────────────────────

# assume config.json sits one level above this utils/ folder
_CONFIG_PATH = Path(__file__).parent.parent / "config.json"
try:
    _CFG = json.loads(_CONFIG_PATH.read_text())
except (FileNotFoundError, json.JSONDecodeError):
    _CFG = {}

# get the file-path key, with a sensible default if missing
_log_rel = _CFG.get("file_paths", {}) \
               .get("bot_client_session_uptime_info_logs", "data/session_info_logs.json")
LOG_PATH = Path(__file__).parent.parent / _log_rel
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

# CST tzinfo
CST = ZoneInfo("America/Chicago")


# ─── Internal helpers ─────────────────────────────────────────────

def _load_log() -> list:
    """Load sessions list or return empty."""
    try:
        return json.loads(LOG_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_log(log: list) -> None:
    """Persist sessions list as pretty JSON."""
    LOG_PATH.write_text(json.dumps(log, indent=2))


def _generate_session_id(session_number: int, start_iso: str) -> str:
    """
    From a UTC ISO timestamp, generate a CST-based session ID:
      <session_number>_<YYYYMMDD>T<HHMMSS>
    """
    dt = datetime.fromisoformat(start_iso).astimezone(CST)
    return f"{dt.strftime('%Y%m%dT%H%M%S')}00{session_number}"


def _format_cst(dt: datetime) -> str:
    """
    Format a CST-aware datetime as:
        M/D/YYYY, H:MM AM/PM CST
    (no leading zeros on month/day/hour; minutes two-digit)
    """
    month  = dt.month
    day    = dt.day
    year   = dt.year
    hour24 = dt.hour
    hour12 = hour24 % 12 or 12
    minute = f"{dt.minute:02d}"
    ampm   = dt.strftime("%p")
    return f"{month}/{day}/{year}, {hour12}:{minute} {ampm} CST"


def _compute_uptime(start_iso: str, end_iso: str) -> dict:
    """
    Compute {days, hours, minutes, seconds} between two UTC ISO timestamps.
    """
    dt_start = datetime.fromisoformat(start_iso)
    dt_end   = datetime.fromisoformat(end_iso)
    delta    = dt_end - dt_start
    secs     = int(delta.total_seconds())
    days, rem = divmod(secs, 86400)
    hrs, rem  = divmod(rem,   3600)
    mins, sec = divmod(rem,    60)
    return {"days": days, "hours": hrs, "minutes": mins, "seconds": sec}


# ─── Public API ───────────────────────────────────────────────────

def start_session() -> str:
    """
    On bot startup:
      • Close any crashed session
      • Open a new one with raw + formatted CST times
    Returns the new session_id.
    """
    now_utc   = datetime.now(timezone.utc)
    start_iso = now_utc.isoformat()
    log       = _load_log()

    # if previous never ended, close it now
    if log and log[-1].get("session_end_time") is None:
        log[-1]["session_end_time"] = start_iso
        log[-1]["formatted_cst_session_end_timestamp"] = _format_cst(
            datetime.fromisoformat(start_iso).astimezone(CST)
        )
        log[-1]["session_uptime"] = _compute_uptime(
            log[-1]["session_start_time"], start_iso
        )

    next_no    = len(log) + 1
    session_id = _generate_session_id(next_no, start_iso)
    start_dt    = datetime.fromisoformat(start_iso).astimezone(CST)
    formatted   = _format_cst(start_dt)

    entry = {
        "session_number":                        next_no,
        "id":                                    session_id,
        "session_start_time":                    start_iso,
        "formatted_cst_session_start_timestamp": formatted,
        "session_end_time":                      None,
        "formatted_cst_session_end_timestamp":   None,
        "session_uptime":                        None,
    }
    log.append(entry)
    _save_log(log)
    return session_id


def record_session_info(session_id: str, info: dict) -> None:
    """
    Attach an arbitrary dict of “session_startup_information” to the
    existing session entry (by session_id) and persist the log.

    session_id: the ID returned by start_session()
    info:      any dict you like—will be stored under “session_startup_information”
    """
    log = _load_log()
    for entry in log:
        if entry.get("id") == session_id:
            # overwrite or create this key
            entry["session_startup_information"] = info
            break
    _save_log(log)



def end_session(session_id: str) -> None:
    """
    On clean exit, mark the session’s end time + formatted CST + uptime.
    """
    end_iso = datetime.now(timezone.utc).isoformat()
    log     = _load_log()
    for entry in log:
        if entry["id"] == session_id and entry.get("session_end_time") is None:
            entry["session_end_time"] = end_iso
            end_dt = datetime.fromisoformat(end_iso).astimezone(CST)
            entry["formatted_cst_session_end_timestamp"] = _format_cst(end_dt)
            entry["session_uptime"] = _compute_uptime(
                entry["session_start_time"], end_iso
            )
            break
    _save_log(log)


# ─── Auto-register on import ──────────────────────────────────────

_current_session_id = None

def _register():
    """
    Start a session on import and ensure it ends cleanly on exit.
    """
    global _current_session_id
    _current_session_id = start_session()
    atexit.register(lambda: end_session(_current_session_id))

_register()