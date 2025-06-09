import discord
from discord.ext import commands, tasks
import json
import asyncio
import os
from datetime import datetime

from utils.nickname_and_roles import rename_user, assign_roles
from utils.users_utils import get_verified_users, save_verified_users

CONFIG_FILE = "config.json"

class VerifiedUserDataUpdater(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = None
        self.update_task = None
        self.load_config()

        if self.config and self.config.get("features", {}).get("verified_user_data_updater", {}).get("enable_feature", False):
            interval = self.config["features"]["verified_user_data_updater"].get("update_time_intervals_seconds", 300)
            self.update_task = tasks.loop(seconds=interval)(self.update_verified_users)
            self.update_task.start()

    def cog_unload(self):
        if self.update_task:
            self.update_task.cancel()

    def load_config(self):
        if not os.path.isfile(CONFIG_FILE):
            print(f"[ERROR] Config file '{CONFIG_FILE}' not found.")
            self.config = None
            return

        try:
            with open(CONFIG_FILE, "r") as f:
                self.config = json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load config: {e}")
            self.config = None

    async def update_verified_users(self):
        self.load_config()
        if not self.config:
            return

        feature_cfg = self.config.get("features", {}).get("verified_user_data_updater", {})
        if not feature_cfg.get("enable_feature", False):
            return

        guild_id = self.config.get("general", {}).get("discord_server_guild_id")
        if not guild_id:
            print("[ERROR] No guild ID found in config.")
            return

        guild = self.bot.get_guild(int(guild_id))
        if not guild:
            print(f"[ERROR] Guild {guild_id} not found.")
            return

        # Use helper to load only verified users
        verified_data = get_verified_users()
        now_iso = datetime.utcnow().isoformat()
        updated = False

        for user_id_str, user_info in verified_data.items():
            try:
                user_id = int(user_id_str)
            except ValueError:
                continue

            member = guild.get_member(user_id)
            still_in_server = member is not None
            discord_profile = user_info.get("discord_profile", {})

            if still_in_server:
                # Rename the user using helper
                await rename_user(member)

                # Assign roles if restoring is enabled
                restore_roles = feature_cfg.get("restore_roles_on_rejoin", True)
                if restore_roles:
                    role_ids = discord_profile.get("roles", [])
                    await assign_roles(user_id, role_ids, guild)

                # Update info
                discord_profile.update({
                    "nickname": member.nick or member.name,
                    "roles": [str(role.id) for role in member.roles if role.id != guild.id],
                    "first_time_joined": member.joined_at.isoformat() if member.joined_at else None,
                    "last_updated": now_iso,
                    "still_in_server": True
                })
            else:
                discord_profile.update({
                    "still_in_server": False,
                    "last_updated": now_iso
                })

            user_info["discord_profile"] = discord_profile
            verified_data[user_id_str] = user_info
            updated = True

        if updated:
            try:
                save_verified_users(verified_data)
                #print("[INFO] Verified user data updated and saved.")
            except Exception as e:
                print(f"[ERROR] Could not save verified user data: {e}")

async def setup(bot):
    await bot.add_cog(VerifiedUserDataUpdater(bot))
