import discord
from discord.ext import commands
from discord import app_commands
import json
from datetime import datetime
from collections import defaultdict
from utils.users_utils import get_verified_users

# Load config
with open('config.json') as json_file:
    config = json.load(json_file)

embed_color = int(config["general"]["embed_color"].strip("#"), 16)

# Helper function for ordinal dates
def get_day_suffix(day):
    if 11 <= day <= 13:
        return f"{day}th"
    last_digit = day % 10
    if last_digit == 1:
        return f"{day}st"
    elif last_digit == 2:
        return f"{day}nd"
    elif last_digit == 3:
        return f"{day}rd"
    else:
        return f"{day}th"

class Birthdays(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.hybrid_command(
        name="birthdays",
        aliases=["bday", "bdays"],
        brief="birthdays",
        description="Displays all member birthdays",
        with_app_command=True
    )
    @app_commands.describe(role="Filter birthdays by this role (optional)")
    async def birthdays(self, ctx: commands.Context, role: discord.Role = None):
        user_data = get_verified_users()

        now = datetime.now()
        month_map = defaultdict(list)
        total_count = 0

        for user_id, data in user_data.items():
            user_id_int = int(user_id)
            member = ctx.guild.get_member(user_id_int)
            if member is None:
                continue  # Skip if user not in server

            # If role param given, skip if member doesn't have that role
            if role and role not in member.roles:
                continue

            birthday_str = data["general"].get("birthday")
            if not birthday_str:
                continue

            try:
                birthday_date = datetime.strptime(birthday_str, "%m/%d/%Y")
                birthday_this_year = birthday_date.replace(year=now.year)
            except ValueError:
                continue

            if birthday_this_year < now:
                birthday_this_year = birthday_this_year.replace(year=now.year + 1)

            days_until = (birthday_this_year - now).days
            suffix_day = get_day_suffix(birthday_date.day)
            month_name = birthday_date.strftime("%B")
            formatted_date = f"{month_name} {suffix_day}"

            time_text = "`Today! 🎉`" if days_until == 0 else f"`{days_until}d away`"

            display_line = f"{member.mention} - {formatted_date} - {time_text}"
            month_map[month_name].append((birthday_date.day, display_line))
            total_count += 1
            

        if total_count == 0:
            await ctx.send("No birthdays found.")
            return

        # inside your birthdays command, after collecting total_count and before creating embed

        if role is not None:
            description_text = f"Displaying **{total_count}** server member birthdays with role <@&{role.id}>.\n"
        else:
            description_text = f"Displaying **{total_count}** server member birthdays.\n"

        embed = discord.Embed(
            title=":birthday: | Displaying All Birthdays",
            description=description_text,
            color=embed_color
        )

        #if ctx.guild.icon:
        #    embed.set_thumbnail(url=ctx.guild.icon.url)

        # Define months in order
        months_order = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        current_month_name = now.strftime("%B")


        # Add fields in order, adding green circle for current month
        for month in months_order:
            if month in month_map:
                entries = sorted(month_map[month], key=lambda x: x[0])
                lines = [entry[1] for entry in entries]
                prefix = "🟢 " if month == current_month_name else ""
                embed.add_field(name=f"\n{prefix}{month} Birthdays ({len(lines)}):", value="\n".join(lines), inline=False)

        embed.timestamp = datetime.now()
        if ctx.guild.icon:
            embed.set_footer(text=f"©️ {ctx.guild.name}", icon_url=ctx.guild.icon.url)


        await ctx.send(embed=embed)


async def setup(client):
    await client.add_cog(Birthdays(client))
