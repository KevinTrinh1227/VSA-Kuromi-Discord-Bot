# server_stats.py
import discord
from discord.ext import tasks, commands
import json
import os
import logging
import asyncio

# ─────────────────────────────────────────────────────────────────────────────
# Logging
# ─────────────────────────────────────────────────────────────────────────────
log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [server_stats] %(message)s")

# ─────────────────────────────────────────────────────────────────────────────
# Config
# ─────────────────────────────────────────────────────────────────────────────
with open('config.json', 'r') as f:
    cfg = json.load(f)

ENABLE    = bool(cfg["features"]["server_stats"]["enable_feature"])

FAM_ID    = int(cfg["role_ids"]["family_member"])
LEAD_ID   = int(cfg["role_ids"]["family_lead"])

CHAN_MEM  = int(cfg["voice_channel_ids"]["member_count"])
CHAN_FAM  = int(cfg["voice_channel_ids"]["online_in_family"])
CHAN_LEAD = int(cfg["voice_channel_ids"]["fam_leads_online"])

FAMILY_NAME = cfg["general"]["family_name"]
GUILD_ID    = int(cfg["general"].get("guild_id", 0))  # prefer explicit guild

CACHE_PATH = "data/server_stats_cache.json"


# ─────────────────────────────────────────────────────────────────────────────
# Cache helpers
# ─────────────────────────────────────────────────────────────────────────────
def load_cache() -> dict:
    if not os.path.exists(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, "r") as f:
            return json.load(f)
    except Exception as e:
        log.warning(f"Could not load cache: {e}")
        return {}

def save_cache(data: dict) -> None:
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(data, f)


# ─────────────────────────────────────────────────────────────────────────────
# Cog
# ─────────────────────────────────────────────────────────────────────────────
class ServerStats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # last-known values (used to avoid unnecessary PATCH calls)
        self._cache      = load_cache()
        self._last_total = self._cache.get("total")
        self._last_fam   = tuple(self._cache.get("fam",  (None, None)))
        self._last_lead  = tuple(self._cache.get("lead", (None, None)))

        # If cache missing keys, we "prime" on first loop (no edits)
        self._first_run = not all(k in self._cache for k in ("total", "fam", "lead"))

        self.update_loop.start()

    def cog_unload(self):
        self.update_loop.cancel()

    @tasks.loop(minutes=10)
    async def update_loop(self):
        """Every 10 minutes: compute counts and update channel names (if changed)."""
        if not ENABLE:
            return

        # Resolve guild robustly
        guild = self.bot.get_guild(GUILD_ID) or (self.bot.guilds[0] if self.bot.guilds else None)
        if not guild:
            log.warning("No guild available; skipping update.")
            return

        # Resolve channels safely
        ch_total = self.bot.get_channel(CHAN_MEM)
        ch_fam   = self.bot.get_channel(CHAN_FAM)
        ch_lead  = self.bot.get_channel(CHAN_LEAD)
        if not all((ch_total, ch_fam, ch_lead)):
            log.warning("One or more configured channel IDs not found; skipping update.")
            return

        # Count roles in a single pass over members (efficient on large guilds)
        fam_total = fam_online = lead_total = lead_online = 0
        for m in guild.members:
            # presence requires intents.presences=True; membership requires intents.members=True
            has_fam  = any(r.id == FAM_ID  for r in m.roles)
            has_lead = any(r.id == LEAD_ID for r in m.roles)

            if has_fam:
                fam_total += 1
                if m.status != discord.Status.offline:
                    fam_online += 1

            if has_lead:
                lead_total += 1
                if m.status != discord.Status.offline:
                    lead_online += 1

        total = guild.member_count

        # First run on a fresh environment: prime cache and exit (no edits)
        if self._first_run:
            self._last_total = total
            self._last_fam   = (fam_online, fam_total)
            self._last_lead  = (lead_online, lead_total)
            save_cache({"total": total, "fam": [fam_online, fam_total], "lead": [lead_online, lead_total]})
            self._first_run = False
            log.info("Primed server stats cache on first run; no API edits made.")
            return

        # Check changes and apply edits with spacing to avoid bursts
        updates_made = False

        if total != self._last_total:
            self._last_total = total
            await self._safe_rename(ch_total, f"Server Members: {total}")
            updates_made = True

        if (fam_online, fam_total) != self._last_fam:
            self._last_fam = (fam_online, fam_total)
            await self._safe_rename(ch_fam, f"Online Fam Members: {fam_online}/{fam_total}")
            updates_made = True

        if (lead_online, lead_total) != self._last_lead:
            self._last_lead = (lead_online, lead_total)
            await self._safe_rename(ch_lead, f"Online Fam Leads: {lead_online}/{lead_total}")
            updates_made = True

        if updates_made:
            save_cache({"total": self._last_total, "fam": list(self._last_fam), "lead": list(self._last_lead)})
            log.info(f"Updated {FAMILY_NAME}: total={total}, fam={fam_online}/{fam_total}, leads={lead_online}/{lead_total}")
        else:
            log.info("No changes detected; skipped API edits.")

    async def _safe_rename(self, channel: discord.abc.GuildChannel, new_name: str):
        """Rename channel with basic rate-limit spacing and error handling."""
        try:
            if getattr(channel, "name", None) != new_name:
                await asyncio.sleep(0.5)  # gentle spacing between PATCH calls
                await channel.edit(name=new_name)
                log.info(f"Renamed channel '{channel.name}' -> '{new_name}'")
        except discord.Forbidden:
            log.error(f"Missing permissions to edit channel '{getattr(channel, 'name', channel.id)}'")
        except discord.HTTPException as e:
            log.error(f"HTTP error while editing '{getattr(channel, 'name', channel.id)}': {e}")

    @update_loop.before_loop
    async def before_update_loop(self):
        await self.bot.wait_until_ready()
        log.info("ServerStats loop started.")

# ─────────────────────────────────────────────────────────────────────────────
# Extension setup (dev-friendly: remove if already loaded)
# ─────────────────────────────────────────────────────────────────────────────
async def setup(bot: commands.Bot):
    # If reloading during dev, remove the old cog instance to avoid
    # "Cog named 'ServerStats' already loaded".
    existing = bot.get_cog("ServerStats")
    if existing:
        bot.remove_cog("ServerStats")
    await bot.add_cog(ServerStats(bot))
