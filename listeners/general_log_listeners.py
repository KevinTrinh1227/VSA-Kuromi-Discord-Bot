import discord
from discord.ext import commands
import discord.ui
import datetime
import json
from PIL import Image, ImageFont, ImageDraw
from io import BytesIO
import requests
import os

# Open the JSON file and read in the data
with open('config.json') as json_file:
    data = json.load(json_file)
    
# Load the "join_dm_message" template
join_dm_template = data["embed_templates"]["join_dm_message"]
    
# JSON file for verified user data
VERIFIED_USER_FILE = "verified_user_data.json"
    
# Bot configuration
bot_prefix = data["general"]["bot_prefix"]
embed_color = int(data["general"]["embed_color"].strip("#"), 16)
member_role_id = int(data["role_ids"]["unverified_vsa_member"])
welcome_channel_id = int(data["text_channel_ids"]["welcome"])
pre_embed_color = data["general"]["embed_color"].strip("#")
logs_channel_id = int(data["text_channel_ids"]["bot_logs"])

font_title = ImageFont.truetype("./assets/fonts/Minecraft.ttf", 20)
font_footer = ImageFont.truetype("./assets/fonts/Minecraft.ttf", 15)


class joinleave(commands.Cog):
    def __init__(self, client):
        self.client = client

    # Welcome message; not logged to logs_channel_id
    @commands.Cog.listener()
    async def on_member_join(self, member):
        def hex_to_rgb(hex_color):
            return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        
        member_count = len(member.guild.members)
        
        # Load background and profile picture
        background_image = Image.open("./assets/backgrounds/welcome_banner.png")
        if member.avatar:
            pfp_url = member.avatar.url
        else:
            pfp_url = member.guild.icon.url

        pfp_response = requests.get(pfp_url)
        member_pfp = Image.open(BytesIO(pfp_response.content)).resize((100, 100))

        # Center coordinates
        image_width, image_height = background_image.size
        center_x = image_width // 2
        center_y = image_height // 2

        # Paste circular cropped profile picture
        paste_x = center_x - member_pfp.width // 2
        paste_y = center_y - member_pfp.height // 2
        mask = Image.new('L', (member_pfp.width, member_pfp.height), 0)
        draw_mask = ImageDraw.Draw(mask)
        draw_mask.ellipse((0, 0, member_pfp.width, member_pfp.height), fill=255)
        member_pfp.putalpha(mask)
        background_image.paste(member_pfp, (paste_x, paste_y), member_pfp)

        # Draw welcome text
        text1 = f"{member} has joined! (#{member_count})"
        text2 = f"Welcome to {member.guild.name}, and enjoy your stay!"
        draw = ImageDraw.Draw(background_image)
        _, _, text1_width, _ = draw.textbbox((0, 0), text1, font=font_title)
        _, _, text2_width, _ = draw.textbbox((0, 0), text2, font=font_footer)
        center_x1 = (image_width - text1_width) // 2
        center_x2 = (image_width - text2_width) // 2
        draw.text((center_x1, 10), text1, (255, 255, 255), font=font_title)
        draw.text((center_x2, 165), text2, (255, 255, 255), font=font_footer)

        # Save the welcome image
        os.makedirs("./assets/outputs", exist_ok=True)
        background_image.save("./assets/outputs/welcome.png")

        # Auto-role assignment
        role = member.guild.get_role(member_role_id)
        autoRole = discord.utils.get(member.guild.roles, name=str(role))

        # Send to welcome channel
        channel = self.client.get_channel(welcome_channel_id)
        file = discord.File("./assets/outputs/welcome.png")
        embed = discord.Embed(
            description=f"Welcome to {member.guild.name}, {member.mention}!",
            colour=embed_color
        )
        embed.set_image(url="attachment://welcome.png")

        # DM to new member
        title = join_dm_template["title"].format(
            guild_name=member.guild.name,
            member=member,
            member_count=member_count
        )
        description = join_dm_template["description"].format(
            guild_name=member.guild.name,
            member_mention=member.mention,
            member_name=member.name
        )
        footer_text = join_dm_template["footer_text"].format(
            guild_name=member.guild.name
        )
        embed2 = discord.Embed(
            title=title,
            description=description,
            colour=embed_color
        )
        # Fixed: use datetime.datetime.now() instead of datetime.datetime.datetime.now()
        embed2.timestamp = datetime.datetime.now()
        embed2.set_footer(text=footer_text, icon_url=member.guild.icon.url)
        try:
            await member.send(embed=embed2)
        except:
            pass

        # Ping & purge in verification channel
        verif_chan = self.client.get_channel(1377177401540218930)
        if verif_chan:
            await verif_chan.send(f"{member.mention}")
            await verif_chan.purge(limit=1)

        # Send welcome image and embed
        await channel.send(f"||{member.mention}||")
        await channel.purge(limit=1)
        await channel.send(file=file, embed=embed)
        await member.add_roles(autoRole)

    # Remove user from verified_user_data.json when they leave
    @commands.Cog.listener()
    async def on_member_remove(self, member):
        # Log leave in logs_channel_id
        channel = self.client.get_channel(logs_channel_id)
        embed = discord.Embed(
            title=f"🚪 | {member.display_name} has left the server.",
            description=f"{member.mention} aka `{member.name}` has left {member.guild.name}.",
            colour=embed_color
        )
        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)
        else:
            embed.set_thumbnail(url=member.guild.icon.url)
        await channel.send(embed=embed)

        # Remove from verified_user_data.json
        if os.path.exists(VERIFIED_USER_FILE):
            try:
                with open(VERIFIED_USER_FILE, "r") as vf:
                    verifs = json.load(vf)
            except json.JSONDecodeError:
                verifs = {}
            user_id_str = str(member.id)
            if user_id_str in verifs:
                del verifs[user_id_str]
                with open(VERIFIED_USER_FILE, "w") as vf:
                    json.dump(verifs, vf, indent=2)

    # Log deleted messages
    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.guild.me.guild_permissions.view_audit_log:
            async for entry in message.guild.audit_logs(limit=1, action=discord.AuditLogAction.message_delete):
                deleter = entry.user
                if message.author.id != self.client.user.id:
                    channel = self.client.get_channel(logs_channel_id)
                    embed = discord.Embed(
                        title=f"🗑️ | A message was deleted in #{message.channel.name}",
                        description=f"**Message deleted:** ```{message.content}```",
                        colour=embed_color
                    )
                    if deleter.avatar:
                        embed.set_author(name=f"{deleter.name} ({deleter.display_name})", icon_url=deleter.avatar.url)
                    else:
                        embed.set_author(name=f"{deleter.name} ({deleter.display_name})")
                    embed.add_field(name="Message Author", value=message.author.mention, inline=True)
                    embed.add_field(name="Author Name", value=message.author.name, inline=True)
                    embed.add_field(name="Author ID", value=message.author.id, inline=True)
                    embed.add_field(name="Deleter", value=deleter.mention, inline=True)
                    embed.add_field(name="Deleter Name", value=deleter.name, inline=True)
                    embed.add_field(name="Deleter ID", value=deleter.id, inline=True)
                    await channel.send(embed=embed)

    # Log edited messages
    @commands.Cog.listener()
    async def on_message_edit(self, message_before, message_after):
        if not message_before.author.bot:
            embed = discord.Embed(
                title=f"✂️ | A message was edited in #{message_before.channel.name}",
                description=(
                    f"**Old Message:**\n```{message_before.content}```\n"
                    f"**New Message:**\n```{message_after.content}```"
                ),
                color=embed_color
            )
            embed.set_author(
                name=f"{message_before.author.name} ({message_before.author.display_name})",
                icon_url=message_before.author.avatar.url
            )
            embed.add_field(name="Message Author", value=message_before.author.mention, inline=True)
            embed.add_field(name="Author Name", value=message_before.author.name, inline=True)
            embed.add_field(name="Author ID", value=message_before.author.id, inline=True)
            channel = self.client.get_channel(logs_channel_id)
            await channel.send(embed=embed)


async def setup(client):
    await client.add_cog(joinleave(client))
