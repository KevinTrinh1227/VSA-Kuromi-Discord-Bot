import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import traceback  # add at top of file
import asyncio

import discord
from discord.ext import commands, tasks

import gspread
from google.oauth2.service_account import Credentials

from utils import stats_utils
from utils.leaderboard_utils import regenerate_leaderboard_pages
from utils import cache_utils
from utils import profile_utils

# ── CONFIG & SHEETS CLIENT SETUP ─────────────────────────────────────────────

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.json')
    
def get_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

# ✅ Load config here so global vars below work
config = get_config()


SPREADSHEET_ID        = config['google_sheets']['spreadsheet_id']
RAW_CACHE_PATH        = config['file_paths']['vsa_google_spreadsheet_save_file']
PARSED_CACHE_PATH     = config['file_paths']['parsed_vsa_member_data_and_events_info_file']


SERVICE_ACCOUNT_FILE  = config['file_paths']['vsa_google_service_account_file']
SCOPES                = ['https://www.googleapis.com/auth/spreadsheets.readonly']

# Build gspread client
def get_gspread_client():
    creds = Credentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=SCOPES)
    return gspread.authorize(creds)

FAMILY_CELL_RANGE     = config['google_sheets']['family_data_cell_range']
MEMBER_CELL_RANGE     = config['google_sheets']['member_data_cell_range']



# ── COG ───────────────────────────────────────────────────────────────────────

class SheetsCacheUpdater(commands.Cog):
    """Fetches spreadsheet data every minute, caches raw & parsed data, and regenerates leaderboard images."""
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.update_cache.is_running():
            # await self.update_cache()   # run first immediately
            self.update_cache.start()   # then start loop


    def cog_unload(self):
        self.update_cache.cancel()

    @tasks.loop(minutes=5.0)
    async def update_cache(self):
        config = get_config()
        try:
            # ── 1) FETCH RAW DATA ────────────────────────────────
            family_stats_raw = await self._get_data(FAMILY_CELL_RANGE)  # "Family Tracker!B3:E9"
            full_master_data = await self._get_data(MEMBER_CELL_RANGE)  # "Master Sheet!D1:DZ1000"
            raw_member_data  = full_master_data[2:]

            #print("------------------\n\n")
            #print(full_master_data[0])

            # a) Dedupe master_data by PSID, keeping highest points
            psid_map = {}
            for row in raw_member_data:
                if len(row) < 6:
                    continue
                psid = row[0].strip()
                if not psid:
                    continue
                try:
                    pts = int(row[5].strip())
                except:
                    pts = 0
                if psid not in psid_map or pts > psid_map[psid][1]:
                    psid_map[psid] = (row, pts)
            master_data_with_psid = [entry[0] for entry in psid_map.values()]

            # b) Extract and dedupe event titles (cols 7+ of first two header rows)
            raw_titles = []
            for header in full_master_data[:2]:
                raw_titles.extend(header[6:])
            seen = set()
            valid_event_titles = []
            for t in raw_titles:
                if t and t not in seen:
                    valid_event_titles.append(t.strip())
                    seen.add(t)

            # c) Compute CST timestamp
            cst_now   = datetime.now(ZoneInfo("America/Chicago"))
            timestamp = cst_now.strftime("%Y-%m-%d %H:%M:%S %Z")

            # ── 2) WRITE RAW CACHE ────────────────────────────────
            os.makedirs(os.path.dirname(RAW_CACHE_PATH), exist_ok=True)
            raw_cache = {
                "last_updated":        timestamp,
                "family_stats":        family_stats_raw,
                "event_titles":        valid_event_titles,
                "all_vsa_member_data": master_data_with_psid
            }
            with open(RAW_CACHE_PATH, "w") as f:
                json.dump(raw_cache, f, indent=2)

            # ── 3) PARSE & STRUCTURE DATA ────────────────────────
            parsed_family_stats = stats_utils.parse_family_tracker_data(family_stats_raw)

            # a) carry over existing flags for events
            # ── cache state lives on the cog instance ──
            if not hasattr(self, "_parsed_cache_state"):
                self._parsed_cache_state = {}

            old_parsed = self._parsed_cache_state or {}
            raw_old_events = old_parsed.get("events_info", {})
            old_mem_psids  = old_parsed.get("leaderboards", {}).get("member_points", [])
            old_fam_names  = old_parsed.get("leaderboards", {}).get("families_pts_mem", [])


            existing_events = []
            if isinstance(raw_old_events, dict):
                for orig, details in raw_old_events.items():
                    et = details.get("event_types", {})
                    existing_events.append({
                        "original":           orig,
                        "date":               details.get("date", ""),
                        "name":               details.get("name", ""),
                        "is_general_meeting": et.get("is_general_meeting", False),
                        "is_tlp":             et.get("is_tlp", False),
                        "is_sale":            et.get("is_sale", False),
                    })
            elif isinstance(raw_old_events, list):
                existing_events = raw_old_events

            # b) Parse event titles into structured dict format (MM/DD/YYYY + name + event_number)
            parsed_events_map = {}
            for idx, evt in enumerate(valid_event_titles, start=1):  # start counting from 1
                try:
                    parts = evt.split(" ", 1)
                    if len(parts) < 2:
                        continue
                    raw_date, raw_name = parts[0].strip(), parts[1].strip()

                    try:
                        dt = datetime.strptime(raw_date, "%m/%d/%Y")
                        formatted_date = dt.strftime("%m/%d/%Y")  # normalize to MM/DD/YYYY
                    except ValueError:
                        continue  # skip if not a valid date

                    # 🔑 Use helper functions from profile_utils to set flags dynamically
                    parsed_events_map[evt] = {
                        "event_number": idx,   # new attribute
                        "date": formatted_date,
                        "name": raw_name or "Unnamed Event",
                        "event_types": {
                            "is_general_meeting": profile_utils.is_gm_event(raw_name),
                            "is_tlp":             profile_utils.is_tlp_event(raw_name),
                            "is_sale":            profile_utils.is_sale_event(raw_name),
                            "is_volunteering":    profile_utils.is_volunteering_event(raw_name),
                        }
                    }
                except Exception as e:
                    print(f"[update_cache] Failed to parse event '{evt}': {e}")

                    
            #print(parsed_events_map)

            # c) Build parsed_members
            parsed_members_list = []
            for row in master_data_with_psid:
                psid   = row[0].strip()
                first  = row[1].strip() if len(row) > 1 else ""
                last   = row[2].strip() if len(row) > 2 else ""
                role   = row[3].strip() if len(row) > 3 else ""
                family = row[4].strip() if len(row) > 4 else "No Family"
                try:
                    total_pts = int(row[5].strip())
                except:
                    total_pts = 0

                raw_vals     = row[6:]
                event_points = [
                    int(raw_vals[i].strip()) if i < len(raw_vals) and raw_vals[i].strip().isdigit() else 0
                    for i in range(len(valid_event_titles))
                ]

                parsed_members_list.append({
                    "psid":         psid or "N/A",
                    "first_name":   first or "N/A",
                    "last_name":    last or "N/A",
                    "role_key":     role or "N/A",
                    "family_name":  family or "No Family",
                    "points":       total_pts,
                    "event_points": event_points
                })

            parsed_family_stats_map = { fam["family"]: fam for fam in parsed_family_stats }
            parsed_members_map      = { m["psid"]: m for m in parsed_members_list }

            # ── 4) PRE-COMPUTE LEADERBOARDS ───────────────────────
            member_leaderboard = sorted(
                parsed_members_map.values(),
                key=lambda m: m["points"],
                reverse=True
            )
            new_mem_psids = [m["psid"] for m in member_leaderboard]

            family_leaderboard = sorted(
                parsed_family_stats_map.values(),
                key=lambda f: f["avg_points"],
                reverse=True
            )
            new_fam_names = [f["family"] for f in family_leaderboard]

            # ── 5) WRITE PARSED CACHE ─────────────────────────────
            os.makedirs(os.path.dirname(PARSED_CACHE_PATH), exist_ok=True)
            parsed_cache = {
                "last_updated_and_parsed": timestamp,
                "family_stats":            parsed_family_stats_map,
                "events_info":             parsed_events_map,
                "parsed_members":          parsed_members_map,
                "leaderboards": {
                    "member_points":    new_mem_psids,
                    "families_pts_mem": new_fam_names
                }
            }
            with open(PARSED_CACHE_PATH, "w") as f:
                json.dump(parsed_cache, f, indent=2)
                
            # later, after writing parsed_cache:
            self._parsed_cache_state = parsed_cache

            # ── 6) REGENERATE CHANGED PAGE IMAGES ─────────────────
            pillow_conf = config["features"]["leaderboards"]["pillow_image_template"]["leaderboards"]
            family_conf = config["family_settings"]
            out_dir     = os.path.join("assets", "outputs", "leaderboards")
            # use the first connected guild’s icon URL if available
            guild   = next(iter(self.client.guilds), None)
            fallback = guild.icon.url if guild and guild.icon else "assets/overlays/default_logo.png"


            await regenerate_leaderboard_pages(
                old_mem_psids,
                new_mem_psids,
                parsed_members_map,
                old_fam_names,
                new_fam_names,
                parsed_family_stats_map,
                pillow_conf,
                family_conf,
                out_dir,
                fallback
            )
            
            # ── 7) SYNC FAMILIES FROM GOOGLE SHEETS TO CONFIG.JSON ─────────────────
            updated_family_settings_in_config = cache_utils.sync_family_settings()
            if updated_family_settings_in_config:  
                print(f"Updated Family Settings Config: {updated_family_settings_in_config}")
            

        except Exception as e:
            print(f"[{datetime.now()}] Failed to update spreadsheet cache: {e}")
            traceback.print_exc()
            
        finally:
            del raw_member_data, psid_map, master_data_with_psid
            del parsed_members_list, parsed_family_stats_map, parsed_members_map



    async def _get_data(self, sheet_range: str):
        """Return values for given range using gspread (non-blocking, thread offload)."""
        try:
            def fetch():
                gc = get_gspread_client()
                sh = gc.open_by_key(SPREADSHEET_ID)

                # Split into sheet name + range if present
                if "!" in sheet_range:
                    sheet_name, cell_range = sheet_range.split("!", 1)
                    ws = sh.worksheet(sheet_name.replace("'", "").strip())
                    return ws.get(cell_range.strip())
                else:
                    # no explicit cell range, just return entire sheet
                    ws = sh.worksheet(sheet_range.replace("'", "").strip())
                    return ws.get_all_values()

            return await asyncio.to_thread(fetch)

        except Exception as e:
            print(f"[get_data] Failed fetching {sheet_range}: {e}")
            return []

async def setup(client):
    await client.add_cog(SheetsCacheUpdater(client))
