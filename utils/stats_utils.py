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
DISCORD_VERIFIED_MEMBERS_DB = config["file_paths"]["all_discord_user_member_database_json_path"]
CONFIG_JSON_PATH = "config.json"


def load_json(path):
    """Helper to load a JSON file"""
    with open(path, "r") as f:
        return json.load(f)


def get_instagram_by_psid(psid: str) -> str | None:
    """
    Look up the Instagram username of a verified member by PSID.

    Args:
        psid (str): The PSID of the user to search for.

    Returns:
        str | None: The Instagram username if available, else None.
    """
    data = load_json(DISCORD_VERIFIED_MEMBERS_DB)
    verified_users = data.get("verified_users", {})

    for user in verified_users.values():
        general = user.get("general", {})
        if str(general.get("psid")) == str(psid):
            ig = general.get("instagram")
            if ig and str(ig).strip().lower() != "null":
                return ig.strip()
            return None
    return None
    
def get_pseudo_family_members() -> list[dict]:
    """
    Get all pseudo family members from the vsa_family_db JSON.

    Loads the family_and_pseudos_db.json file (path from config.json),
    extracts the "fam_psuedos" section, and returns it as a list of dicts
    including PSID, first_name, and last_name.

    Returns:
        list[dict]: List of pseudo members, each with keys:
                    - psid (str)
                    - first_name (str)
                    - last_name (str)
    """
    # Load config
    config = load_json(CONFIG_JSON_PATH)
    fam_db_path = config["file_paths"]["vsa_family_db"]

    # Load family db
    fam_db = load_json(fam_db_path)
    fam_pseudos = fam_db.get("fam_psuedos", {})

    # Convert to list of dicts
    pseudos_list = []
    for psid, info in fam_pseudos.items():
        pseudos_list.append({
            "psid": str(psid),
            "first_name": info.get("first_name", ""),
            "last_name": info.get("last_name", "")
        })

    return pseudos_list


def count_total_family_members(member_dicts: list[dict]) -> int:
    """
    Count the total number of unique family members across both
    family_and_pseudos_db.json and the provided list of parsed member dictionaries.

    Args:
        member_dicts (list[dict]): List of member dictionaries (parsed members).

    Returns:
        int: Total unique people across fam_leads, fam_members, fam_pseudos,
             and the provided member_dicts list.
    """
    # Load config
    config = load_json(CONFIG_JSON_PATH)
    fam_db_path = config["file_paths"]["vsa_family_db"]

    # Load family db
    fam_db = load_json(fam_db_path)
    fam_leads = fam_db.get("fam_leads", {})
    fam_members = fam_db.get("fam_members", {})
    fam_pseudos = fam_db.get("fam_psuedos", {})

    # Collect PSIDs
    parsed_psids = {str(m["psid"]) for m in member_dicts}
    leads_psids = set(fam_leads.keys())
    members_psids = set(fam_members.keys())
    pseudos_psids = set(fam_pseudos.keys())

    # Combine all into one big set of unique psids
    all_unique_psids = leads_psids | members_psids | pseudos_psids | parsed_psids

    return len(all_unique_psids)


def sync_family_members(member_dicts: list[dict]):
    """
    Sync the given list of member dictionaries with the fam_members section
    of the vsa_family_db JSON file.

    Rules:
    - Skip Family Leaders (role_key == "Family Leader"). They belong in fam_leads only.
    - All other roles are synced into fam_members.
    - If the JSON already matches exactly, no changes are made and a message is logged.
    - Otherwise, fam_members is updated: new members added, removed ones deleted.

    Args:
        member_dicts (list[dict]): List of parsed member dictionaries to sync.
    """
    # Load config
    config = load_json(CONFIG_JSON_PATH)
    fam_name_from_config = config["general"]["google_sheets_fam_name"]

    if not member_dicts:
        print("⚠️ No members provided, skipping sync.")
        return

    # Ensure family match (case-insensitive)
    fam_names = {m.get("family_name", "").lower() for m in member_dicts if m.get("family_name")}
    if fam_name_from_config.lower() not in fam_names:
        print(f"❌ Family mismatch: provided list families = {fam_names}, "
              f"but config expects '{fam_name_from_config}'. Skipping sync.")
        return

    # Load family DB
    fam_db_path = config["file_paths"]["vsa_family_db"]
    fam_db = load_json(fam_db_path)
    fam_members = fam_db.get("fam_members", {})

    # Build desired state: members that should be in fam_members
    desired_fam_members = {}
    for member in member_dicts:
        role = member.get("role_key", "").lower()
        if role == "family leader":
            # Skip leaders
            continue
        psid = str(member["psid"])
        desired_fam_members[psid] = {
            "first_name": member.get("first_name", ""),
            "last_name": member.get("last_name", "")
        }

    # Compare current vs desired
    if fam_members == desired_fam_members:
        #print(f"✅ JSON looks good. No changes needed. All {len(desired_fam_members)} / {len(desired_fam_members)} members already synced. Skipping...")
        return

    # Otherwise, sync changes
    input_psids = set(desired_fam_members.keys())
    current_psids = set(fam_members.keys())

    # Add/update members
    for psid, info in desired_fam_members.items():
        if psid not in fam_members or fam_members[psid] != info:
            fam_members[psid] = info
            print(f"✅ Synced member {psid}: {info['first_name']} {info['last_name']}")

    # Remove members not in desired list
    to_remove = current_psids - input_psids
    for psid in to_remove:
        removed = fam_members.pop(psid, None)
        if removed:
            print(f"🗑️ Removed member {psid}: {removed['first_name']} {removed['last_name']}")

    # Save updated JSON
    fam_db["fam_members"] = fam_members
    with open(fam_db_path, "w", encoding="utf-8") as f:
        json.dump(fam_db, f, indent=2, ensure_ascii=False)

    print(f"✅ Finished syncing fam_members for '{fam_name_from_config}'. "
          f"Now {len(fam_members)} members are in sync.")



def get_family_members(family_name: str) -> list[dict]:
    """
    Get all member records belonging to a specific family.

    This function loads the parsed VSA member data JSON (defined by
    VSA_PARSED_ALL_MEMBER_DATA_JSON_PATH) and searches the "parsed_members"
    section. It collects the full member dictionaries for all members whose
    "family_name" matches the provided family_name argument.

    Args:
        family_name (str): The family name to search for (case-insensitive match).

    Returns:
        list[dict]: A list of member dictionaries belonging to the given family.
                    If no members match, returns an empty list.

    Notes:
        - Members with empty or null "family_name" are ignored.
        - Family name comparison is case-insensitive.
    """
    data = load_json(VSA_PARSED_ALL_MEMBER_DATA_JSON_PATH)
    parsed_members = data.get("parsed_members", {})

    results = []
    for member in parsed_members.values():
        fam = member.get("family_name")
        if fam and fam.strip() and fam.lower() == family_name.lower():
            results.append(member)

    return results


def get_family_total_points(family_name: str) -> int:
    """
    Calculate the total points for all members in a specific family.

    Args:
        family_name (str): The family name to search for (case-insensitive).

    Returns:
        int: The total sum of 'points' across all members in the family.
    """
    members = get_family_members(family_name)
    return sum(member.get("points", 0) for member in members)

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
