import json

# Global variable for easy filename change
FAMILY_MEMBERS_JSON = "list_of_family_members.json"

# Load the family members data once at module load
with open(FAMILY_MEMBERS_JSON, "r") as f:
    family_psid_map = json.load(f)

def is_family_member(psid: str) -> bool:
    """
    Check if the given PSID exists in the family members JSON.
    """
    return psid in family_psid_map
