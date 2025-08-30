import json

# Load config.json
with open("config.json") as f:
    cfg = json.load(f)

# Global variable for easy filename change
FAMILY_MEMBERS_JSON = cfg['file_paths']["vsa_family_db"]

def load_family_data() -> dict:
    """
    Load the latest family members JSON data each time it's needed.
    """
    with open(FAMILY_MEMBERS_JSON, "r") as f:
        return json.load(f)

def is_family_member(psid: str) -> bool:
    """
    Check if the given PSID exists in any of the family JSON categories:
    fam_leads, fam_members, or fam_psuedos.
    """
    family_psid_map = load_family_data()
    return (
        psid in family_psid_map.get("fam_leads", {}) or
        psid in family_psid_map.get("fam_members", {}) or
        psid in family_psid_map.get("fam_psuedos", {})
    )

def get_family_role(psid: str) -> str | None:
    """
    Returns the family role for a given PSID.
    Possible returns: "Family Leader", "Member (Official)", 
    "Psuedo (Unofficial Member)", or None if not found.
    """
    family_psid_map = load_family_data()
    if psid in family_psid_map.get("fam_leads", {}):
        return "Family Leader"
    elif psid in family_psid_map.get("fam_members", {}):
        return "Member (Official)"
    elif psid in family_psid_map.get("fam_psuedos", {}):
        return "Psuedo (Unofficial Member)"
    return None


def get_total_verified_users() -> int:
    """
    Loads the verified users JSON and returns the total number of verified users.
    """
    try:
        with open(FAMILY_MEMBERS_JSON, "r") as f:
            data = json.load(f)
        verified_users = data.get("verified_users", {})
        return len(verified_users)
    except Exception as e:
        print(f"Error reading verified users: {e}")
        return 0