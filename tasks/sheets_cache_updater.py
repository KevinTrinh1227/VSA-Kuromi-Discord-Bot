import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo
import re

import discord
from discord.ext import commands, tasks

from google.oauth2 import service_account
from googleapiclient.discovery import build

from utils import stats_utils
from utils.leaderboard_utils import regenerate_leaderboard_pages
from utils import cache_utils

# ── CONFIG & SHEETS CLIENT SETUP ─────────────────────────────────────────────

CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.json')
with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)

SPREADSHEET_ID        = config['google_sheets']['spreadsheet_id']
RAW_CACHE_PATH        = config['file_paths']['vsa_google_spreadsheet_save_file']
PARSED_CACHE_PATH     = config['file_paths']['parsed_vsa_member_data_and_events_info_file']
SERVICE_ACCOUNT_FILE  = config['file_paths']['vsa_google_service_account_file']
SCOPES                = ['https://www.googleapis.com/auth/spreadsheets.readonly']

credentials = service_account.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, scopes=SCOPES
)
service = build('sheets', 'v4', credentials=credentials)

# ── COG ───────────────────────────────────────────────────────────────────────

class SheetsCacheUpdater(commands.Cog):
    """Fetches spreadsheet data every minute, caches raw & parsed data, and regenerates leaderboard images."""
    def __init__(self, client):
        self.client = client

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.update_cache.is_running():
            await self.update_cache()   # run first immediately
            self.update_cache.start()   # then start loop


    def cog_unload(self):
        self.update_cache.cancel()

    @tasks.loop(minutes=1.0)
    async def update_cache(self):
        try:
            # ── 1) FETCH RAW DATA ────────────────────────────────
            family_stats_raw = self._get_data("Sheet9FamTracker!A2:D6")
            #print(family_stats_raw)
            full_master_data = self._get_data("Sheet9!A1:LA50")

            # Print header
            #print(f"{'PSID':<10} | {'First Name':<12} | {'Last Name':<12} | {'Membership':<15} | {'VSA Family':<12} | {'Total Points':<12}")
            #print("-" * 85)

            # Print rows
            for row in full_master_data[1:]:
                psid = row[0] if len(row) > 0 else ""
                first = row[1] if len(row) > 1 else ""
                last = row[2] if len(row) > 2 else ""
                membership = row[3] if len(row) > 3 else ""
                vsa_family = row[4] if len(row) > 4 and row[4].strip() else "Not In Fam"
                total_points = row[5] if len(row) > 5 else "0"

                #print(f"{psid:<10} | {first:<12} | {last:<12} | {membership:<15} | {vsa_family:<12} | {total_points:<12}")

            raw_member_data  = full_master_data[2:]

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
            for header in full_master_data[:1]:
                raw_titles.extend(header[6:])

            seen = set()
            valid_event_titles = [
                t for t in raw_titles
                if t and re.match(r"\d{1,2}-\d{1,2}-\d{4}", t) and t not in seen and not seen.add(t)
            ]

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

            # b) carry over existing flags for events
            try:
                old_parsed     = json.load(open(PARSED_CACHE_PATH))
                raw_old_events = old_parsed.get("events_info", {})
            except:
                raw_old_events = {}

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

            parsed_events_list = stats_utils.parse_event_titles(
                valid_event_titles,
                existing_events=existing_events
            )
            parsed_events_map = {
                evt["original"]: {
                    "date":        evt["date"],
                    "name":        evt["name"],
                    "event_types": {
                        "is_general_meeting": evt.get("is_general_meeting", False),
                        "is_tlp":             evt.get("is_tlp", False),
                        "is_sale":            evt.get("is_sale", False),
                    }
                }
                for evt in parsed_events_list
            }

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
                    "psid":         psid,
                    "first_name":   first,
                    "last_name":    last,
                    "role_key":     role,
                    "family_name":  family,
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

            # pull old leaderboards out of disk
            try:
                old_data      = json.load(open(PARSED_CACHE_PATH))
                old_mem_psids = old_data.get("leaderboards", {}).get("member_points", [])
                old_fam_names = old_data.get("leaderboards", {}).get("families_pts_mem", [])
            except:
                old_mem_psids = []
                old_fam_names = []

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

            # ── 6) REGENERATE CHANGED PAGE IMAGES ─────────────────
            """
            pillow_conf = config["features"]["leaderboards"]["pillow_image_template"]["leaderboards"]
            family_conf = config["family_settings"]
            out_dir     = os.path.join("assets", "outputs", "leaderboards")
            # use the first connected guild’s icon URL if available
            guild   = next(iter(self.client.guilds), None)
            fallback = guild.icon.url if guild and guild.icon else None

            
            regenerate_leaderboard_pages(
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
            ) """
            
            # ── 7) SYNC FAMILIES FROM GOOGLE SHEETS TO CONFIG.JSON ─────────────────
            #updated_family_settings_in_config = cache_utils.sync_family_settings()

        except Exception as e:
            print(f"[{datetime.now()}] ERROR: failed to update spreadsheet cache: {e}")

    def _get_data(self, sheet_range):
        sheet  = service.spreadsheets()
        result = sheet.values().get(
            spreadsheetId=SPREADSHEET_ID,
            range=sheet_range
        ).execute()
        return result.get('values', [])

async def setup(client):
    await client.add_cog(SheetsCacheUpdater(client))
