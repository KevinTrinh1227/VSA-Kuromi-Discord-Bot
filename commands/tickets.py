import discord
from discord.ext import commands
from discord.ui import Button, View
import datetime
import json
import asyncio
import io
import chat_exporter  # 

# Load config.json
with open('config.json') as json_file:
    data = json.load(json_file)

embed_color = int(data["general"]["embed_color"].strip("#"), 16)
bot_prefix = data["general"]["bot_prefix"]

category_id        = int(data["category_ids"]["tickets_category"])
staff_role_id      = int(data["role_ids"]["staff_member"])
transcript_chan_id = int(data["text_channel_ids"]["tickets_transcripts"])
bot_logs_id        = int(data["text_channel_ids"]["bot_logs"])

# Ticket menu template
ticket_types    = data["embed_templates"]["ticket_system"]["ticket_type_list"]
ticket_template = data["embed_templates"]["ticket_system"]

class Roles(View):
    def __init__(self):
        super().__init__(timeout=None)
        for t in ticket_types:
            btn = Button(
                label=t["button_label"],
                style=discord.ButtonStyle.secondary,
                custom_id=t["ticket_type"],
                emoji=t["ticket_type_emoji"]
            )
            btn.callback = self.button_callback
            self.add_item(btn)

    async def button_callback(self, interaction: discord.Interaction):
        guild        = interaction.guild
        category     = guild.get_channel(category_id)
        staff_role   = guild.get_role(staff_role_id)
        user         = interaction.user
        choice       = interaction.data["custom_id"]

        # find matching emoji for channel name
        emoji = next((t["ticket_type_emoji"] for t in ticket_types if t["ticket_type"] == choice), "")

        # check if user already has open ticket
        for ch in category.channels:
            if ch.name.startswith(f"ticket-{user.name}-"):
                embed = discord.Embed(
                    title=ticket_template["title"],
                    description=(
                        f"You already have an open ticket. To access it: <#{ch.id}>\n\n"
                        "Please be patient with our staff and remember only one ticket at a time."
                    ),
                    color=embed_color
                )
                embed.timestamp = datetime.datetime.now()
                if guild.icon:
                    embed.set_footer(
                        text=ticket_template["footer_text"].format(guild_name=guild.name),
                        icon_url=guild.icon.url
                    )
                else:
                    embed.set_footer(
                        text=ticket_template["footer_text"].format(guild_name=guild.name)
                    )
                await user.send(embed=embed)
                # log warning
                log = discord.Embed(
                    title=f"{ticket_template['title']} - Duplicate Attempt",
                    description=f"{user.mention} tried opening another ticket.",
                    color=embed_color
                )
                log.timestamp = datetime.datetime.now()
                if guild.icon:
                    log.set_footer(text=f"©️ {guild.name}", icon_url=guild.icon.url)
                await guild.get_channel(bot_logs_id).send(embed=log)
                return

        # create new ticket channel
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            staff_role:          discord.PermissionOverwrite(read_messages=True, send_messages=True),
            user:                discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        ch = await category.create_text_channel(f"ticket-{user.name}-{emoji}", overwrites=overwrites)

        # mention staff + user in channel
        await ch.send(f"{staff_role.mention} {user.mention}")

        # initial embed in ticket
        embed = discord.Embed(
            title=f"{choice} Ticket",
            description=(
                "Please describe your issue clearly and a staff member will assist you shortly.\n\n"
                f"Ticket Issuer: {user.mention}\n"
                "Use `/closeticket` to close this ticket."
            ),
            color=embed_color
        )
        embed.timestamp = datetime.datetime.now()
        if user.avatar:
            embed.set_author(name=f"Requested by {user}", icon_url=user.avatar.url)
        else:
            embed.set_author(name=f"Requested by {user}")
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
            embed.set_footer(text=f"©️ {guild.name}", icon_url=guild.icon.url)
        else:
            embed.set_footer(text=f"©️ {guild.name}")
        await ch.send(embed=embed)
        await interaction.response.defer()


class Ticket(commands.Cog):
    def __init__(self, client):
        self.client = client
        self.client.add_view(Roles())

    @commands.has_permissions(administrator=True)
    @commands.hybrid_command(aliases=["ticket"], brief="ticket",
                             description="Sends a ticket menu", with_app_command=True)
    async def tickets(self, ctx):
        embed = discord.Embed(
            title=ticket_template["title"],
            description=ticket_template["description"].replace("{guild_name}", ctx.guild.name),
            color=embed_color
        )
        embed.timestamp = datetime.datetime.now()
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
            embed.set_footer(
                text=ticket_template["footer_text"].format(guild_name=ctx.guild.name),
                icon_url=ctx.guild.icon.url
            )
        else:
            embed.set_footer(
                text=ticket_template["footer_text"].format(guild_name=ctx.guild.name)
            )
        await ctx.send(embed=embed, view=Roles())

    @commands.hybrid_command(aliases=["close"], brief="closeticket",
                             description="Closes the current ticket", with_app_command=True)
    async def closeticket(self, ctx):
        if not ctx.channel.name.startswith("ticket-"):
            return

        # confirmation embed (only the user who ran /closeticket can click)
        confirm = discord.Embed(
            title="🎟️ | Confirmation",
            description=(
                "Click the button below to close this ticket. "
                "Only the user who ran `/closeticket` can close it."
            ),
            color=embed_color
        )
        confirm.timestamp = datetime.datetime.now()
        if ctx.guild.icon:
            confirm.set_footer(text=f"©️ {ctx.guild.name}", icon_url=ctx.guild.icon.url)
        else:
            confirm.set_footer(text=f"©️ {ctx.guild.name}")

        button = Button(label="Close Ticket", style=discord.ButtonStyle.red)
        async def cb(inter: discord.Interaction):
            if inter.user == ctx.author:
                await inter.response.defer()  # acknowledge so “This interaction failed” won’t appear
            else:
                await inter.response.send_message("Not authorized.", ephemeral=True)
        button.callback = cb

        view = View()
        view.add_item(button)
        msg = await ctx.send(embed=confirm, view=view)

        try:
            await self.client.wait_for(
                "interaction",
                timeout=30.0,
                check=lambda i: i.message.id == msg.id and i.user == ctx.author
            )
        except asyncio.TimeoutError:
            await ctx.send("Timed out, ticket not closed.")
            return

        # ── EXPORT THE HTML AS A DOWNLOADABLE FILE ──
        transcript_html = await chat_exporter.export(ctx.channel)
        if transcript_html:
            fp = io.BytesIO(transcript_html.encode("utf-8"))
            file_transcript = discord.File(fp, filename=f"transcript-{ctx.channel.name}.html")
        else:
            file_transcript = None

        # identify user
        parts = ctx.channel.name.split("-")
        username = parts[1]
        user = discord.utils.get(ctx.guild.members, name=username)
        user_id = user.id if user else None

        # ── ATTEMPT TO DM THE USER & TRACK SUCCESS ──
        dm_success = False
        if user and transcript_html:
            dm_embed = discord.Embed(
                title=f"🎟️ | {username}'s Ticket Transcript",
                description="Here is your ticket transcript (attached below). Please save it if needed.",
                color=embed_color
            )
            dm_embed.timestamp = datetime.datetime.now()
            if ctx.guild.icon:
                dm_embed.set_footer(text=f"©️ {ctx.guild.name}", icon_url=ctx.guild.icon.url)
            try:
                await user.send(embed=dm_embed)
                fp3 = io.BytesIO(transcript_html.encode("utf-8"))
                dm_file = discord.File(fp3, filename=f"transcript-{ctx.channel.name}.html")
                await user.send(file=dm_file)
                dm_success = True
            except discord.Forbidden:
                dm_success = False

        # ── SEND TO TRANSCRIPTS CHANNEL (embed + file) ──
        tc_transcripts = self.client.get_channel(transcript_chan_id)
        if transcript_html:
            if user:
                user_tag = f"<@{user_id}>"
                username_only = user.name
            else:
                user_tag = "Unknown User"
                username_only = "Unknown"

            # Choose status text based on DM success
            if dm_success:
                dm_status_text = "DM successfully sent! 🟢"
            else:
                dm_status_text = "User's DMs are closed! 🔴"

            embed = discord.Embed(
                title=f"🎟️ | {ctx.channel.name} Closed",
                description=(
                    f"Issuer ID: `{user_id}`\n"
                    f"Issuer: {user_tag} ({username_only})\n"
                    f"Transcript was sent to issuer: {dm_status_text}\n\n"
                    f"{ctx.channel.name} transcript download below."
                ),
                color=embed_color
            )
            embed.timestamp = datetime.datetime.now()
            if user and user.avatar:
                embed.set_thumbnail(url=user.avatar.url)
            embed.set_footer(text=f"©️ {ctx.guild.name}")
            await tc_transcripts.send(embed=embed)

            # Attach the transcript file
            await tc_transcripts.send(file=file_transcript)
        else:
            if user:
                await tc_transcripts.send(
                    f"<@{user_id}> ({user.name})'s DMs are closed; transcript not delivered."
                )
            else:
                await tc_transcripts.send("Transcript generation failed; user not found.")

        # notify ticket channel
        close_embed = discord.Embed(
            title="🎟️ | Closed | This ticket is now locked",
            description=(
                "Your support ticket is now locked. A transcript copy has been recorded.\n"
                "This channel will be deleted in 1 minute."
            ),
            color=embed_color
        )
        close_embed.timestamp = datetime.datetime.now()
        if ctx.guild.icon:
            close_embed.set_footer(text=f"©️ {ctx.guild.name}", icon_url=ctx.guild.icon.url)
        await ctx.send(embed=close_embed)

        await asyncio.sleep(60)
        await ctx.channel.delete()



async def setup(client):
    await client.add_cog(Ticket(client))
