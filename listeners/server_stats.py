# server_stats.py

import discord
from discord.ext import tasks, commands
import json

with open('config.json') as f:
    cfg = json.load(f)

ENABLE = bool(cfg["features"].get("server_stats", 0))
FAM_ID    = int(cfg["role_ids"]["family_member"])
LEAD_ID   = int(cfg["role_ids"]["family_lead"])
CHAN_MEM  = int(cfg["voice_channel_ids"]["member_count"])
CHAN_FAM  = int(cfg["voice_channel_ids"]["online_in_family"])
CHAN_LEAD = int(cfg["voice_channel_ids"]["fam_leads_online"])

_last_total = None
_last_fam   = (None, None)
_last_lead  = (None, None)


class serverstats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.update_loop.start()

    @tasks.loop(minutes=10)
    async def update_loop(self):
        if not ENABLE:
            return

        guild = self.bot.guilds[0]
        total = guild.member_count

        fam_members = [m for m in guild.members
                       if any(r.id == FAM_ID for r in m.roles)]
        fam_total  = len(fam_members)
        fam_online = sum(1 for m in fam_members
                         if m.status is not discord.Status.offline)

        lead_members = [m for m in guild.members
                        if any(r.id == LEAD_ID for r in m.roles)]
        lead_total  = len(lead_members)
        lead_online = sum(1 for m in lead_members
                          if m.status is not discord.Status.offline)

        ch_total = self.bot.get_channel(CHAN_MEM)
        ch_fam   = self.bot.get_channel(CHAN_FAM)
        ch_lead  = self.bot.get_channel(CHAN_LEAD)

        global _last_total, _last_fam, _last_lead

        if total != _last_total:
            _last_total = total
            await ch_total.edit(name=f"Server Members: {total}")

        if (fam_online, fam_total) != _last_fam:
            _last_fam = (fam_online, fam_total)
            await ch_fam.edit(name=f"Online Slytherines: {fam_online}/{fam_total}")

        if (lead_online, lead_total) != _last_lead:
            _last_lead = (lead_online, lead_total)
            await ch_lead.edit(name=f"Online Fam Leads: {lead_online}/{lead_total}")

    @update_loop.before_loop
    async def before(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(serverstats(bot))
