import discord
from discord.ext import commands
import json
import random
import time
import datetime
from dateutil import parser as date_parser

# Load config once at startup
with open('config.json') as json_file:
    config_data = json.load(json_file)

embed_color = int(config_data["general"]["embed_color"].strip("#"), 16)
command_prefix = config_data["general"]["bot_prefix"]
nickname_template = config_data.get("nickname_templates", {})
nick_before = nickname_template.get("format_before_seperator", "")
nick_separator = nickname_template.get("seperator_symbol", "|")
family_name = config_data["general"].get("family_name", "N/A")

currency_name = config_data.get("features", {}).get("coin_level_system", {}).get("currency_name", "coins")
currency_label = currency_name.capitalize()

VERIFIED_USER_FILE = "verified_user_data.json"

# Feature flags
coin_level_config = config_data.get("features", {}).get("coin_level_system", {})
coin_level_system_enabled = coin_level_config.get("enable_feature", False)
non_linear_leveling = coin_level_config.get("non_linear_harder_level_up", False)
blacklisted_channel_ids = set(coin_level_config.get("blacklisted_channels_id", []))

log_channel_id = int(config_data.get("text_channel_ids", {}).get("bot_logs", 0))

class LevelingCog(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.load_user_data()
        self.message_cooldown = {}
        self.spam_tracker = {}
        self.coin_level_system_enabled = coin_level_system_enabled

    def load_user_data(self):
        try:
            with open(VERIFIED_USER_FILE, "r") as f:
                self.user_data = json.load(f)
        except FileNotFoundError:
            self.user_data = {}

    def save_user_data(self):
        with open(VERIFIED_USER_FILE, "w") as f:
            json.dump(self.user_data, f, indent=2)

    def build_progress_bar(self, exp, level):
        needed_exp = self.get_required_exp(level)
        progress = min(exp / needed_exp, 1.0)
        filled = int(progress * 10)
        empty = 10 - filled
        green_circle = chr(0x1F7E2)
        white_circle = chr(0x26AA)
        return f"[{green_circle * filled}{white_circle * empty}] ({int(progress * 100)}%)"

    def get_required_exp(self, level):
        if non_linear_leveling:
            return int(100 * (1.15 ** (level - 1)))
        return 100

    async def update_nickname(self, member: discord.Member, level: int):
        # Load the nickname format settings
        fmt_before = config_data["nickname_templates"]["format_before_seperator"]
        separator = config_data["nickname_templates"]["seperator_symbol"]
        fmt_after = config_data["nickname_templates"].get("format_after_seperator", "{first_name} {last_name}")

        # Fetch first/last name from stored user_data (falls back to member.name if missing)
        user_id_str = str(member.id)
        general_info = self.user_data.get(user_id_str, {}).get("general", {})
        first_name = general_info.get("first_name", member.name)
        last_name = general_info.get("last_name", "")

        # Build desired before_part and after_part
        before_part = fmt_before.replace("{level}", str(level))
        after_part = fmt_after.replace("{first_name}", first_name).replace("{last_name}", last_name)

        # Assemble full desired nickname
        desired_nick = f"{before_part}{separator}{after_part}".strip()
        if len(desired_nick) > 32:
            desired_nick = desired_nick[:32]

        # Determine current visible name (nick or username)
        current_nick = member.nick or member.name

        # Only update if it doesn't already match
        if current_nick == desired_nick:
            return

        try:
            await member.edit(nick=desired_nick)
        except discord.Forbidden:
            pass

    @commands.Cog.listener()
    async def on_message(self, message):
        if (not self.coin_level_system_enabled
            or message.author.bot
            or message.content.startswith(command_prefix)
            or "ticket" in message.channel.name.lower()
            or str(message.channel.id) in blacklisted_channel_ids):
            return

        self.load_user_data()
        user_id = str(message.author.id)
        if user_id not in self.user_data:
            return

        user_record = self.user_data[user_id]
        stats = user_record.setdefault("stats", {})

        # ── Nickname check: compare current nick vs. desired format ──
        # Load first/last name from stored verification data
        general_info = user_record.get("general", {})
        first_name = general_info.get("first_name", message.author.name)
        last_name = general_info.get("last_name", "")

        level = stats.get("level", 0)  # assume default level=0 if not set
        fmt_before = config_data["nickname_templates"]["format_before_seperator"]
        separator = config_data["nickname_templates"]["seperator_symbol"]
        fmt_after = config_data["nickname_templates"].get("format_after_seperator", "{first_name} {last_name}")

        # Build exactly what their nickname should be right now
        desired_before = fmt_before.replace("{level}", str(level))
        desired_after = fmt_after.replace("{first_name}", first_name).replace("{last_name}", last_name)
        desired_nick = f"{desired_before}{separator}{desired_after}".strip()
        if len(desired_nick) > 32:
            desired_nick = desired_nick[:32]

        current_nick = message.author.nick or message.author.name
        if current_nick != desired_nick:
            # Only call update_nickname if it doesn't match
            await self.update_nickname(message.author, level)

        # ── Spam tracking, XP gain, and leveling logic follow ──
        now = time.time()

        # Spam tracking
        timestamps = self.spam_tracker.get(user_id, [])
        timestamps = [ts for ts in timestamps if now - ts < 10]
        timestamps.append(now)
        self.spam_tracker[user_id] = timestamps

        if len(timestamps) > 5:
            log_channel = self.client.get_channel(log_channel_id)
            if log_channel:
                embed = discord.Embed(
                    title=f"⚠️ Anti-Spam Triggered",
                    description=(f"User {message.author.mention} has triggered anti-spam protection.\n"
                                 f"Messages in last 10s: {len(timestamps)}"),
                    color=discord.Color.red()
                )
                embed.set_footer(text=f"User ID: {user_id}")
                embed.timestamp = datetime.datetime.now()
                await log_channel.send(embed=embed)
            return

        stats["exp"] = stats.get("exp", 0)
        stats["coins"] = stats.get("coins", 0)
        stats["level"] = stats.get("level", 0)
        stats["total_messages_sent"] = stats.get("total_messages_sent", 0)
        stats["coinflips_won"] = stats.get("coinflips_won", 0)
        stats["coinflips_lost"] = stats.get("coinflips_lost", 0)

        stats["total_messages_sent"] += 1

        last_timestamp = self.message_cooldown.get(user_id, 0)
        if now - last_timestamp < 5:
            return
        self.message_cooldown[user_id] = now

        stats["exp"] += random.randint(1, 5) + 0.25
        stats["coins"] += random.randint(1, 5)

        needed_exp = self.get_required_exp(stats["level"])
        if stats["exp"] >= needed_exp:
            stats["level"] += 1
            stats["exp"] = 0
            await message.channel.send(f"🎉 {message.author.mention} leveled up to **Level {stats['level']}**!")
            await self.update_nickname(message.author, stats["level"])

        user_record["stats"] = stats
        self.user_data[user_id] = user_record
        self.save_user_data()


    @commands.hybrid_command(name="profile", aliases=["prof", "user", "p"], brief="profile", description="View a certain user's profile", with_app_command=True)
    async def profile(self, ctx, member: discord.Member = None):
        if not self.coin_level_system_enabled:
            await ctx.send("The coin and level system is disabled.")
            return

        member = member or ctx.author
        self.load_user_data()

        user_id = str(member.id)
        user_data = self.user_data.get(user_id)

        if not user_data:
            await ctx.send("❌ This user is not verified.")
            return

        general = user_data.get("general", {})
        stats = user_data.get("stats", {})

        level = stats.get("level", 1)
        exp = stats.get("exp", 0)
        coins = stats.get("coins", 0)
        messages = stats.get("total_messages_sent", 0)
        wins = stats.get("coinflips_won", 0)
        losses = stats.get("coinflips_lost", 0)
        total_games = wins + losses
        win_rate = f"{wins}/{losses} ({(wins/total_games*100):.0f}%)" if total_games > 0 else "0/0 (0%)"

        needed_exp = self.get_required_exp(level)
        progress_bar = self.build_progress_bar(exp, level)
        remaining_exp = max(needed_exp - exp, 0)

        timestamp_str = general.get("timestamp")
        days_in_server = 1
        if timestamp_str:
            try:
                joined_at = date_parser.parse(timestamp_str)
                days_in_server = max((datetime.datetime.utcnow() - joined_at).days, 1)
            except:
                pass

        avg_msgs = messages // days_in_server

        raw_birthday = general.get("birthday", "")
        formatted_bday = "Unknown"
        days_away = "?"
        today = datetime.date.today()
        try:
            # Try parsing "MM/DD/YYYY" first, otherwise "MMDDYYYY"
            try:
                bd_full = datetime.datetime.strptime(raw_birthday, "%m/%d/%Y").date()
            except ValueError:
                bd_full = datetime.datetime.strptime(raw_birthday, "%m%d%Y").date()
            formatted_bday = bd_full.strftime("%b %d, %Y")
            # Calculate next occurrence of birthday
            this_year_bday = bd_full.replace(year=today.year)
            if this_year_bday < today:
                next_bday = this_year_bday.replace(year=today.year + 1)
            else:
                next_bday = this_year_bday
            days_away = (next_bday - today).days
        except:
            pass

        in_family = "Yes" if general.get("in_family") else "No"

        embed = discord.Embed(
            title=f"📊 | {member.display_name}'s Profile",
            description=(
                f"Now displaying {member.mention}'s profile.\n"
                f"Use `/leaderboards <category>` to view a certain leaderboard.\n\n"
                f"**General Information**\n"
                f"• First name: {general.get('first_name', 'N/A')}\n"
                f"• Last name: {general.get('last_name', 'N/A')}\n"
                f"• Birthday: {formatted_bday} ({days_away} days away)\n"
                f"• In {family_name} Fam: {in_family}\n\n"
                f"**EXP Progress:**\n"
                f"• Current EXP: {exp:.2f} / {needed_exp}\n"
                f"• EXP remaining (Lvl. {level} ➜ Lvl. {level + 1}): {remaining_exp:.2f}\n"
                f"• {progress_bar}\n\n"
                f"**Currency Stats**\n"
                f"{currency_label} amount: {coins} {currency_name}\n"
                f"Coinflips WLR: {win_rate}"
            ),
            color=embed_color
        )
        embed.timestamp = datetime.datetime.now()
        embed.add_field(name='Messages Sent', value=f"{messages}", inline=True)
        embed.add_field(name='Messages/day', value=f"{avg_msgs}", inline=True)
        embed.add_field(name='Days Since Verified', value=f"{days_in_server}", inline=True)

        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)
        embed.set_footer(text=f"©️ {ctx.guild.name}", icon_url=ctx.guild.icon.url)

        await ctx.send(embed=embed)


async def setup(client):
    await client.add_cog(LevelingCog(client))
