# commands/verification.py

import discord
from discord.ext import commands
from discord.ui import Modal, TextInput, View, Button
import json
import os
import datetime

# Load configuration
CONFIG_PATH = 'config.json'
VERIFICATIONS_FILE = 'verified_user_data.json'

# Load config.json
with open(CONFIG_PATH) as f:
    cfg = json.load(f)

GUILD_ID = int(cfg['general']['discord_server_guild_id'])
VERIF_CHANNEL_ID = int(cfg['text_channel_ids']['verification'])
FAM_ROLE_ID = int(cfg['role_ids']['family_member'])
VERIFIED_ROLE_ID = int(cfg['role_ids']['verified_vsa_member'])
UNVER_ROLE_ID = int(cfg['role_ids']['unverified_vsa_member'])
TICKET_CHANNEL_ID = int(cfg['text_channel_ids']['tickets_menu'])
STAFF_ROLE_ID = int(cfg['role_ids']['staff_member'])
FAMILY_LEAD_ROLE_ID = int(cfg['role_ids']['family_lead'])

# Helper functions

def load_verifications():
    if os.path.exists(VERIFICATIONS_FILE):
        with open(VERIFICATIONS_FILE, 'r') as vf:
            return json.load(vf)
    return {}

def save_verifications(data):
    with open(VERIFICATIONS_FILE, 'w') as vf:
        json.dump(data, vf, indent=2)

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
        verifications = load_verifications()

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
            title='Are you a member of the Slytherin Family?',
            description=(
                'Click **Yes** if you are a member of this family, and **No** if you aren’t. '
                '**Note** we will verify using your information. If there is an issue please contact the family chair **Peter Nguyen**.'
            ),
            color=int(cfg['general']['embed_color'].strip('#'), 16)
        )
        embed.timestamp = datetime.datetime.utcnow()
        embed.set_footer(text=f"©️ {interaction.guild.name}")

        class FamilyView(View):
            def __init__(self):
                super().__init__(timeout=120)

            @discord.ui.button(label="Yes, I'm in Slytherin Fam.", style=discord.ButtonStyle.green)
            async def yes(self, interaction: discord.Interaction, button: Button):
                await interaction.response.defer(ephemeral=True)
                await self.next_step(interaction, True)

            @discord.ui.button(label="No, I'm not but I'll join!", style=discord.ButtonStyle.red)
            async def no(self, interaction: discord.Interaction, button: Button):
                await interaction.response.defer(ephemeral=True)
                await self.next_step(interaction, False)

            async def next_step(self, interaction: discord.Interaction, in_family: bool):
                data = interaction.client._verification_data
                data['in_family'] = in_family
                fam_status = 'Yes' if in_family else 'No'

                # Confirmation embed
                confirm = discord.Embed(
                    title='📋 | Verification Confirmation',
                    description=(
                        'By proceeding you confirm this form is only to validate your VSA/family membership '
                        'and that all information is correct and valid. Incorrect info may result in denial or removal.\n\n'
                        '**Please double check the following information:**\n'
                        f"**First Name:** {data['first_name']}\n"
                        f"**Last Name:** {data['last_name']}\n"
                        f"**DOB:** {data['birthday']}\n"
                        f"**PSID:** `{data['psid']}`\n"
                        f"**In Slytherin Family?** {fam_status}\n\n"
                        'If it is **100% correct**, click **Confirm & Verify** below. Otherwise click **Restart Verification** to begin again or **Cancel** to abort.'
                    ),
                    color=int(cfg['general']['embed_color'].strip('#'), 16)
                )
                confirm.timestamp = datetime.datetime.utcnow()
                confirm.set_footer(text=f"©️ {interaction.guild.name}")

                class ConfirmView(View):
                    def __init__(self):
                        super().__init__(timeout=120)

                    @discord.ui.button(label="Confirm & Verify", style=discord.ButtonStyle.green)
                    async def confirm(self, interaction: discord.Interaction, button: Button):
                        rec = interaction.client._verification_data
                        user = interaction.user

                        # Remove unverified role, add verified role
                        await user.remove_roles(user.guild.get_role(UNVER_ROLE_ID), reason='Verified')
                        await user.add_roles(user.guild.get_role(VERIFIED_ROLE_ID), reason='Verified')

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
                        verifs = load_verifications()
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
                        save_verifications(verifs)

                        # Send confirmation and close
                        await interaction.response.send_message('✅ You have been verified!', ephemeral=True)
                        self.stop()

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

        TARGET_TITLE = '📋 | VSA Member Verification'

        # Create the new embed in advance for comparison
        new_description = (
            f"To gain access to roles, permissions, and general server access including bot access, please verify your account below. Important information is listed below as well, and if you have any issues please contact a staff member or <@&{FAMILY_LEAD_ROLE_ID}>.\n\n"
            "**Why Verify?**\n"
            "Verification helps us confirm that you're a student and lets us automatically assign appropriate roles based on whether you're a"
            "family member, paid VSA member, unpaid VSA member, non VSA member, or just a UH student, etc.\n\n"
            "**We only ask for:**\n"
            "• Your **First** and **Last Name** *(Cause everyone has diff. Discord names)*\n"
            "• Your **Birthday** *(for birthday shoutouts, etc)*\n"
            "• Your **PSID/PeopleSoft ID** *(to verify roles and permissions)*\n\n"
            "**Your info stays private.**\n"
            "It's only used for role assignment and internal verification."
            " **Please note:** You **do not** need to be a Family Member or a paid VSA Member to verify — just a student with a valid PSID."
            "Submitting **false information and or someone's information** may lead to **removal from the server**.\n\n"
            "**Disclaimer Message: **Verification is highly encouraged for all students and especially **Family Members** or **VSA Members** if you want to get access to the entire server, but it is **not required**. You can still access some channels and commands/permissions etc.\n\n"
            "**Need Help?**\n"
            f"If something doesn't work or you're having trouble, please open a <#{TICKET_CHANNEL_ID}> and a <@&{STAFF_ROLE_ID}> will assist you shortly."
        )

        # Search for existing embed and collect messages to delete 
        found_embed_msg = None
        messages_to_delete = []

        async for msg in chan.history(limit=50):
            if msg.embeds:
                embed = msg.embeds[0]
                if embed.title == TARGET_TITLE:
                    if embed.description == new_description:
                        found_embed_msg = msg
                        continue
                    else:
                        # Embed exists but outdated → delete it
                        await msg.delete()
                else:
                    messages_to_delete.append(msg)
            else:
                messages_to_delete.append(msg)

        # Delete non-embed messages
        if messages_to_delete:
            await chan.delete_messages(messages_to_delete)

        # If no valid embed found, post new one
        if not found_embed_msg:
            embed = discord.Embed(
                title=TARGET_TITLE,
                description=new_description,
                color=int(cfg['general']['embed_color'].strip('#'), 16)
            )
            embed.timestamp = datetime.datetime.utcnow()
            embed.set_footer(text=f'©️ {self.bot.guilds[0].name}')
            view = self.StartVerificationView()
            await chan.send(embed=embed, view=view)


async def setup(bot):
    await bot.add_cog(VerificationLobby(bot))
