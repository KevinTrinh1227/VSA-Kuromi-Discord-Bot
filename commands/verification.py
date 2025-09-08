# commands/verification.py

import discord
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Button
import json
import os
import datetime
from utils.family_utils import is_family_member, get_family_role, get_total_verified_users
from utils.users_utils import get_verified_users, save_verified_users, get_unverified_users, save_unverified_users
from utils.stats_utils import is_vsa_officer


from dotenv import load_dotenv

load_dotenv()

# Load configuration
CONFIG_PATH = 'config.json'

# Load config.json
with open(CONFIG_PATH) as f:
    cfg = json.load(f)


GUILD_ID = int(os.getenv("DISCORD_SERVER_GUILD_ID"))
VERIF_CHANNEL_ID = int(cfg['text_channel_ids']['verification'])
FAM_ROLE_ID = int(cfg['role_ids']['family_member'])
VSA_OFFICER_ROLE_ID = int(cfg['role_ids']['vsa_officer_chair_member'])
PSUEDO_ROLE_ID = int(cfg['role_ids']['family_pseudo_member'])
VERIFIED_ROLE_ID = int(cfg['role_ids']['verified_vsa_member'])
UNVER_ROLE_ID = int(cfg['role_ids']['unverified_vsa_member'])
TICKET_CHANNEL_ID = int(cfg['text_channel_ids']['tickets_menu'])
STAFF_ROLE_ID = int(cfg['role_ids']['staff_member'])
FAMILY_LEAD_ROLE_ID = int(cfg['role_ids']['family_lead'])

FAM_NAME = cfg['general']['family_name']

BOT_LOGS_CHANNEL_ID = int(cfg['text_channel_ids']['bot_logs'])

# Modal for collecting user info
class VerificationModal(Modal, title='📋 | VSA Member Verification'):
    first_name = TextInput(label='First Name', placeholder='First name', required=True, max_length=30)
    last_name  = TextInput(label='Last Name', placeholder='Last name', required=True, max_length=30)
    birthday   = TextInput(label='Birthday (MM/DD/YYYY)', placeholder='MM/DD/YYYY', required=True, max_length=10)
    psid       = TextInput(label='PeopleSoft ID (PSID)', placeholder='12345678', required=True, max_length=20)

    async def on_submit(self, interaction: discord.Interaction):
        import datetime

        # Strip inputs
        raw_first = self.first_name.value.strip()
        raw_last  = self.last_name.value.strip()
        first_name = raw_first.capitalize()
        last_name  = raw_last.capitalize()

        birthday_raw = self.birthday.value.strip()
        psid = self.psid.value.strip()

        # Name validation
        if not (first_name.isalpha() and last_name.isalpha()):
            return await interaction.response.send_message(
                "❌ Names must only contain letters.", ephemeral=True
            )
        if not (2 <= len(first_name) <= 15) or not (2 <= len(last_name) <= 15):
            return await interaction.response.send_message(
                "❌ First and last names must be between 2 and 15 characters.", ephemeral=True
            )

        # PSID validation
        if not psid.isdigit() or not (4 <= len(psid) <= 8):
            return await interaction.response.send_message(
                "❌ PSID must be 4 - 8 digits and contain only numbers.", ephemeral=True
            )

        # Birthday parsing and validation
        dob = None
        try:
            dob = datetime.datetime.strptime(birthday_raw, "%m/%d/%Y")
        except ValueError:
            try:
                dob = datetime.datetime.strptime(birthday_raw, "%m%d%Y")
            except ValueError:
                return await interaction.response.send_message(
                    "❌ Invalid birthday format. Use MM/DD/YYYY or MMDDYYYY (e.g. 12/27/2002 or 12272002).",
                    ephemeral=True
                )

        # Age calculation
        today = datetime.date.today()
        birth_date = dob.date()
        age = today.year - birth_date.year - (
            (today.month, today.day) < (birth_date.month, birth_date.day)
        )

        # Formatted birthday string
        birthdate_formatted_str = birth_date.strftime("%b %d, %Y")  # e.g., "Dec 27, 2002"

        user_id_str = str(interaction.user.id)
        verifications = get_verified_users()

        # Check if user is already verified
        if user_id_str in verifications:
            return await interaction.response.send_message(
                f"❌ You are already verified. If you need help, open a <#{TICKET_CHANNEL_ID}>.",
                ephemeral=True
            )

        # Check if PSID is already in use
        if any(rec.get("psid") == psid for rec in verifications.values()):
            return await interaction.response.send_message(
                f"❌ That PSID is already linked to another user. Please open a <#{TICKET_CHANNEL_ID}> for support.",
                ephemeral=True
            )

        # Save all cleaned/validated data
        data = {
            "first_name": first_name,
            "last_name": last_name,
            "birthday": birthdate_formatted_str,
            "psid": psid,
            "age": age,
            "timestamp": datetime.datetime.utcnow().isoformat()
        }
        interaction.client._verification_data = data

        # Ask family membership
        embed = discord.Embed(
            title=f'Are you a member/psuedo of the {FAM_NAME}?',
            description=(
                'Click **Yes** if you are a member/psuedo of this family, and **No** if you aren\'t. '
                '\n\n**Note** we will verify using your information automatically after confirming. '
                'If you click yes, note that you must already be on the psuedo/family member list for verification to work successfully. '
                'Ignore this if you have already been assigned to this Fam or contacted a Fam Lead to psuedo. '
                'If not please contact a fam lead to add you. '
                '\n\nIf there is an issue please contact the family chair **Peter Nguyen**.'
            ),
            color=int(cfg['general']['embed_color'].strip('#'), 16)
        )
        embed.timestamp = datetime.datetime.utcnow()
        embed.set_footer(text=f"©️ {interaction.guild.name}")

        class FamilyView(View):
            def __init__(self):
                super().__init__(timeout=120)

            @discord.ui.button(label=f"Yes, I'm in {FAM_NAME} Fam.", style=discord.ButtonStyle.green)
            async def yes(self, interaction: discord.Interaction, button: Button):
                await interaction.response.defer(ephemeral=True)
                psid = interaction.client._verification_data.get("psid")

                if psid and is_family_member(psid):
                    await self.next_step(interaction, True)
                else:
                    await interaction.followup.send(
                        f"❌ We couldn't find your information in the family list. Please open a <#{TICKET_CHANNEL_ID}> if you believe this to be a mistake.",
                        ephemeral=True
                    )
                    await self.next_step(interaction, False)


            @discord.ui.button(label="No, I'm not but I'll join!", style=discord.ButtonStyle.red)
            async def no(self, interaction: discord.Interaction, button: Button):
                await interaction.response.defer(ephemeral=True)
                await self.next_step(interaction, False)


            async def next_step(self, interaction: discord.Interaction, in_family: bool):
                data = interaction.client._verification_data
                data['in_family'] = in_family
                fam_status = 'Yes (Successfully Validated)' if in_family else 'No'

                # Confirmation embed
                confirm = discord.Embed(
                    title='📋 | Verification Confirmation',
                    description=(
                        'By proceeding you confirm this form is only to validate your VSA/family membership '
                        'and that all information is correct and valid. Incorrect info may result in denial or removal.\n\n'
                        '**Double check the following information:**\n'
                        f"**Full Name:** {data['first_name']} {data['last_name']}\n"
                        f"**DOB:** {data['birthday']} (Only month & day will be visible)\n"
                        f"**PSID:** `{data['psid']}`\n"
                        f"**In {FAM_NAME} Fam?** {fam_status}\n"
                        f"**Family Role:** {get_family_role(psid)}\n\n"
                        'If it is **100% correct**, click **Confirm & Verify** below. Otherwise click **Restart Verification** to begin again or **Cancel** to abort.'
                    ),
                    color=int(cfg['general']['embed_color'].strip('#'), 16)
                )
                confirm.timestamp = datetime.datetime.utcnow()
                confirm.set_footer(text=f"©️ {interaction.guild.name}")

                class ConfirmView(View):
                    def __init__(self):
                        super().__init__(timeout=120)
                        
                    async def verify_member(user, psid: int, in_family: bool):
                        guild = user.guild
                        roles_to_add = []
                        roles_to_remove = []

                        # Always remove unverified role, add verified role
                        unverified_role = guild.get_role(UNVER_ROLE_ID)
                        verified_role = guild.get_role(VERIFIED_ROLE_ID)

                        if unverified_role:
                            roles_to_remove.append(unverified_role)
                        if verified_role:
                            roles_to_add.append(verified_role)

                        # Family roles
                        if in_family:
                            fam_role = get_family_role(psid)

                            if fam_role == "Psuedo (Unofficial Member)":
                                pseudo_role = guild.get_role(PSUEDO_ROLE_ID)
                                if pseudo_role:
                                    roles_to_add.append(pseudo_role)

                            elif fam_role == "Member (Official)":
                                fam_member_role = guild.get_role(FAM_ROLE_ID)
                                if fam_member_role:
                                    roles_to_add.append(fam_member_role)

                            elif fam_role == "Family Leader":
                                leader_role = guild.get_role(FAMILY_LEAD_ROLE_ID)
                                if leader_role:
                                    roles_to_add.append(leader_role)

                        # Officer check
                        if is_vsa_officer(psid):
                            officer_role = guild.get_role(VSA_OFFICER_ROLE_ID)
                            if officer_role:
                                roles_to_add.append(officer_role)

                        # Apply role changes in bulk
                        if roles_to_remove:
                            await user.remove_roles(*roles_to_remove, reason="Verification update")
                        if roles_to_add:
                            await user.add_roles(*roles_to_add, reason="Verification update")


                    @discord.ui.button(label="Confirm & Verify", style=discord.ButtonStyle.green)
                    async def confirm(self, interaction: discord.Interaction, button: Button):
                        rec = interaction.client._verification_data
                        user = interaction.user

                        # Remove unverified role, add verified role
                        await self.verify_member(user, psid, in_family)
                        

                        # Build nickname
                        nickname_template = cfg.get("nickname_templates", {})
                        before = nickname_template.get("format_before_seperator", "").strip()
                        separator = nickname_template.get("seperator_symbol", "|")
                        after = nickname_template.get("format_after_seperator", "{first_name} {last_name}").strip()

                        first = rec.get("first_name")
                        last = rec.get("last_name")
                        level = 0  # Starting level

                        formatted_after = after.replace("{first_name}", first).replace("{last_name}", last)
                        if "{level}" in before:
                            formatted_before = before.replace("{level}", str(level))
                        else:
                            formatted_before = before

                        nickname = f"{formatted_before}{separator}{formatted_after}"
                        try:
                            await user.edit(nick=nickname[:32])
                        except discord.Forbidden:
                            pass

                        if rec.get('in_family'):
                            await user.add_roles(user.guild.get_role(FAM_ROLE_ID), reason='Family Member')

                        # Save record
                        verifs = get_verified_users()
                        formatted_birthday = datetime.datetime.strptime(
                            rec["birthday"], "%b %d, %Y"
                        ).strftime("%m/%d/%Y")
                        verifs[str(user.id)] = {
                            "general": {
                                "first_name": rec["first_name"],
                                "last_name": rec["last_name"],
                                "birthday": formatted_birthday,
                                "psid": rec["psid"],
                                "timestamp": rec["timestamp"],
                                "in_family": rec["in_family"]
                            }
                        }
                        
                        # Move from unverified to verified, keep discord_profile if exists
                        unverified = get_unverified_users()
                        user_id_str = str(user.id)
                        if user_id_str in unverified:
                            discord_profile = unverified[user_id_str].get("discord_profile", {})
                            verifs[user_id_str]["discord_profile"] = discord_profile
                            del unverified[user_id_str]
                            save_unverified_users(unverified)

                        # Save verified users file after update
                        save_verified_users(verifs)


                        # Send confirmation and close
                        await interaction.response.send_message('✅ You have been verified! All proper roles and permissions have been awarded to you. Use `/help` for command options!', ephemeral=True)
                        self.stop()
                        
                        # Create a second embed for the target channel (Bot Logs)
                        total_verifications = get_total_verified_users()
                        embed_public = discord.Embed(
                            title=f"🪪 | New Verified User: {interaction.user} (#{total_verifications + 1})",
                            description="A discord member has just verified themselves.",
                            color=discord.Color.green(),
                            timestamp=datetime.datetime.utcnow()
                        )

                        # Add fields with user data
                        embed_public.add_field(name="First Name", value=rec["first_name"], inline=True)
                        embed_public.add_field(name="Last Name", value=rec["last_name"], inline=True)
                        embed_public.add_field(name="PSID", value=rec["psid"], inline=True)
                        embed_public.add_field(name="Birthday", value=rec["birthday"], inline=True)
                        embed_public.add_field(name="In Family", value="Yes" if rec.get("in_family") else "No", inline=True)

                        fam_role = get_family_role(psid) if rec.get("in_family") else "N/A"
                        embed_public.add_field(name="Family Role", value=fam_role, inline=True)

                        # Footer and thumbnail (user avatar or guild icon)
                        if interaction.user.avatar:
                            embed_public.set_thumbnail(url=interaction.user.avatar.url)
                        elif interaction.guild.icon:
                            embed_public.set_thumbnail(url=interaction.guild.icon.url)

                        embed_public.set_footer(
                            text=f"{interaction.guild.name}",
                            icon_url=interaction.guild.icon.url if interaction.guild.icon else None
                        )

                        # Send to bot logs channel
                        channel = interaction.client.get_channel(BOT_LOGS_CHANNEL_ID)
                        if channel:
                            await channel.send(embed=embed_public)

                    @discord.ui.button(label="Restart Verification", style=discord.ButtonStyle.gray)
                    async def restart(self, interaction: discord.Interaction, button: Button):
                        # Restart the modal
                        await interaction.response.send_modal(VerificationModal())

                    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red)
                    async def cancel(self, interaction: discord.Interaction, button: Button):
                        await interaction.response.send_message('❌ Verification cancelled.', ephemeral=True)
                        self.stop()

                # Use followup since we deferred earlier
                await interaction.followup.send(embed=confirm, view=ConfirmView(), ephemeral=True)

        # Send the "Are you in family?" embed with its view
        await interaction.response.send_message(embed=embed, view=FamilyView(), ephemeral=True)
        
        
        


# Cog to post lobby
class VerificationLobby(commands.Cog):
    class StartVerificationView(View):
        def __init__(self):
            super().__init__(timeout=None)

        @discord.ui.button(
            label='Start Verification',
            style=discord.ButtonStyle.primary,
            emoji='✅',
            custom_id='start_verification'
        )
        async def start(self, interaction: discord.Interaction, button: Button):
            await interaction.response.send_modal(VerificationModal())

    def __init__(self, bot):
        self.bot = bot
        # register persistent view
        bot.add_view(self.StartVerificationView())
        bot.loop.create_task(self.ensure_lobby())

    async def ensure_lobby(self):
        await self.bot.wait_until_ready()
        chan = self.bot.get_channel(VERIF_CHANNEL_ID)
        if not chan:
            return

        # Search for existing messages to delete
        found_msg = None
        messages_to_delete = []

        async for msg in chan.history(limit=50):
            if msg.attachments:
                if msg.attachments[0].filename == "verification_menu.png":
                    found_msg = msg
                    continue
            messages_to_delete.append(msg)

        # Delete outdated messages
        if messages_to_delete:
            await chan.delete_messages(messages_to_delete)

        # If no valid image found, send new one
        if not found_msg:
            file_path = "assets/outputs/verification_menu.png"
            view = self.StartVerificationView()
            await chan.send(file=discord.File(file_path), view=view)
            

    @commands.hybrid_command(name="verifiedstats", description="Show server stats from verified user data.")
    async def verifiedstats(self, ctx: commands.Context):
        data = get_verified_users

        total_users = len(data)
        users_with_stats = sum(1 for u in data.values() if "stats" in u)
        total_in_family = sum(1 for u in data.values() if u["general"].get("in_family", False))
        total_not_in_family = total_users - total_in_family
        percent_in_family = (total_in_family / total_users) * 100 if total_users > 0 else 0

        # EXP & coins
        total_exp = sum(u.get("stats", {}).get("exp", 0) for u in data.values())
        avg_exp = total_exp / total_users if total_users else 0
        total_coins = sum(u.get("stats", {}).get("coins", 0) for u in data.values())
        avg_coins = total_coins / total_users if total_users else 0

        top_exp_user = max(data.items(), key=lambda x: x[1].get("stats", {}).get("exp", 0), default=(None, {}))
        top_coin_user = max(data.items(), key=lambda x: x[1].get("stats", {}).get("coins", 0), default=(None, {}))
        top_msg_user = max(data.items(), key=lambda x: x[1].get("stats", {}).get("total_messages_sent", 0), default=(None, {}))

        # Messages
        total_msgs = sum(u.get("stats", {}).get("total_messages_sent", 0) for u in data.values())
        avg_msgs = total_msgs / total_users if total_users else 0

        # Timestamps
        newest = max(data.values(), key=lambda u: u["general"]["timestamp"])
        oldest = min(data.values(), key=lambda u: u["general"]["timestamp"])

        # Birth months
        from collections import Counter
        import datetime
        birth_months = Counter()
        name_counter = Counter()

        for u in data.values():
            # Birth month
            try:
                dt = datetime.datetime.strptime(u["general"]["birthday"], "%m/%d/%Y")
                birth_months[dt.strftime("%B")] += 1
            except:
                pass
            # Name counts
            name_counter[u["general"]["first_name"]] += 1

        most_common_month = birth_months.most_common(1)[0][0] if birth_months else "N/A"
        most_common_name = name_counter.most_common(1)[0][0] if name_counter else "N/A"
        current_month = datetime.datetime.now().strftime("%B")
        current_month_bdays = birth_months.get(current_month, 0)

        # Format embed
        embed = discord.Embed(
            title=f"📊 | {ctx.guild.name} Statistics",
            color=int(cfg['general']['embed_color'].strip('#'), 16)
        )

        embed.description = (
            f"**👥 General Info**\n"
            f"• Total Verified Users: `{total_users}`\n"
            f"• Newest Verified: `{newest['general']['first_name']} {newest['general']['last_name']}`\n"
            f"• Oldest Verified: `{oldest['general']['first_name']} {oldest['general']['last_name']}`\n\n"

            f"**🏠 Family Membership**\n"
            f"• In Family: `{total_in_family}` ({percent_in_family:.1f}%)\n"
            f"• Not in Family: `{total_not_in_family}`\n\n"

            f"**📈 EXP & 💰 Coins**\n"
            f"• Total EXP: `{round(total_exp, 2)}`\n"
            f"• Avg EXP: `{round(avg_exp, 2)}`\n"
            f"• Most EXP: `{top_exp_user[1]['general']['first_name']} {top_exp_user[1]['general']['last_name']}` ({top_exp_user[1].get('stats', {}).get('exp', 0)} EXP)\n"
            f"• Total Coins: `{total_coins}`\n"
            f"• Avg Coins: `{round(avg_coins, 2)}`\n"
            f"• Richest User: `{top_coin_user[1]['general']['first_name']} {top_coin_user[1]['general']['last_name']}` ({top_coin_user[1].get('stats', {}).get('coins', 0)} coins)\n\n"

            f"**💬 Activity**\n"
            f"• Users with Activity Stats: `{users_with_stats}`\n"
            f"• Total Messages Sent: `{total_msgs}`\n"
            f"• Avg Messages/User: `{round(avg_msgs, 2)}`\n"
            f"• Top Chatter: `{top_msg_user[1]['general']['first_name']} {top_msg_user[1]['general']['last_name']}` ({top_msg_user[1].get('stats', {}).get('total_messages_sent', 0)} messages)\n\n"

            f"**🎂 Birthdays & Names**\n"
            f"• Most Common First Name: `{most_common_name}`\n"
            f"• Most Common Birth Month: `{most_common_month}`\n"
            f"• Birthdays This Month ({current_month}): `{current_month_bdays}`\n"
        )

        await ctx.send(embed=embed)



async def setup(bot):
    await bot.add_cog(VerificationLobby(bot))
