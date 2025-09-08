"""
stats_utils.py

Shared functions for:
 - parsing and normalizing member records
 - sorting and ranking logic
 - profile‐cog ranking helpers
 - parsing Family‐Tracker data
 - parsing event titles
"""
from datetime import datetime
from utils import cache_utils
import json


with open("config.json", "r") as f:
    config = json.load(f)
VSA_PARSED_ALL_MEMBER_DATA_JSON_PATH = config["file_paths"]["parsed_vsa_member_data_and_events_info_file"]
CONFIG_JSON_PATH = "config.json"


def load_json(path):
    """Helper to load a JSON file"""
    with open(path, "r") as f:
        return json.load(f)


def is_vsa_officer(psid: int) -> bool:

    vsa_db = load_json(VSA_PARSED_ALL_MEMBER_DATA_JSON_PATH)

    members = vsa_db.get("parsed_members", {})

    psid_str = str(psid)
    if psid_str not in members:
        return False

    role_key = members[psid_str].get("role_key", "")
    return role_key.lower() == "officer"

# ── NEW FUNCTIONS FOR TIMEFRAME-BASED FAMILY RANKINGS ─────────────────────────

def get_family_size_rank():
    """
    Returns the rank (1-based) of your family based on total number of members
    compared to all families in the family_stats.
    """
    data = load_json(VSA_PARSED_ALL_MEMBER_DATA_JSON_PATH)
    families = data.get("family_stats", {})

    # Create list of (family_name, member_count)
    family_counts = [(f["family"], f["member_count"]) for f in families.values()]

    # Sort descending by member_count
    sorted_families = sorted(family_counts, key=lambda x: x[1], reverse=True)

    # Get my family name
    my_family = load_json(CONFIG_JSON_PATH)["general"]["google_sheets_fam_name"]

    # Find rank (1-based)
    rank = next((i + 1 for i, (fam, _) in enumerate(sorted_families) if fam == my_family), None)

    return rank


def get_family_pts_per_member_ranking():
    """
    Returns a sorted list of families by total points / member_count (descending),
    along with each family's pts_per_member value.
    """
    data = load_json(VSA_PARSED_ALL_MEMBER_DATA_JSON_PATH)
    family_stats = data.get("family_stats", {})

    ranking = []
    for fam_name, stats in family_stats.items():
        member_count = stats.get("member_count", 1)  # avoid division by zero
        total_points = stats.get("total_points", 0)
        pts_per_member = total_points / member_count if member_count > 0 else 0
        ranking.append({
            "family": fam_name,
            "pts_per_member": pts_per_member,
            "total_points": total_points,
            "member_count": member_count
        })

    # Sort descending by pts_per_member
    ranking_sorted = sorted(ranking, key=lambda f: f["pts_per_member"], reverse=True)
    return ranking_sorted


def get_my_family_overall_rank():
    """
    Returns the 1-based rank (int) of the current user's family
    based on overall total points from family_stats in parsed JSON.
    """
    config = load_json(CONFIG_JSON_PATH)
    my_family = config["general"]["google_sheets_fam_name"]

    rank, _ = get_overall_family_rank(my_family)
    return rank



def get_family_points_rank_in_timeframe(start_date: str, end_date: str):
    """
    Returns a list of tuples (family_name, points) ranked descending by total points
    earned within the timeframe.
    """
    contributors = get_contributors_in_timeframe(start_date, end_date)
    family_points = {}
    for member in contributors:
        fam = member.get("family_name", "")
        pts = sum(member["event_points"])
        family_points[fam] = family_points.get(fam, 0) + pts
    return sorted(family_points.items(), key=lambda x: x[1], reverse=True)


def get_family_contributor_rank_in_timeframe(start_date: str, end_date: str):
    """
    Returns a list of tuples (family_name, num_contributors) ranked descending
    by number of contributing members within the timeframe.
    """
    contributors = get_contributors_in_timeframe(start_date, end_date)
    family_counts = {}
    for member in contributors:
        fam = member.get("family_name", "")
        family_counts[fam] = family_counts.get(fam, 0) + 1
    return sorted(family_counts.items(), key=lambda x: x[1], reverse=True)


def get_family_pts_per_member_rank_in_timeframe(start_date: str, end_date: str):
    """
    Returns a list of tuples (family_name, pts_per_member) ranked descending by
    average points per contributing member within the timeframe.
    """
    contributors = get_contributors_in_timeframe(start_date, end_date)
    family_points = {}
    family_members = {}
    for member in contributors:
        fam = member.get("family_name", "")
        pts = sum(member["event_points"])
        family_points[fam] = family_points.get(fam, 0) + pts
        family_members[fam] = family_members.get(fam, 0) + 1

    pts_per_member = {fam: family_points[fam]/family_members[fam] for fam in family_points}
    return sorted(pts_per_member.items(), key=lambda x: x[1], reverse=True)


def get_overall_family_rank(family_name: str):
    """
    Returns the rank and total_points of a specific family based on
    overall family_stats from the parsed JSON.
    """
    data = load_json(VSA_PARSED_ALL_MEMBER_DATA_JSON_PATH)
    family_stats = data.get("family_stats", {})
    sorted_families = sorted(family_stats.items(), key=lambda x: x[1]["total_points"], reverse=True)

    for idx, (fam, stats) in enumerate(sorted_families, start=1):
        if fam == family_name:
            return idx, stats["total_points"]
    return None, 0


def get_full_family_leaderboard():
    """
    Returns the full family_stats dictionary from parsed JSON.
    """
    data = load_json(VSA_PARSED_ALL_MEMBER_DATA_JSON_PATH)
    return data.get("family_stats", {})


def get_contributors_in_timeframe(start_date: str, end_date: str):
    """
    Returns a list of member dicts who attended at least 1 event in the timeframe.

    Parameters:
        start_date (str): "MM/DD/YYYY"
        end_date (str): "MM/DD/YYYY"
    """
    data = load_json(VSA_PARSED_ALL_MEMBER_DATA_JSON_PATH)
    events_info = data["events_info"]
    parsed_members = data["parsed_members"]

    # Convert dates to datetime
    start_dt = datetime.strptime(start_date, "%m/%d/%Y")
    end_dt = datetime.strptime(end_date, "%m/%d/%Y")

    # Map event indices to dates
    event_list = list(events_info.items())
    event_indices_in_range = []
    for idx, (event_key, event) in enumerate(event_list):
        event_dt = datetime.strptime(event["date"], "%m/%d/%Y")
        if start_dt <= event_dt <= end_dt:
            event_indices_in_range.append(idx)

    # Find members with points > 0 in any event in range
    contributors = []
    for member in parsed_members.values():
        for idx in event_indices_in_range:
            if member["event_points"][idx] > 0:
                contributors.append(member)
                break  # only need one event to count
    return contributors


def get_family_contributors_in_timeframe(start_date: str, end_date: str):
    """
    Returns a list of member dicts who attended at least 1 event in the timeframe
    and belong to the family defined in config.json's google_sheets_fam_name.
    """
    config = load_json(CONFIG_JSON_PATH)
    family_name = config["general"]["google_sheets_fam_name"]

    all_contributors = get_contributors_in_timeframe(start_date, end_date)
    family_contributors = [m for m in all_contributors if m["family_name"] == family_name]

    return family_contributors

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
