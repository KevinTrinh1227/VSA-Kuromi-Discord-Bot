# commands/bot_status.py
import discord
from discord.ext import commands, tasks
import json, asyncio, random, os

CONFIG_PATH = "config.json"

# Load configuration
with open(CONFIG_PATH, "r") as f:
    cfg = json.load(f)

# General config
GENERAL_CFG = cfg["general"]
FAMILY_NAME = GENERAL_CFG.get("family_name", "Project (K)uromi")
FAMILY_KIDS_NAME = GENERAL_CFG.get("family_kids_name_singular", "Kuromi")
FAMILY_MEMBER_ROLE_ID = int(GENERAL_CFG.get("family_member_role_id", 0))

# Feature config
BOT_STATUS_FEATURE = cfg.get("features", {}).get("bot_status", {})
FEATURE_ENABLED = BOT_STATUS_FEATURE.get("enable_feature", False)
STATUS_LIST = BOT_STATUS_FEATURE.get("statuses", [])
INTERVAL = BOT_STATUS_FEATURE.get("interval_minutes", 10) * 60  # convert minutes to seconds

# Safety constants
BACKOFF_TIME = 300  # 5 minutes if rate-limited


class BotStatus(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.index = 0
        if FEATURE_ENABLED and not self.cycle_status.is_running():
            self.cycle_status.start()

    @tasks.loop(seconds=INTERVAL)
    async def cycle_status(self):
        await asyncio.sleep(random.randint(0, 10))  # jitter

        guild = self.bot.guilds[0] if self.bot.guilds else None
        if not guild or not STATUS_LIST:
            return

        # Gather dynamic stats
        # Gather dynamic stats
        total_server_members = guild.member_count

        # Get role objects from guild based on IDs from config
        role_ids_cfg = cfg.get("role_ids", {})
        family_member_role = guild.get_role(int(role_ids_cfg.get("family_member", 0)))
        family_pseudo_role = guild.get_role(int(role_ids_cfg.get("family_pseudo_member", 0)))

        # Total members with any "family" roles (member + pseudo)
        total_family_members_with_pseudos = 0
        if family_member_role or family_pseudo_role:
            for m in guild.members:
                if (family_member_role and family_member_role in m.roles) or (family_pseudo_role and family_pseudo_role in m.roles):
                    total_family_members_with_pseudos += 1

        # Total members with only "family_member" role (exclude pseudo)
        total_family_members_no_pseudos = len(family_member_role.members) if family_member_role else 0


        # Get current status config
        status_cfg = STATUS_LIST[self.index % len(STATUS_LIST)]
        status_type = status_cfg.get("status", "online")
        activity_type = status_cfg.get("activity_type", "playing").lower()
        status_text = status_cfg.get("text", "").format(
            total_family_members_with_pseudos=total_family_members_with_pseudos,
            total_family_members_no_pseudos=total_family_members_no_pseudos,
            total_server_members_count=total_server_members,
            family_name=FAMILY_NAME,
            family_kids_name_singular=FAMILY_KIDS_NAME
        )

        # Map status and activity types
        status_enum = getattr(discord.Status, status_type.lower(), discord.Status.online)
        activity_enum_map = {
            "watching": discord.ActivityType.watching,
            "playing": discord.ActivityType.playing,
            "listening": discord.ActivityType.listening,
            "streaming": discord.ActivityType.streaming
        }
        activity_enum = activity_enum_map.get(activity_type, discord.ActivityType.playing)

        try:
            await self.bot.change_presence(
                status=status_enum,
                activity=discord.Activity(type=activity_enum, name=status_text)
            )
            await asyncio.sleep(2)  # short sleep to avoid back-to-back updates
            self.index += 1

        except discord.HTTPException as e:
            print(f"[BotStatus] Rate limit hit, backing off for {BACKOFF_TIME} seconds. Error: {e}")
            await asyncio.sleep(BACKOFF_TIME)

    @cycle_status.error
    async def cycle_status_error(self, error):
        print(f"[BotStatus] Task error: {error}")


async def setup(bot):
    await bot.add_cog(BotStatus(bot))
