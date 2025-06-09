# users_utils.py
import json
import os


VERIFIED_UNVERIFIED_USER_DATA_PATH = 'users_database.json'

def get_verified_users():
    with open(VERIFIED_UNVERIFIED_USER_DATA_PATH, 'r') as f:
        data = json.load(f)
    # Return only the dictionary under "verified_users"
    #print(data.get("verified_users", {}))
    return data.get("verified_users", {})


def save_verified_users(verified_users_dict):
    # Load entire file if it exists
    if os.path.exists(VERIFIED_UNVERIFIED_USER_DATA_PATH):
        with open(VERIFIED_UNVERIFIED_USER_DATA_PATH, 'r') as f:
            full_data = json.load(f)
    else:
        full_data = {}

    full_data["verified_users"] = verified_users_dict

    with open(VERIFIED_UNVERIFIED_USER_DATA_PATH, 'w') as f:
        json.dump(full_data, f, indent=2)
        
        
        
def get_unverified_users():
    with open(VERIFIED_UNVERIFIED_USER_DATA_PATH, 'r') as f:
        data = json.load(f)
    # Return only the dictionary under "unverified_users"
    return data.get("unverified_users", {})


def save_unverified_users(unverified_users_dict):
    # Load entire file if it exists
    if os.path.exists(VERIFIED_UNVERIFIED_USER_DATA_PATH):
        with open(VERIFIED_UNVERIFIED_USER_DATA_PATH, 'r') as f:
            full_data = json.load(f)
    else:
        full_data = {}

    full_data["unverified_users"] = unverified_users_dict

    with open(VERIFIED_UNVERIFIED_USER_DATA_PATH, 'w') as f:
        json.dump(full_data, f, indent=2)
