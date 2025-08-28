import discord
from discord.ext import commands, tasks
import json
from datetime import datetime, time
import pytz
from utils.users_utils import get_verified_users, save_verified_users
import os
from dotenv import load_dotenv

load_dotenv()


with open("config.json") as f:
    config = json.load(f)

GUILD_ID = int(os.getenv("DISCORD_SERVER_GUILD_ID"))
FAMILY_ROLE_ID = int(config["role_ids"]["family_member"])
FAM_BDAY_CHANNEL_ID = int(config["features"]["birthdays"]["fam_birthdays_announce_channel"])
GEN_BDAY_CHANNEL_ID = int(config["features"]["birthdays"]["general_birthdays_announce_channel"])
REMINDER_CHANNEL_ID = int(config["text_channel_ids"].get("birthdays_reminder", "0"))
EMBED_COLOR = int(config["general"]["embed_color"].strip("#"), 16)
CST = pytz.timezone("America/Chicago")


def format_birthday_date(mmdd_str):
    month_num, day_num = map(int, mmdd_str.split("/"))
    month_name = datetime(2000, month_num, 1).strftime("%B")
    def suffix(d):
        return 'th' if 11 <= d <= 13 else {1: 'st', 2: 'nd', 3: 'rd'}.get(d % 10, 'th')
    return f"{month_name} {day_num}{suffix(day_num)}"


class BirthdayListener(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.announced_today = set()
        self.testing_mode = False  # <-- Set True to test every minute, False for daily at midnight CST
        if self.testing_mode:
            self.daily_birthday_check_test.start()
        else:
            self.daily_birthday_check.start()
        self.monthly_reminder_check.start()

    def cog_unload(self):
        self.daily_birthday_check.cancel()
        self.daily_birthday_check_test.cancel()
        self.monthly_reminder_check.cancel()


    @staticmethod
    def is_valid_birthday(bday_str):
        try:
            parts = bday_str.split("/")
            if len(parts) < 2:
                return False
            month = int(parts[0])
            day = int(parts[1])
            return 1 <= month <= 12 and 1 <= day <= 31
        except Exception:
            return False

    def get_today_mmdd(self):
        return datetime.now(CST).strftime("%m/%d")

    def get_current_month(self):
        return datetime.now(CST).month

    async def fetch_guild(self):
        return self.bot.get_guild(GUILD_ID) or await self.bot.fetch_guild(GUILD_ID)

    async def send_family_embed(self, channel, birthday_users):
        for member, bday in birthday_users:
            user_info = get_verified_users().get(str(member.id), {}).get("general", {})
            first = user_info.get("first_name", "First")
            last = user_info.get("last_name", "Last")
            bday_formatted = format_birthday_date(bday[:5])
            embed = discord.Embed(
                title=f"🎉 | Happy Birthday {first} {last}!",
                description=(
                    f"Happy birthday {member.mention}! On behalf of our family, we wish the best!"
                    f"Have an amazing day and stay safe!\n\n🎂 Birthday: {bday_formatted}"
                ),
                color=EMBED_COLOR
            )
            if member.avatar:
                embed.set_thumbnail(url=member.avatar.url)

            mention_msg = await channel.send(f"||{member.mention}||")
            if mention_msg.content == f"||{member.mention}||":
                await mention_msg.delete()
            msg = await channel.send(embed=embed)
            for emoji in ("🎀", "🎉", "❤️", "🎂", "🥳", "🎁", "🫶"):
                await msg.add_reaction(emoji)

    # --- DAILY BIRTHDAY CHECK TASK ---
    # Normal operation: runs once daily at midnight CST
    @tasks.loop(time=time(0, 0, tzinfo=CST))
    #@tasks.loop(minutes=1)
    async def daily_birthday_check(self):
        #print(f"[Birthday Check] Running daily_birthday_check at {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')}")
        self.announced_today.clear()
        today = self.get_today_mmdd()
        guild = await self.fetch_guild()
        if guild is None:
            return

        user_data = get_verified_users()
        fam_birthdays = []
        gen_birthdays = []

        for uid, data in user_data.items():
            general = data.get("general", {})
            birthday = general.get("birthday")
            if not birthday or not self.is_valid_birthday(birthday) or birthday[:5] != today:
                continue
            member = guild.get_member(int(uid))
            if not member or member.id in self.announced_today:
                continue

            if hasattr(member, "roles") and any(role.id == FAMILY_ROLE_ID for role in member.roles):
                fam_birthdays.append((member, birthday))
            else:
                gen_birthdays.append((member, birthday))

        fam_channel = gen_channel = None

        if fam_birthdays or gen_birthdays:
            fam_channel = guild.get_channel(FAM_BDAY_CHANNEL_ID)
            gen_channel = guild.get_channel(GEN_BDAY_CHANNEL_ID)

        if fam_channel and fam_birthdays:
            await self.send_family_embed(fam_channel, fam_birthdays)

        if gen_channel:
            for member, birthday in fam_birthdays:
                msg = await gen_channel.send(
                    f"**🎀 Happy birthday to our family member {member.mention}! 🎀** (<#{FAM_BDAY_CHANNEL_ID}>)"
                )
                for emoji in ("❤️", "🎉", "🥳"):
                    await msg.add_reaction(emoji)

            for member, _ in gen_birthdays:
                msg = await gen_channel.send(
                    f"🎉 Happy birthday {member.mention}! Have an amazing day today!"
                )
                for emoji in ("❤️", "🎉"):
                    await msg.add_reaction(emoji)

        self.announced_today.update(m.id for m, _ in fam_birthdays + gen_birthdays)

    # --- TESTING MODE: RUNS EVERY 1 MINUTE ---
    @tasks.loop(minutes=1)
    async def daily_birthday_check_test(self):
        #print(f"[Birthday Check] Running TEST daily_birthday_check at {datetime.now(CST).strftime('%Y-%m-%d %H:%M:%S')}")
        self.announced_today.clear()
        today = self.get_today_mmdd()
        guild = await self.fetch_guild()
        if guild is None:
            return

        user_data = get_verified_users()
        fam_birthdays = []
        gen_birthdays = []

        for uid, data in user_data.items():
            general = data.get("general", {})
            birthday = general.get("birthday")
            if not birthday or not self.is_valid_birthday(birthday) or birthday[:5] != today:
                continue
            member = guild.get_member(int(uid))
            if not member or member.id in self.announced_today:
                continue

            if hasattr(member, "roles") and any(role.id == FAMILY_ROLE_ID for role in member.roles):
                fam_birthdays.append((member, birthday))
            else:
                gen_birthdays.append((member, birthday))

        fam_channel = gen_channel = None
        #print(fam_birthdays)

        if fam_birthdays or gen_birthdays:
            fam_channel = guild.get_channel(FAM_BDAY_CHANNEL_ID)
            gen_channel = guild.get_channel(GEN_BDAY_CHANNEL_ID)

        if fam_channel and fam_birthdays:
            await self.send_family_embed(fam_channel, fam_birthdays)

        if gen_channel:
            for member, birthday in fam_birthdays:
                msg = await gen_channel.send(
                    f"**🎀 Happy birthday to our family member {member.mention}! 🎀** (<#{FAM_BDAY_CHANNEL_ID}>)"
                )
                for emoji in ("❤️", "🎉", "🥳"):
                    await msg.add_reaction(emoji)

            for member, _ in gen_birthdays:
                msg = await gen_channel.send(
                    f"🎉 Happy birthday {member.mention}! Have an amazing day today!"
                )
                for emoji in ("❤️", "🎉"):
                    await msg.add_reaction(emoji)

        self.announced_today.update(m.id for m, _ in fam_birthdays + gen_birthdays)

    @tasks.loop(hours=24)
    async def monthly_reminder_check(self):
        now = datetime.now(CST)
        if now.day != 1 or now.hour != 0:
            return

        guild = await self.fetch_guild()
        if guild is None:
            return

        user_data = get_verified_users()
        current_month = self.get_current_month()

        fam_members = []
        gen_members = []

        for uid, data in user_data.items():
            general = data.get("general", {})
            birthday = general.get("birthday")
            if not birthday or not self.is_valid_birthday(birthday):
                continue

            if int(birthday.split("/")[0]) != current_month:
                continue

            member = guild.get_member(int(uid))
            if member is None:
                continue

            if any(role.id == FAMILY_ROLE_ID for role in member.roles):
                fam_members.append(member)
            else:
                gen_members.append(member)

        channel = guild.get_channel(REMINDER_CHANNEL_ID)
        if channel:
            embed = discord.Embed(
                title=f"📅 Birthdays This Month — {now.strftime('%B')}",
                color=EMBED_COLOR,
                timestamp=now
            )
            embed.add_field(name="Family Members", value="\n".join(m.mention for m in fam_members) or "None", inline=True)
            embed.add_field(name="General Members", value="\n".join(m.mention for m in gen_members) or "None", inline=True)
            await channel.send(embed=embed)


async def setup(bot):
    await bot.add_cog(BirthdayListener(bot))
