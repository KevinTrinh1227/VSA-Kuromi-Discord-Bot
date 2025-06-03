# commands/profile.py

import discord
from discord.ext import commands
import json
from dateutil import parser as date_parser
import datetime
from zoneinfo import ZoneInfo

# Path to the verified users JSON
VERIFIED_USER_FILE = "verified_user_data.json"

# Load config once at startup
with open('config.json') as json_file:
    config_data = json.load(json_file)

embed_color = int(config_data["general"]["embed_color"].strip("#"), 16)
family_name = config_data["general"].get("family_name", "N/A")
currency_name = config_data.get("features", {}).get("coin_level_system", {}).get("currency_name", "coins")
currency_label = currency_name.capitalize()


class ProfileCog(commands.Cog):
    def __init__(self, client):
        self.client = client
        # Load verified users data
        self.load_user_data()

    def load_user_data(self):
        try:
            with open(VERIFIED_USER_FILE, "r") as f:
                self.user_data = json.load(f)
        except FileNotFoundError:
            self.user_data = {}

    @commands.hybrid_command(
        name="profile",
        aliases=["prof", "user", "p"],
        brief="profile",
        description="View a user's profile",
        with_app_command=True
    )
    async def profile(self, ctx, member: discord.Member = None):
        if not ctx.guild:
            return  # must be in a guild

        member = member or ctx.author
        self.load_user_data()

        user_id = str(member.id)
        user_record = self.user_data.get(user_id)
        if not user_record:
            await ctx.send("❌ This user is not verified.")
            return

        general = user_record.get("general", {})
        stats = user_record.get("stats", {})

        # Name, first & last together
        first_name = general.get("first_name", "N/A")
        last_name = general.get("last_name", "")
        full_name = f"{first_name} {last_name}".strip()

        # Birthday formatting
        raw_birthday = general.get("birthday", "")
        formatted_bday = "Unknown"
        days_away = "?"
        today = datetime.datetime.now(ZoneInfo("America/Chicago")).date()
        try:
            # Try parsing "MM/DD/YYYY" first, otherwise "MMDDYYYY"
            try:
                bd_full = datetime.datetime.strptime(raw_birthday, "%m/%d/%Y").date()
            except ValueError:
                bd_full = datetime.datetime.strptime(raw_birthday, "%m%d%Y").date()
            formatted_bday = bd_full.strftime("%b %d, %Y")
            this_year_bday = bd_full.replace(year=today.year)
            if this_year_bday < today:
                next_bday = this_year_bday.replace(year=today.year + 1)
            else:
                next_bday = this_year_bday
            days_away = (next_bday - today).days
        except:
            pass

        # Account creation date (UTC → CST)
        created_at_utc = member.created_at
        created_cst = created_at_utc.replace(tzinfo=datetime.timezone.utc).astimezone(ZoneInfo("America/Chicago"))
        created_str = created_cst.strftime("%b %d, %Y %I:%M %p CST")

        # Member join date (UTC → CST)
        joined_at_utc = member.joined_at
        if joined_at_utc:
            joined_cst = joined_at_utc.replace(tzinfo=datetime.timezone.utc).astimezone(ZoneInfo("America/Chicago"))
            joined_str = joined_cst.strftime("%b %d, %Y %I:%M %p CST")
        else:
            joined_str = "Unknown"

        # Verified timestamp from JSON (assume stored in UTC)
        verified_ts = general.get("timestamp")
        try:
            ver_dt_utc = date_parser.parse(verified_ts).replace(tzinfo=datetime.timezone.utc)
            ver_dt_cst = ver_dt_utc.astimezone(ZoneInfo("America/Chicago"))
            verified_str = ver_dt_cst.strftime("%b %d, %Y %I:%M %p CST")
            delta = datetime.datetime.now(ZoneInfo("America/Chicago")) - ver_dt_cst
            days_since_verified = delta.days
        except:
            verified_str = "Unknown"
            days_since_verified = "?"

        # Roles (excluding @everyone)
        role_mentions = [r.mention for r in member.roles if r.id != ctx.guild.id]
        roles_list = " ".join(role_mentions) if role_mentions else "None"

        # Stats
        level = stats.get("level", 1)
        exp = stats.get("exp", 0)
        coins = stats.get("coins", 0)
        messages = stats.get("total_messages_sent", 0)
        wins = stats.get("coinflips_won", 0)
        losses = stats.get("coinflips_lost", 0)
        total_games = wins + losses
        win_rate = f"{wins}/{losses} ({(wins/total_games*100):.0f}%)" if total_games > 0 else "0/0 (0%)"

        # EXP progress bar functions
        def get_required_exp(lvl):
            if config_data.get("features", {}).get("coin_level_system", {}).get("non_linear_harder_level_up", False):
                return int(100 * (1.15 ** (lvl - 1)))
            return 100

        def build_progress_bar(exp_val, lvl):
            needed = get_required_exp(lvl)
            prog = min(exp_val / needed, 1.0)
            filled = int(prog * 10)
            empty = 10 - filled
            green_circle = chr(0x1F7E2)
            white_circle = chr(0x26AA)
            return f"**[**{green_circle * filled}{white_circle * empty}**]** ({int(prog * 100)}%)"

        needed_exp = get_required_exp(level)
        progress_bar = build_progress_bar(exp, level)
        remaining_exp = max(needed_exp - exp, 0)

        # Build a single description string with blank lines between sections
        description_parts = []

        # General Information section
        general_info_text = (
            f"• User: {member.mention} - `{member.id}`\n"
            f"• Name: `{full_name}`\n"
            f"• Birthday: `{formatted_bday} ({days_away} days away)`\n"
            f"• In {family_name} Fam: `{'Yes' if general.get('in_family') else 'No'}`"
        )
        description_parts.append("**General Information:**\n" + general_info_text)

        # EXP Progress section
        exp_info_text = (
            f"• Level: `{level}`\n"
            f"• Current EXP: `{exp:.2f}` / `{needed_exp}`\n"
            f"• EXP Remaining: `{remaining_exp:.2f}`\n"
            f"• {progress_bar}"
        )
        description_parts.append("**EXP Progress:**\n" + exp_info_text)

        # Currency & Stats section
        currency_info_text = (
            f"• {currency_label} Amount: `{coins}`\n"
            f"• Messages Sent: `{messages}`\n"
            f"• Coinflips W/L: `{win_rate}`\n\n"
            f"**Misc. Account Info:**\n"
            f"• Account Created: `{created_str}`\n"
            f"• User Joined: `{joined_str}`\n"
            f"• Verified On: `{verified_str} ({days_since_verified} days ago)`\n\n"
            f"**Current Roles:**\n{roles_list}\n"
        )
        description_parts.append("**Currency & Stats:**\n" + currency_info_text)

        # Join them with two newlines between sections
        final_description = "\n\n".join(description_parts)

        embed = discord.Embed(
            title=f"📊 | {member.display_name}'s Profile",
            description=final_description,
            color=embed_color
        )
        embed.timestamp = datetime.datetime.now(ZoneInfo("America/Chicago"))

        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)
        embed.set_footer(text=f"©️ {ctx.guild.name}", icon_url=ctx.guild.icon.url)

        await ctx.send(embed=embed)


async def setup(client):
    await client.add_cog(ProfileCog(client))
