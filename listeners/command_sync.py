# cogs/listeners/command_sync.py

import os
from dotenv import load_dotenv
import discord
from discord.ext import commands

# ─── Load .env ─────────────────────────────────────────────────────
load_dotenv()  # reads .env from your project root

class CommandSyncCog(commands.Cog):
    """Automatically syncs all application (slash) commands on startup."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._did_sync = False
        # read your target guild ID from DISCORD_SERVER_GUILD_ID in .env
        try:
            self._guild_id = int(os.environ["DISCORD_SERVER_GUILD_ID"])
        except (KeyError, ValueError):
            self._guild_id = None

    @commands.Cog.listener()
    async def on_ready(self):
        # only run once per process
        if self._did_sync:
            return
        self._did_sync = True

        # 1) Global sync (propagates within ~1h)
        try:
            synced = await self.bot.tree.sync()
            print(f"| 🌐 Synced {len(synced)} global commands.")
        except Exception as e:
            print(f"[Sync] ⚠️  Global sync failed:", e)

        # 2) Guild-level sync (instant)
        if self._guild_id:
            try:
                guild_obj = discord.Object(id=self._guild_id)
                synced_g = await self.bot.tree.sync(guild=guild_obj)
                print(f"[Sync] ✅ Synced {len(synced_g)} commands to guild ID {self._guild_id}.")
            except Exception as e:
                print(f"[Sync] ❌ Guild sync failed for {self._guild_id}:", e)
        else:
            print("[Sync] ⚠️  DISCORD_SERVER_GUILD_ID not set or invalid in .env; skipping guild-level sync.")

async def setup(bot: commands.Bot):
    await bot.add_cog(CommandSyncCog(bot))