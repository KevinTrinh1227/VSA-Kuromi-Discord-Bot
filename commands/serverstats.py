import discord
from discord.ext import commands
import json

# Load configuration
CONFIG_PATH = 'config.json'

# Load config.json
with open(CONFIG_PATH) as f:
    cfg = json.load(f)

class ServerStats(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="serverstats", description="Shows real-time server statistics.")
    async def serverstats(self, ctx: commands.Context):
        guild = ctx.guild
        members = guild.members
        bots = [m for m in members if m.bot]
        humans = [m for m in members if not m.bot]

        # Member status
        online = sum(1 for m in members if m.status == discord.Status.online)
        idle = sum(1 for m in members if m.status == discord.Status.idle)
        dnd = sum(1 for m in members if m.status == discord.Status.dnd)
        offline = sum(1 for m in members if m.status == discord.Status.offline)

        # Roles
        role_counts = sorted(guild.roles[1:], key=lambda r: len(r.members), reverse=True)
        most_used_role = role_counts[0] if role_counts else None

        # Channels
        text_channels = len(guild.text_channels)
        voice_channels = len(guild.voice_channels)

        # Boosts and media
        boost_level = guild.premium_tier
        boost_count = guild.premium_subscription_count
        created_at = discord.utils.format_dt(guild.created_at, style="F")

        # Embed
        embed = discord.Embed(
            title=f"📊 | {guild.name} Server Stats",
            color=int(cfg['general']['embed_color'].strip('#'), 16)
        )

        embed.set_thumbnail(url=guild.icon.url if guild.icon else discord.Embed.Empty)
        if guild.banner:
            embed.set_image(url=guild.banner.url)

        embed.description = (
            f"**🪪 General Info**\n"
            f"• Server ID: `{guild.id}`\n"
            f"• Owner: {guild.owner.mention}`\n"
            f"• Created: {created_at}\n\n"

            f"**👥 Members**\n"
            f"• Total Members: `{guild.member_count}`\n"
            f"• Humans: `{len(humans)}`\n"
            f"• Bots: `{len(bots)}`\n"
            f"• Online: `{online}` | Idle: `{idle}` | DND: `{dnd}` | Offline: `{offline}`\n"
            f"• % Online: `{(online / guild.member_count) * 100:.1f}%`\n\n"

            f"**🏷️ Roles & Channels**\n"
            f"• Total Roles: `{len(guild.roles)}`\n"
            f"• Most Used Role: `{most_used_role.name}` ({len(most_used_role.members)} members)\n"
            f"• Text Channels: `{text_channels}`\n"
            f"• Voice Channels: `{voice_channels}`\n"
            f"• AFK Channel: `{guild.afk_channel.name if guild.afk_channel else 'None'}`\n\n"

            f"**✨ Boosts & Media**\n"
            f"• Boost Level: `{boost_level}`\n"
            f"• Boosts: `{boost_count}`\n"
            f"• Vanity URL: `{guild.vanity_url_code or 'None'}`\n"
        )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(ServerStats(bot))
