import discord
from discord.ext import commands
from discord import app_commands
import json
from datetime import datetime
from dateutil import parser as date_parser

with open('config.json') as json_file:
    config_data = json.load(json_file)

embed_color = int(config_data["general"]["embed_color"].strip("#"), 16)
nick_template = config_data.get("nickname_templates", {})
nick_before = nick_template.get("format_before_seperator", "")
nick_separator = nick_template.get("seperator_symbol", "|")
nick_after = nick_template.get("format_after_seperator", "{first_name} {last_name}")
currency_name = config_data.get("features", {}).get("coin_level_system", {}).get("currency_name", "coins")
currency_label = currency_name.capitalize()
VERIFIED_USER_FILE = "verified_user_data.json"

class LeaderboardsCog(commands.Cog):
    def __init__(self, client):
        self.client = client
        try:
            with open(VERIFIED_USER_FILE, "r") as f:
                self.user_data = json.load(f)
        except FileNotFoundError:
            self.user_data = {}

    def build_name(self, uid, data, guild):
        member = guild.get_member(int(uid))
        if member:
            return f"<@{member.id}>"

        general = data.get("general", {})
        stats = data.get("stats", {})
        lvl = stats.get("level", 0)
        first = general.get("first_name", "?")
        last = general.get("last_name", "?")

        formatted_before = nick_before.replace("{level}", str(lvl)) if "{level}" in nick_before else nick_before
        formatted_after = nick_after.replace("{first_name}", first).replace("{last_name}", last)
        return f"@{formatted_before}{nick_separator}{formatted_after}"

    @commands.hybrid_command(
        name="leaderboards",
        aliases=["lb", "top"],
        brief="leaderboards",
        description="View top EXP, coin holders, or coinflip wins",
        with_app_command=True
    )
    @app_commands.describe(type="The type of leaderboard to view (exp, coins, coinflips)")
    async def leaderboards(self, ctx, type: str):
        self.__init__(self.client)  # reload user_data
        type = type.lower()

        if type == "exp":
            key = lambda x: x[1].get("stats", {}).get("level", 0)
            title = "Top EXP Server Members"
            value_fn = lambda stats: f"Total EXP: {int(stats.get('level', 0)) * 100 + int(stats.get('exp', 0))} (Lvl. {stats.get('level', 0)})"
        elif type == "coins":
            key = lambda x: x[1].get("stats", {}).get("coins", 0)
            title = f"Top {currency_label} Holders"
            value_fn = lambda stats: f"{currency_label}: {stats.get('coins', 0)}"
        elif type == "coinflips":
            key = lambda x: x[1].get("stats", {}).get("coinflips_won", 0)
            title = "Top Coinflip Winners"
            value_fn = lambda stats: f"Wins: {stats.get('coinflips_won', 0)}"
        else:
            await ctx.send("❌ Invalid leaderboard type. Choose from 'exp', 'coins', or 'coinflips'.")
            return

        sorted_users = sorted(self.user_data.items(), key=key, reverse=True)
        top_ten = sorted_users[:10]
        others_count = len(sorted_users) - 10

        description_lines = []
        for idx, (uid, data) in enumerate(top_ten, 1):
            stats = data.get("stats", {})
            name = self.build_name(uid, data, ctx.guild)
            description_lines.append(f"**{idx}.** {name} - {value_fn(stats)}\n")

        if others_count > 0:
            description_lines.append(f"... ({others_count} more users not shown)")

        embed = discord.Embed(
            title=f"**\U0001F3C6 | {title}**",
            description="\n".join(description_lines),
            color=embed_color
        )
        embed.set_footer(text=f"Requested by {ctx.author} • {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}", icon_url=ctx.author.avatar.url)
        await ctx.send(embed=embed)

async def setup(client):
    await client.add_cog(LeaderboardsCog(client))
