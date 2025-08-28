import json

# Load config.json
with open("config.json") as f:
    cfg = json.load(f)

# Global variable for easy filename change
FAMILY_MEMBERS_JSON = cfg['file_paths']["vsa_family_db"]

# Load the family members data once at module load
with open(FAMILY_MEMBERS_JSON, "r") as f:
    family_psid_map = json.load(f)

def is_family_member(psid: str) -> bool:
    """
    Check if the given PSID exists in any of the family JSON categories:
    fam_leads, fam_members, or fam_psuedos.
    """
    return (
        psid in family_psid_map.get("fam_leads", {}) or
        psid in family_psid_map.get("fam_members", {}) or
        psid in family_psid_map.get("fam_psuedos", {})
    )
    

def get_family_role(psid: str) -> str | None:
    """
    Returns the family role for a given PSID.
    Possible returns: "lead", "member", "psuedo", or None if not found.
    """
    if psid in family_psid_map.get("fam_leads", {}):
        return "Family Leader"
    elif psid in family_psid_map.get("fam_members", {}):
        return "Member (Official)"
    elif psid in family_psid_map.get("fam_psuedos", {}):
        return "Psuedo (Unofficial Member)"
    return None