import discord
from discord.ext import commands
from discord import app_commands
import json
import os

from utils.stats_utils import get_instagram_by_psid

class FamilyMembers(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config_path = 'config.json'
        self.db_path = 'data/family_and_pseudos_db.json'
        self.load_config()
        self.load_db()

    def load_config(self):
        """Load configuration from config.json."""
        with open(self.config_path, 'r') as f:
            self.config = json.load(f)

    def load_db(self):
        """Load family and pseudo members database."""
        if os.path.exists(self.db_path):
            with open(self.db_path, 'r') as f:
                self.db = json.load(f)
        else:
            self.db = {"fam_leads": {}, "fam_members": {}, "fam_psuedos": {}}

    def save_db(self):
        """Save the database to a file."""
        with open(self.db_path, 'w') as f:
            json.dump(self.db, f, indent=4)

    def get_member_type(self, psid):
        """Determine if a PSID is a lead, member, or pseudo member."""
        if str(psid) in self.db['fam_leads']:
            return 'lead'
        elif str(psid) in self.db['fam_members']:
            return 'member'
        elif str(psid) in self.db['fam_psuedos']:
            return 'pseudo'
        else:
            return None

    @app_commands.command(name="myfam", description="Manage family members")
    @app_commands.describe(
        psid="PSID of the member",
        first_name="First Name",
        last_name="Last Name",
        idx="Index of member to remove"
    )
    @app_commands.choices(
        action=[
            app_commands.Choice(name="Add", value="add"),
            app_commands.Choice(name="Remove", value="remove"),
            app_commands.Choice(name="List", value="list")
        ],
        member_type=[
            app_commands.Choice(name="Official Family Member", value="official"),
            app_commands.Choice(name="Pseudo Member", value="pseudo")
        ]
    )
    async def myfam(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        member_type: app_commands.Choice[str] = None,  # only needed for Add
        psid: int = None,
        first_name: str = None,
        last_name: str = None,
        idx: int = None
    ):
        """Manage family members."""
        # Permission check
        family_lead_role_id = int(self.config['role_ids']['family_lead'])
        if not any(role.id == family_lead_role_id for role in interaction.user.roles):
            await interaction.response.send_message(
                f"You need the <@&{family_lead_role_id}> role.", ephemeral=True
            )
            return

        if action.value == "add":
            if not all([psid, first_name, last_name, member_type]):
                await interaction.response.send_message(
                    "For adding, you must provide PSID, first name, last name, and select member type.",
                    ephemeral=True
                )
                return
            if member_type.value == "official":
                self.db['fam_members'][str(psid)] = {'first_name': first_name, 'last_name': last_name}
            else:
                self.db['fam_psuedos'][str(psid)] = {'first_name': first_name, 'last_name': last_name}
            self.save_db()
            await interaction.response.send_message(
                f"✅ Successfully added {first_name} {last_name} as {member_type.name}.", ephemeral=True
            )

        elif action.value == "remove":
            if psid is None:
                await interaction.response.send_message(
                    "To remove a member, you must provide the PSID of the member.",
                    ephemeral=True
                )
                return

            member_type = self.get_member_type(psid)
            if not member_type:
                await interaction.response.send_message(
                    f"No member found with PSID {psid}.",
                    ephemeral=True
                )
                return

            # Remove from the appropriate category
            del self.db[{'lead': 'fam_leads', 'member': 'fam_members', 'pseudo': 'fam_psuedos'}[member_type]][str(psid)]
            self.save_db()
            await interaction.response.send_message(
                f"✅ Successfully removed member with PSID {psid} from {member_type}.",
                ephemeral=True
            )


        elif action.value == "list":
            self.load_db()
            fam_leads = self.db.get('fam_leads', {})
            fam_members = self.db.get('fam_members', {})
            fam_psuedos = self.db.get('fam_psuedos', {})

            total_leads = len(fam_leads)
            total_members = len(fam_members)
            total_psuedos = len(fam_psuedos)
            total_all = total_leads + total_members + total_psuedos

            if total_all == 0:
                await interaction.response.send_message("No members found.", ephemeral=True)
                return

            msg_lines = []

            # Family Leads
            msg_lines.append(f"**Family Leads ({total_leads})**")
            for idx, (psid, member) in enumerate(fam_leads.items(), start=1):
                ig_user = get_instagram_by_psid(psid)
                if ig_user:
                    msg_lines.append(f"{idx}. `PSID: {psid}` {member['first_name']} {member['last_name']} - IG: [@{ig_user}](https://www.instagram.com/{ig_user}/)")
                else:
                    msg_lines.append(f"{idx}. `PSID: {psid}` {member['first_name']} {member['last_name']} - IG: Not Set")

            # Family Members
            msg_lines.append(f"\n**Family Members ({total_members})**")
            for idx, (psid, member) in enumerate(fam_members.items(), start=1):
                ig_user = get_instagram_by_psid(psid)
                if ig_user:
                    msg_lines.append(f"{idx}. `PSID: {psid}` {member['first_name']} {member['last_name']} - IG: [@{ig_user}](https://www.instagram.com/{ig_user}/)")
                else:
                    msg_lines.append(f"{idx}. `PSID: {psid}` {member['first_name']} {member['last_name']} - IG: Not Set")

            # Psuedo Members
            msg_lines.append(f"\n**Psuedo Members ({total_psuedos})**")
            for idx, (psid, member) in enumerate(fam_psuedos.items(), start=1):
                ig_user = get_instagram_by_psid(psid)
                if ig_user:
                    msg_lines.append(f"{idx}. `PSID: {psid}` {member['first_name']} {member['last_name']} - IG: [@{ig_user}](https://www.instagram.com/{ig_user}/)")
                else:
                    msg_lines.append(f"{idx}. `PSID: {psid}` {member['first_name']} {member['last_name']} - IG: Not Set")
                
            msg_lines.append(f"\nTotal Members ({total_all})")

            await interaction.response.send_message("\n".join(msg_lines), ephemeral=True)



async def setup(bot):
    await bot.add_cog(FamilyMembers(bot))
