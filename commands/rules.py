import discord
from discord.ext import commands
import discord.ui
import datetime
import json
import os

# Load config.json
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.json')
with open(CONFIG_PATH) as json_file:
    data = json.load(json_file)

# Embed config
embed_color = int(data["general"]["embed_color"].strip("#"), 16)
feature_enabled = data.get("features", {}).get("rules", {}).get("enable_feature", False)
embed_template_config = data.get("features", {}).get("rules", {}).get("auto_send_rules_message", {}).get("embed_template", {})

VSA_FAMILY_NAME = data["general"]["family_name"]

# Channel IDs from config
RULES_CHANNEL_ID = int(data.get("text_channel_ids", {}).get("rules_channel", 0))
TICKETS_MENU_CHANNEL_ID = int(data.get("text_channel_ids", {}).get("tickets_menu", 0))


class rules(commands.Cog):
    """Handles sending and displaying the server rules embed."""
    description = "Handles sending and displaying the server rules embed."

    def __init__(self, client):
        self.client = client
        if feature_enabled:
            self.client.loop.create_task(self.sync_once_on_startup())

    async def sync_once_on_startup(self):
        await self.client.wait_until_ready()
        await self.sync_rules_embed()

    async def sync_rules_embed(self):
        if not RULES_CHANNEL_ID:
            print("Rules channel ID not set in config.json")
            return

        channel = self.client.get_channel(RULES_CHANNEL_ID)
        if not channel:
            print("Rules channel not found or bot missing access.")
            return

        # Build expected embed
        footer_text = embed_template_config.get("footer", "").replace(
            "{family_name}", VSA_FAMILY_NAME
        )
        description = embed_template_config.get("description", "").replace(
            "{tickets_menu_channel}", f"<#{TICKETS_MENU_CHANNEL_ID}>"
        )

        expected_embed = discord.Embed(
            title=embed_template_config.get("title", "Rules"),
            description=description,
            color=embed_color
        )
        if channel.guild.icon:
            expected_embed.set_footer(text=footer_text, icon_url=channel.guild.icon.url)
        else:
            expected_embed.set_footer(text=footer_text)

        # Get most recent message
        last_msg = None
        async for msg in channel.history(limit=1):
            last_msg = msg
            break

        if last_msg:
            should_edit = False
            should_delete = False

            if last_msg.embeds:
                existing = last_msg.embeds[0]
                same_embed = (
                    existing.title == expected_embed.title and
                    existing.description == expected_embed.description and
                    (existing.footer.text if existing.footer else None) == expected_embed.footer.text and
                    (existing.footer.icon_url if existing.footer and existing.footer.icon_url else None) ==
                    (expected_embed.footer.icon_url if expected_embed.footer and expected_embed.footer.icon_url else None)
                )

                if same_embed:
                    # Embed is identical, do nothing
                    return

                if last_msg.author == self.client.user:
                    should_edit = True
                else:
                    should_delete = True
            else:
                should_delete = True

            if should_edit:
                try:
                    await last_msg.edit(embed=expected_embed)
                    return
                except Exception as e:
                    print(f"Failed to edit rules embed, deleting instead: {e}")
                    should_delete = True

            if should_delete:
                try:
                    await last_msg.delete()
                except Exception as e:
                    print(f"Failed to delete previous message: {e}")

        # Send new message
        await channel.send(embed=expected_embed)

    @commands.hybrid_command(
        name="rules",
        description="View the server rules"
    )
    async def rules(self, ctx):
        footer_text = embed_template_config.get("footer", "").replace(
            "{family_name}", VSA_FAMILY_NAME
        )
        description = embed_template_config.get("description", "").replace(
            "{tickets_menu_channel}", f"<#{TICKETS_MENU_CHANNEL_ID}>"
        )

        embed = discord.Embed(
            title=embed_template_config.get("title", "Rules"),
            description=description,
            color=embed_color
        )
        embed.timestamp = datetime.datetime.now()
        if ctx.guild.icon:
            embed.set_footer(text=footer_text, icon_url=ctx.guild.icon.url)
        else:
            embed.set_footer(text=footer_text)

        await ctx.send(embed=embed)


async def setup(client):
    await client.add_cog(rules(client))