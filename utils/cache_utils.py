import os
import json
from pathlib import Path
from typing import Dict, List

# === CONFIG & CACHE PATHS ===
BASE_DIR   = os.path.dirname(__file__)
ROOT_DIR   = os.path.abspath(os.path.join(BASE_DIR, '..'))
CONFIG     = os.path.join(ROOT_DIR, 'config.json')
PARSED_KEY = 'parsed_vsa_member_data_and_events_info_file'

# Load config template once
with open(CONFIG, 'r') as f:
    _CFG_TEMPLATE = json.load(f)

# Raw vs. Parsed cache
RAW_CACHE_PATH    = os.path.join(ROOT_DIR, _CFG_TEMPLATE['file_paths']['vsa_google_spreadsheet_save_file'])
PARSED_CACHE_PATH = os.path.join(ROOT_DIR, _CFG_TEMPLATE['file_paths'][PARSED_KEY])

# --- Cache Loaders ---
def load_raw_cache() -> dict:
    """Return raw spreadsheet JSON (or empty dict on failure)."""
    try:
        return json.loads(Path(RAW_CACHE_PATH).read_text())
    except Exception:
        return {}

def load_parsed_cache() -> dict:
    """Return parsed spreadsheet JSON (or empty dict on failure)."""
    try:
        return json.loads(Path(PARSED_CACHE_PATH).read_text())
    except Exception:
        return {}

# --- Legacy raw getters ---
def get_family_stats_raw() -> list:
    return load_raw_cache().get('family_stats', [])

def get_event_titles_raw() -> list:
    return load_raw_cache().get('event_titles', [])

def get_master_data_raw() -> list:
    return load_raw_cache().get('all_vsa_member_data', [])

# --- Parsed getters ---
def get_family_stats() -> Dict[str, dict]:
    """Map family_name -> stats dict."""
    return load_parsed_cache().get('family_stats', {})

def get_events_info() -> Dict[str, dict]:
    """Map event_tag -> event info dict."""
    return load_parsed_cache().get('events_info', {})

def get_parsed_members() -> Dict[str, dict]:
    """Map psid -> member info dict."""
    return load_parsed_cache().get('parsed_members', {})

def list_parsed_members() -> List[dict]:
    """List of all parsed member dicts."""
    return list(get_parsed_members().values())

def list_family_stats() -> List[dict]:
    """List of all parsed family stats dicts."""
    return list(get_family_stats().values())

# --- Parsed leads extractor ---
def get_parsed_family_leads() -> Dict[str, List[dict]]:
    """
    Build mapping: family_name -> list of leads (role_key 'FL').
    Each entry: { first_name, last_name, psid }.
    """
    leads_map: Dict[str, List[dict]] = {}
    for member in get_parsed_members().values():
        if member.get('role_key') == 'FL':
            fam = member.get('family_name')
            psid = member.get('psid')
            if fam and psid:
                leads_map.setdefault(fam, []).append({
                    'first_name': member.get('first_name'),
                    'last_name':  member.get('last_name'),
                    'psid':       str(psid)
                })
    return leads_map

# --- Sync functions ---

def sync_family_settings() -> bool:
    """
    1. Sync 'family_settings' keys in config.json with parsed sheet families.
    2. Write changes atomically if needed.
    3. Always call sync_family_leads() after key sync.
    Returns True if any modifications occurred.
    """
    modified = False
    parsed_families = set(get_family_stats().keys()) - {'Not in a family'}

    # Load and mutate config in memory
    cfg_path = Path(CONFIG)
    full_cfg = json.loads(cfg_path.read_text())
    fs = full_cfg.setdefault('family_settings', {})
    cfg_fams = set(fs.keys())

    # Add new families skeleton
    for fam in parsed_families - cfg_fams:
        fs[fam] = {
            'short_name':       None,
            'abbreviation':     None,
            'family_role_id':   None,
            'family_emoji':     None,
            'logo_image_url':   None,
            'banner_image_url': None,
            'discord_link':     None,
            'instagram':        None,
            'website':          None,
            'description':      None,
            'leads':           []
        }
        modified = True
    # Remove old families
    for fam in cfg_fams - parsed_families:
        fs.pop(fam, None)
        modified = True

    # Persist key sync if changed
    if modified:
        tmp = cfg_path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(full_cfg, indent=2))
        os.replace(tmp, cfg_path)

    # Always sync leads
    leads_modified = sync_family_leads()
    return modified or leads_modified


def sync_family_leads() -> bool:
    """
    Merge parsed leads into config.json family_settings:
      - Match by PSID: update names if changed.
      - Else match single case-insensitive name-only entry lacking PSID: assign PSID.
      - Else append new lead entry.
    Non-destructive of unmatched existing leads.
    Returns True if config.json was modified.
    """
    modified = False
    parsed_leads = get_parsed_family_leads()
    #print(parsed_leads)

    # Load config in memory
    cfg_path = Path(CONFIG)
    full_cfg = json.loads(cfg_path.read_text())
    fs = full_cfg.get('family_settings', {})

    for fam, new_leads in parsed_leads.items():
        if fam not in fs:
            continue
        existing = fs[fam].setdefault('leads', [])
        for nl in new_leads:
            psid = nl['psid']
            first_n = nl['first_name'] or ''
            last_n  = nl['last_name'] or ''
            # 1) Match by PSID
            for ex in existing:
                if ex.get('psid') == psid:
                    # update names if changed
                    if (ex.get('first_name') != nl['first_name'] or
                        ex.get('last_name')  != nl['last_name']):
                        ex['first_name'] = nl['first_name']
                        ex['last_name']  = nl['last_name']
                        modified = True
                    break
            else:
                # 2) single name-only match (case-insensitive) and no PSID
                name_matches = [ex for ex in existing
                                if not ex.get('psid')
                                and ex.get('first_name', '').strip().lower() == first_n.strip().lower()
                                and ex.get('last_name',  '').strip().lower() == last_n.strip().lower()]
                if len(name_matches) == 1:
                    name_matches[0]['psid'] = psid
                    modified = True
                else:
                    # 3) new lead
                    existing.append({
                        'first_name': nl['first_name'],
                        'last_name':  nl['last_name'],
                        'psid':       psid
                    })
                    modified = True

    # Persist leads sync if changed
    if modified:
        tmp = cfg_path.with_suffix('.json.tmp')
        tmp.write_text(json.dumps(full_cfg, indent=2))
        os.replace(tmp, cfg_path)

    return modified
