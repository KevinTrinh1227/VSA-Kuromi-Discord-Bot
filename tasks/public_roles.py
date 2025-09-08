import discord
from discord.ext import commands
import json
import os
from datetime import datetime

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "config.json")

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


class SelfRolesView(discord.ui.View):
    def __init__(self, cfg, client):
        super().__init__(timeout=None)
        self.cfg = cfg
        self.client = client
        self.roles_data = cfg["features"]["self_roles_selection"]["list_of_roles"]
        self.default_color = discord.ButtonStyle.secondary

        color = cfg["features"]["self_roles_selection"].get("roles_selection_button_color", "").lower()
        style = {
            "primary": discord.ButtonStyle.primary,
            "secondary": discord.ButtonStyle.secondary,
            "success": discord.ButtonStyle.success,
            "danger": discord.ButtonStyle.danger,
            "grey": discord.ButtonStyle.secondary,
            "gray": discord.ButtonStyle.secondary,
            "blue": discord.ButtonStyle.primary
        }.get(color, self.default_color)

        for role in self.roles_data:
            label = role.get("image_menu_button_label") or role.get("embed_menu_button_label") or "❔"
            button = discord.ui.Button(label=label, style=style, custom_id=str(role["role_id"]))
            button.callback = self.button_callback
            self.add_item(button)

    async def button_callback(self, interaction: discord.Interaction):
        role_id = int(interaction.data["custom_id"])
        role = interaction.guild.get_role(role_id)
        if not role:
            print(f"[WARN] Role ID {role_id} not found in guild.")
            await interaction.response.send_message("Role not found.", ephemeral=True)
            return

        action = "claimed"
        if role in interaction.user.roles:
            await interaction.user.remove_roles(role)
            action = "unclaimed"
        else:
            await interaction.user.add_roles(role)

        await interaction.response.defer()

        # Define shared values
        embed_color = int(self.cfg["general"]["embed_color"].strip("#"), 16)
        emoji = "🟢" if action == "claimed" else "🔴"
        verb = "claimed" if action == "claimed" else "unclaimed"
        role_label = f"{role.mention} (`{role.id}`)"
        updated_roles = [r for r in interaction.user.roles if r.name != "@everyone"]
        roles_list = ", ".join(r.mention for r in updated_roles) or "None"

        # Optional: DM the user about their role change
        dm_user_role_log_status = "Unknown"
        if self.cfg["features"]["self_roles_selection"].get("dm_user_role_logs"):
            try:
                dm_embed = discord.Embed(
                    title=f"You have **{verb}** the {role.name} role!",
                    color=embed_color,
                )
                await interaction.user.send(embed=dm_embed)
                dm_user_role_log_status = "Role log sent to user"
            except discord.Forbidden:
                dm_user_role_log_status = "Role log NOT sent (DMs off)"
                # print(f"[INFO] Could not DM {interaction.user} (DMs likely disabled).")

        # Optional: Log role change to bot logs channel
        if self.cfg["features"]["self_roles_selection"].get("log_all_public_role_activity_in_bot_logs"):
            log_channel_id = int(self.cfg["text_channel_ids"]["bot_logs"])
            log_channel = self.client.get_channel(log_channel_id)
            action = "Claimed" if action == "claimed" else "Unclaimed"
            if not log_channel:
                print("[WARN] Bot logs channel not found.")
                return

            embed = discord.Embed(
                title=f"{emoji} | {interaction.user.name} {verb} a role from roles menu!",
                description=(
                    f"**User:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                    f"**Role:** {role_label}\n"
                    # f"**Current Roles ({len(updated_roles)}):** {roles_list}"
                ),
                color=discord.Color.green() if action == "Claimed" else discord.Color.red(),
                #timestamp=datetime.utcnow()
            )
            embed.set_footer(text=f"{dm_user_role_log_status}")

            if interaction.user.avatar:
                embed.set_thumbnail(url=interaction.user.avatar.url)

            await log_channel.send(embed=embed)


class SelfRoles(commands.Cog):
    """Allows users to select own roles."""

    def __init__(self, client):
        self.client = client
        self.cfg = load_config()
        self.channel_id = int(self.cfg["text_channel_ids"]["self_role_selection_menu"])

        if self.cfg["features"]["self_roles_selection"].get("enable_feature"):
            client.add_view(SelfRolesView(self.cfg, client))
            client.loop.create_task(self.sync_menu_once())

    async def sync_menu_once(self):
        await self.client.wait_until_ready()
        channel = self.client.get_channel(self.channel_id)
        if not channel:
            print("[WARN] Self-role selection channel not found.")
            return

        fr = self.cfg["features"]["self_roles_selection"]
        is_image_menu = fr.get("use_image_button_menu_instead_of_embed_menu", False)
        existing_message = None

        async for msg in channel.history(limit=1):
            existing_message = msg
            break

        buttons_view = SelfRolesView(self.cfg, self.client)

        if is_image_menu:
            path = fr.get("roles_menu_header_image_path")
            if not os.path.exists(path):
                print(f"[WARN] Image path not found: {path}")
                return

            file = discord.File(path, filename="header.png")
            should_delete = True

            if existing_message and existing_message.attachments:
                old_name = existing_message.attachments[0].filename
                if old_name == "header.png":
                    should_delete = False

            if existing_message and should_delete:
                await existing_message.delete()

            if not existing_message or should_delete:
                await channel.send(file=file, view=buttons_view)

        else:
            tpl = fr["embed_template"]
            expected_embed = discord.Embed(
                title=tpl["title"],
                description=tpl["description"],
                color=int(self.cfg["general"]["embed_color"].strip("#"), 16),
                timestamp=datetime.utcnow()
            )
            expected_embed.set_footer(
                text=tpl.get("footer_text", "").format(guild_name=channel.guild.name),
                icon_url=channel.guild.icon.url if channel.guild.icon else discord.Embed.Empty
            )

            should_delete = True
            if existing_message and existing_message.embeds:
                old = existing_message.embeds[0]
                if (
                    old.title == expected_embed.title and
                    old.description == expected_embed.description and
                    old.footer.text == expected_embed.footer.text
                ):
                    should_delete = False

            if existing_message and should_delete:
                await existing_message.delete()

            if not existing_message or should_delete:
                await channel.send(embed=expected_embed, view=buttons_view)


async def setup(client):
    await client.add_cog(SelfRoles(client))