# commands/bot_status.py

import discord
from discord.ext import commands, tasks
import json

# Load configuration
with open('config.json') as json_file:
    cfg = json.load(json_file)

COMMAND_PREFIX = cfg['general']['bot_prefix']
FAMILY_ROLE_ID = int(cfg['role_ids']['family_member'])

# index for cycling statuses
i = 0

class BotStatus(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.cycle_status.start()

    @tasks.loop(seconds=120)
    async def cycle_status(self):
        global i
        guild = self.client.guilds[0]
        # count members with family role
        family_role = guild.get_role(FAMILY_ROLE_ID)
        if family_role:
            family_count = sum(1 for m in guild.members if family_role in m.roles)
        else:
            family_count = 'NA'

        if i == 0:
            # watching over X Slytherins 🐍
            await self.client.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.watching,
                    name=f"over {family_count} Slytherins 🐍"
                )
            )
        elif i == 1:
            # playing Bầu cua 🦀
            await self.client.change_presence(
                activity=discord.Game(name="Bầu cua 🦀")
            )
        else:
            # listening to command: /help 🔎
            await self.client.change_presence(
                activity=discord.Activity(
                    type=discord.ActivityType.listening,
                    name="/help 🔎"
                )
            )

        i = (i + 1) % 3

async def setup(client):
    await client.add_cog(BotStatus(client))