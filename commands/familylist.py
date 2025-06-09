import discord
from discord.ext import commands
from discord import app_commands
import json
from utils.users_utils import get_verified_users

FAMILY_FILE = "list_of_family_members.json"
CONFIG_FILE = "config.json"

with open(CONFIG_FILE) as f:
    cfg = json.load(f)

EMBED_COLOR = int(cfg["general"]["embed_color"].strip("#"), 16)
FAMILY_NAME = cfg["general"]["family_name"]
BOT_LOGS_CHANNEL_ID = int(cfg["text_channel_ids"]["bot_logs"])

def load_family_data():
    with open(FAMILY_FILE, "r") as f:
        return json.load(f)

def save_family_data(data):
    with open(FAMILY_FILE, "w") as f:
        json.dump(data, f, indent=2)

class FamilyList(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="familylist", description="Manage the family list: view/add/remove")
    @app_commands.describe(
        action="Choose an action",
        visibility="Visibility for view action",
        first="First name (for add)",
        last="Last name (for add)",
        psid="PSID",
        role="Role (for add): Lead or Member"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="View", value="view"),
            app_commands.Choice(name="Add", value="add"),
            app_commands.Choice(name="Remove", value="remove")
        ],
        visibility=[
            app_commands.Choice(name="Public", value="public"),
            app_commands.Choice(name="Private", value="private")
        ],
        role=[
            app_commands.Choice(name="Member", value="Member"),
            app_commands.Choice(name="Lead", value="Lead")
        ]
    )
    async def familylist(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        visibility: app_commands.Choice[str] = None,
        first: str = None,
        last: str = None,
        psid: str = None,
        role: app_commands.Choice[str] = None,
    ):
        # Make sure role param is string or default
        role_value = role.value if role else "Member"
        action_value = action.value
        visibility_value = visibility.value if visibility else None

        family_data = load_family_data()
        verified_data = get_verified_users()


        # Everyone can run only view public or just view with no param (default to public)
        # Everything else is admin only + ephemeral responses (only visible to caller)
        is_admin = interaction.user.guild_permissions.administrator
        ephemeral_response = True  # Default to ephemeral

        # Enforce admin only for add/remove and private view
        if action_value in ["add", "remove"] or (action_value == "view" and visibility_value == "private"):
            if not is_admin:
                await interaction.response.send_message("❌ Only administrators can use this command.", ephemeral=True)
                return
        # For view public or default view (no visibility param), everyone can run, non-ephemeral
        if action_value == "view" and (visibility_value == "public" or visibility_value is None):
            ephemeral_response = False

        # === VIEW ===
        if action_value == "view":
            total_count = len(family_data)
            embed = discord.Embed(
                title=f"📜 | {FAMILY_NAME} Family Members ({total_count})",
                color=EMBED_COLOR,
                timestamp=discord.utils.utcnow()
            )

            leads = []
            members = []

            for psid_key, member in family_data.items():
                # role fallback default to Member
                r = member.get("role", "Member")
                entry = (psid_key, member["first_name"], member["last_name"], r)
                if r.lower() == "lead":
                    leads.append(entry)
                else:
                    members.append(entry)

            def format_field(index, psid, first, last, role):
                # Verified check by matching psid in verified data
                is_verified = any(d.get("general", {}).get("psid") == psid for d in verified_data.values())
                emoji = "🟢" if is_verified else "🔴"
                # Show PSID only if private view
                psid_str = f" - PSID: `{psid}`" if visibility_value == "private" else f" "
                name = f"{emoji} | {index}. {first} {last}{psid_str}"
                # Mention if verified, else "Not verified yet."
                user_id = next((uid for uid, d in verified_data.items() if d.get("general", {}).get("psid") == psid), None)
                mention = f"<@{user_id}>" if user_id else "Not verified yet."
                return name, mention

            index = 1
            if leads:
                embed.add_field(name="**🧠 Family Leads**", value="─" * 30, inline=False)
                for psid_, first_, last_, _ in leads:
                    n, v = format_field(index, psid_, first_, last_, "Lead")
                    embed.add_field(name=n, value=v, inline=False)
                    index += 1

            if members:
                embed.add_field(name="**👥 Members**", value="─" * 30, inline=False)
                for psid_, first_, last_, _ in members:
                    n, v = format_field(index, psid_, first_, last_, "Member")
                    embed.add_field(name=n, value=v, inline=False)
                    index += 1

            # Footer with server icon if exists
            if interaction.guild.icon:
                embed.set_footer(text=f"©️ {interaction.guild.name}", icon_url=interaction.guild.icon.url)
            else:
                embed.set_footer(text=f"©️ {interaction.guild.name}")

            await interaction.response.send_message(embed=embed, ephemeral=ephemeral_response)
            return

        # === ADD ===
        if action_value == "add":
            if not all([first, last, psid]):
                return await interaction.response.send_message("❌ You must provide first name, last name, and PSID.", ephemeral=True)

            if psid in family_data:
                return await interaction.response.send_message("⚠️ This PSID already exists.", ephemeral=True)

            role_str = role_value.capitalize()
            if role_str not in ["Member", "Lead"]:
                return await interaction.response.send_message("❌ Role must be 'Member' or 'Lead'.", ephemeral=True)

            family_data[psid] = {
                "first_name": first,
                "last_name": last,
                "role": role_str
            }
            save_family_data(family_data)

            # Log to bot logs channel
            bot_logs_channel = self.bot.get_channel(BOT_LOGS_CHANNEL_ID)
            if bot_logs_channel:
                await bot_logs_channel.send(
                    f"✅ **FamilyList Add:** `{first} {last}` with PSID `{psid}` as **{role_str}** added by {interaction.user.mention}"
                )

            await interaction.response.send_message(
                f"✅ Successfully added `{first} {last}` with PSID `{psid}` as **{role_str}**.", ephemeral=True
            )
            return

        # === REMOVE ===
        if action_value == "remove":
            if not psid:
                return await interaction.response.send_message("❌ You must provide a PSID to remove.", ephemeral=True)
            if psid not in family_data:
                return await interaction.response.send_message("❌ This PSID does not exist in the list.", ephemeral=True)

            removed = family_data.pop(psid)
            save_family_data(family_data)

            # Log to bot logs channel
            bot_logs_channel = self.bot.get_channel(BOT_LOGS_CHANNEL_ID)
            if bot_logs_channel:
                await bot_logs_channel.send(
                    f"🗑️ **FamilyList Remove:** `{removed['first_name']} {removed['last_name']}` with PSID `{psid}` removed by {interaction.user.mention}"
                )

            await interaction.response.send_message(
                f"🗑️ Removed `{removed['first_name']} {removed['last_name']}` with PSID `{psid}`.", ephemeral=True
            )
            return

async def setup(bot):
    await bot.add_cog(FamilyList(bot))
