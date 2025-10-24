import json

# Load config.json
with open("config.json") as f:
    cfg = json.load(f)

# Global variable for easy filename change
FAMILY_MEMBERS_JSON = cfg['file_paths']["vsa_family_db"]
ALL_VERIFIED_DISCORD_MEMBERS_JSON = cfg['file_paths']['all_discord_user_member_database_json_path']
ALL_INSTAGRAM_USERS_IN_GROUPCHAT_THREAD = cfg['file_paths']['instagram_db']

# --- add this helper (right below your other load_* helpers) ---
def _load_instagram_db() -> dict:
    """
    Load the Instagram DB JSON (participants live here).
    Safe if file missing/corrupt.
    """
    try:
        with open(ALL_INSTAGRAM_USERS_IN_GROUPCHAT_THREAD, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _instagram_participant_usernames() -> set[str]:
    """
    Return a lowercase set of usernames from the configured IG DM thread.
    Expected schema (written by your IG sync cog):
      {
        "dm_sync": {
          "participants": [
            {"user_id": 123, "username": "alice", "full_name": "Alice ..."},
            ...
          ]
        }
      }
    """
    db = _load_instagram_db()
    parts = (db.get("dm_sync") or {}).get("participants") or []
    names = {str(p.get("username", "")).strip().lower() for p in parts if p.get("username")}
    return {n for n in names if n}  # drop empties


def load_family_data() -> dict:
    """
    Load the latest family members JSON data each time it's needed.
    """
    with open(FAMILY_MEMBERS_JSON, "r") as f:
        return json.load(f)

# --- update this: optional instagram_username & last-resort IG check ---
def is_family_member(psid: str, instagram_username: str | None = None) -> bool:
    """
    True if PSID is in fam_leads/members/psuedos, OR (last resort)
    if instagram_username is present in the IG DM participants list.
    """
    family_psid_map = load_family_data()
    in_core = (
        psid in family_psid_map.get("fam_leads", {}) or
        psid in family_psid_map.get("fam_members", {}) or
        psid in family_psid_map.get("fam_psuedos", {})
    )
    if in_core:
        return True

    if instagram_username:
        ig_names = _instagram_participant_usernames()
        if instagram_username.strip().lower() in ig_names:
            return True

    return False


# --- update this: allow optional instagram_username & add last-resort check ---
def get_family_role(psid: str, instagram_username: str | None = None) -> str | None:
    """
    Returns the family role for a given PSID (or, last-resort, by IG username).
    Possible returns: "Family Leader", "Member (Official)",
    "Psuedo (Unofficial Member)", or None if not found.

    Order:
      1) fam_leads
      2) fam_members
      3) fam_psuedos
      4) LAST RESORT: if instagram_username is in IG participants -> "Psuedo (Unofficial Member)"
    """
    family_psid_map = load_family_data()

    if psid in family_psid_map.get("fam_leads", {}):
        return "Family Leader"
    elif psid in family_psid_map.get("fam_members", {}):
        return "Member (Official)"
    elif psid in family_psid_map.get("fam_psuedos", {}):
        return "Psuedo (Unofficial Member)"

    # Last-resort IG participants check (only if username provided)
    if instagram_username:
        ig_names = _instagram_participant_usernames()
        if instagram_username.strip().lower() in ig_names:
            return "Psuedo (Unofficial Member)"

    return None



def get_total_verified_users() -> int:
    """
    Loads the verified users JSON and returns the total number of verified users.
    """
    try:
        with open(ALL_VERIFIED_DISCORD_MEMBERS_JSON, "r") as f:
            data = json.load(f)
        verified_users = data.get("verified_users", {})
        return len(verified_users)
    except Exception as e:
        print(f"Error reading verified users: {e}")
        return 0


def get_total_unverified_users() -> int:
    """
    Loads the verified users JSON and returns the total number of unverified users.
    """
    try:
        with open(ALL_VERIFIED_DISCORD_MEMBERS_JSON, "r") as f:
            data = json.load(f)
        unverified_users = data.get("unverified_users", {})
        return len(unverified_users)
    except Exception as e:
        print(f"Error reading unverified users: {e}")
        return 0