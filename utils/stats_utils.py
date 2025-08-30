"""
stats_utils.py

Shared functions for:
 - parsing and normalizing member records
 - sorting and ranking logic
 - profile‐cog ranking helpers
 - parsing Family‐Tracker data
 - parsing event titles
"""

from utils import cache_utils


def parse_event_titles(raw_titles, existing_events=None):
    """
    Turn a list of strings like "8-26-2025 Bake Sale" into
    structured dicts with date, name, and user-preserved flags.
    """
    existing_map = {e["original"]: e for e in (existing_events or [])}
    parsed = []

    for idx, tag in enumerate(raw_titles, start=1):
        parts = tag.split(" ", 1)
        date_raw = parts[0]                # e.g. "8-26-2025"
        name = parts[1] if len(parts) > 1 else ""

        # Parse new date format
        try:
            month, day, year = map(int, date_raw.split("-"))
            date_str = f"{month:02d}/{day:02d}/{year}"  # keeps full date MM/DD/YYYY
        except ValueError:
            # fallback if the cell is not in expected format
            date_str = date_raw

        old = existing_map.get(tag, {})
        parsed.append({
            "id": idx,
            "original": tag,
            "date": date_str,
            "name": name,
            "is_general_meeting": old.get("is_general_meeting", False),
            "is_tlp": old.get("is_tlp", False),
            "is_sale": old.get("is_sale", False),
        })

    return parsed


def get_raw_sheet_data():
    """
    Returns the raw master‐sheet rows (each a list of strings), for parsing.
    """
    return cache_utils.get_master_data_raw()


def parse_members_from_sheet(data):
    """
    Turn raw sheet rows into a list of normalized member dicts.
    Pads short rows, skips invalid entries, and dedups by first+last name.
    Each member dict has:
      - psid         (str)
      - first_name   (str)
      - last_name    (str)
      - role_key     (str)
      - family_name  (str)
      - points       (int)
      - event_points (List[int])
    """
    members_map = {}

    for row in data:
        # ensure at least 6 columns for PSID, First, Last, Type, Family, Points
        row += [""] * (6 - len(row))
        psid, first, last, mtype, family, pts = [c.strip() for c in row[:6]]
        family = family or "No Family"

        if not psid or not first or not pts:
            continue

        try:
            pts_int = int(pts)
        except ValueError:
            continue

        key = f"{first.lower()}_{last.lower()}"
        if key in members_map:
            continue

        members_map[key] = {
            "psid":         psid,
            "first_name":   first,
            "last_name":    last,
            "role_key":     mtype or "",
            "family_name":  family,
            "points":       pts_int,
            # event_points will be filled by the cache‐updater
        }

    return list(members_map.values())


def get_sorted_leaderboard(members, sort_key="points", reverse=True):
    """
    Sort members by `sort_key` (default: points descending).
    """
    return sorted(members, key=lambda m: m.get(sort_key, 0), reverse=reverse)


def get_member_rank(members, target_first, target_last, sort_key="points"):
    """
    Return 1-based rank of the member matching (first, last).
    If not found, returns None.
    """
    sorted_list = get_sorted_leaderboard(members, sort_key=sort_key)
    target = (target_first.lower(), target_last.lower())
    for idx, m in enumerate(sorted_list, start=1):
        if (m["first_name"].lower(), m["last_name"].lower()) == target:
            return idx
    return None


def normalize_member_type(mt):
    """
    Normalize various member-type strings to one of:
     - "FL", "DD", "NM", "OFFICER", or passthrough.
    """
    mt0 = (mt or "").upper().strip()
    if mt0 in ("FL", "FAMILY LEAD", "FAMILY LEADER"):
        return "FL"
    if mt0 in ("DD", "DANCE DIRECTOR"):
        return "DD"
    if mt0 in ("NM", "NEW MEMBER"):
        return "NM"
    if mt0 in ("OFFICER", "EX-OFFICER", "EX OFFICER"):
        return "OFFICER"
    return mt0


def filter_members_by_family(members, family_name):
    """
    Return only those members whose `family_name` matches exactly.
    """
    return [m for m in members if m["family_name"] == family_name]


def filter_members_by_member_type(members, member_type):
    """
    Return only those members whose normalized role_key matches.
    """
    norm = normalize_member_type(member_type)
    return [m for m in members if normalize_member_type(m.get("role_key", "")) == norm]


# ── FAMILY TRACKER HELPERS ────────────────────────────────────────────────────

def get_raw_family_data():
    """
    Fetch the raw family_stats rows (list of lists) from cache.
    """
    return cache_utils.get_family_stats_raw()


def parse_family_tracker_data(raw_rows):
    """
    Turn raw Family-Tracker rows into a list of dicts:
      - family       (str)
      - total_points (int)
      - member_count (int)
      - avg_points   (int)  # rounded
    """
    families = []
    for row in raw_rows:
        if len(row) < 4:
            continue
        name, tot_s, cnt_s, avg_s = row[0], row[1], row[2], row[3]
        try:
            tot = int(tot_s)
            cnt = int(cnt_s)
            avg = round(float(avg_s))
        except (ValueError, TypeError):
            continue
        families.append({
            "family":       name,
            "total_points": tot,
            "member_count": cnt,
            "avg_points":   avg
        })
    return families


def get_sorted_family_leaderboard(families, sort_key="avg_points", reverse=True):
    """
    Sort the list of families by `avg_points`.
    """
    return sorted(families, key=lambda f: f.get(sort_key, 0), reverse=reverse)
