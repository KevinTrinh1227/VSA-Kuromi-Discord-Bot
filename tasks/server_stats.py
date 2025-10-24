# server_stats.py
import discord
from discord.ext import tasks, commands
import json
import os
import logging
import asyncio

# Logging setup
log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [server_stats] %(message)s")

# Load config
with open('config.json') as f:
    cfg = json.load(f)

ENABLE = bool(cfg["features"]["server_stats"]["enable_feature"])
FAM_ID = int(cfg["role_ids"]["family_member"])
LEAD_ID = int(cfg["role_ids"]["family_lead"])
CHAN_MEM = int(cfg["voice_channel_ids"]["member_count"])
CHAN_FAM = int(cfg["voice_channel_ids"]["online_in_family"])
CHAN_LEAD = int(cfg["voice_channel_ids"]["fam_leads_online"])
FAMILY_NAME = cfg["general"]["family_name"]
GUILD_ID = int(cfg["general"].get("guild_id", 0))  # optional fallback

CACHE_PATH = "data/server_stats_cache.json"


def load_cache():
    """Load last known stats from cache file."""
    if not os.path.exists(CACHE_PATH):
        return {}
    try:
        with open(CACHE_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(data):
    """Save current stats to cache file."""
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(data, f)


class ServerStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._cache = load_cache()
        self._last_total = self._cache.get("total")
        self._last_fam = tuple(self._cache.get("fam", (None, None)))
        self._last_lead = tuple(self._cache.get("lead", (None, None)))
        self.update_loop.start()

    def cog_unload(self):
        self.update_loop.cancel()

    @tasks.loop(minutes=10)
    async def update_loop(self):
        """Runs every 10 minutes to update member/family stats."""
        if not ENABLE:
            return

        guild = self.bot.get_guild(GUILD_ID) or (self.bot.guilds[0] if self.bot.guilds else None)
        if not guild:
            log.warning("No guild found; skipping update.")
            return

        # Get channels safely
        ch_total = self.bot.get_channel(CHAN_MEM)
        ch_fam = self.bot.get_channel(CHAN_FAM)
        ch_lead = self.bot.get_channel(CHAN_LEAD)
        if not all([ch_total, ch_fam, ch_lead]):
            log.warning("One or more target channels not found; skipping update.")
            return

        fam_total = fam_online = lead_total = lead_online = 0
        for m in guild.members:
            if any(r.id == FAM_ID for r in m.roles):
                fam_total += 1
                if m.status != discord.Status.offline:
                    fam_online += 1
            if any(r.id == LEAD_ID for r in m.roles):
                lead_total += 1
                if m.status != discord.Status.offline:
                    lead_online += 1

        total = guild.member_count

        # Check and update if changed
        updates_made = False

        if total != self._last_total:
            self._last_total = total
            await self.safe_edit(ch_total, f"Server Members: {total}")
            updates_made = True

        if (fam_online, fam_total) != self._last_fam:
            self._last_fam = (fam_online, fam_total)
            await self.safe_edit(ch_fam, f"Online Fam Members: {fam_online}/{fam_total}")
            updates_made = True

        if (lead_online, lead_total) != self._last_lead:
            self._last_lead = (lead_online, lead_total)
            await self.safe_edit(ch_lead, f"Online Fam Leads: {lead_online}/{lead_total}")
            updates_made = True

        # Cache results if any updates occurred
        if updates_made:
            save_cache({
                "total": self._last_total,
                "fam": list(self._last_fam),
                "lead": list(self._last_lead)
            })
            log.info(f"Updated server stats for {FAMILY_NAME}: total={total}, fam={fam_online}/{fam_total}, leads={lead_online}/{lead_total}")
        else:
            log.info("No changes detected; skipped API updates.")

    async def safe_edit(self, channel, new_name):
        """Edit channel name with built-in rate-limit protection."""
        try:
            if channel.name != new_name:
                await asyncio.sleep(0.5)  # small spacing between edits
                await channel.edit(name=new_name)
                log.info(f"Updated channel: {channel.name} -> {new_name}")
        except discord.Forbidden:
            log.error(f"Missing permissions to edit channel {channel.name}")
        except discord.HTTPException as e:
            log.error(f"Error editing {channel.name}: {e}")

    @update_loop.before_loop
    async def before_loop(self):
        await self.bot.wait_until_ready()
        log.info("ServerStats loop started.")

async def setup(bot):
    await bot.add_cog(ServerStats(bot))
