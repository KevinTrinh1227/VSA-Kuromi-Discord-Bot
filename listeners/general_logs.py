import discord
from discord.ext import commands
import discord.ui
import datetime
import json
from PIL import Image, ImageFont, ImageDraw
from io import BytesIO
import requests
import os
from utils.pillow import create_welcome_image
from utils.users_utils import get_verified_users, save_verified_users, get_unverified_users, save_unverified_users
from utils.nickname_and_roles import rename_user, assign_roles

# Open the JSON file and read in the data
with open('config.json') as json_file:
    data = json.load(json_file)

# Load the "join_dm_message" template
join_dm_template = data["embed_templates"]["join_dm_message"]

VSA_FAMILY_NAME = data["general"]["family_name"]
# Bot configuration
bot_prefix = data["general"]["bot_prefix"]
embed_color = int(data["general"]["embed_color"].strip("#"), 16)
member_role_id = int(data["role_ids"]["unverified_vsa_member"])
welcome_channel_id = int(data["text_channel_ids"]["welcome"])
pre_embed_color = data["general"]["embed_color"].strip("#")
logs_channel_id = int(data["text_channel_ids"]["bot_logs"])
VERIFICATION_CHANNEL_ID = int(data["text_channel_ids"]["verification"])


class joinleave(commands.Cog):
    def __init__(self, client):
        self.client = client

    # Helper function to calculate time difference nicely
    def format_time_diff(self, earlier: datetime.datetime, later: datetime.datetime):
        diff = later - earlier
        days = diff.days
        seconds = diff.seconds
        weeks = days // 7
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return weeks, days, hours, minutes

    @commands.Cog.listener()
    async def on_member_join(self, member):
        verified_users = get_verified_users()  # returns dict, keys are user id strings
        user_id_str = str(member.id)

        if user_id_str in verified_users:
            user_data = verified_users[user_id_str]
            discord_profile = user_data.get("discord_profile", {})
            saved_roles = discord_profile.get("roles", [])
            saved_nick = discord_profile.get("nickname", "")
            users_curr_points = 0
            first_join_str = discord_profile.get("first_time_joined", None)
            
            user_general = user_data.get("general")
            first_name = user_general.get("first_name", "")
            last_name = user_general.get("last_name", "")

            # Convert first join timestamp string to datetime object
            first_join_time = None
            if first_join_str:
                try:
                    first_join_time = datetime.datetime.fromisoformat(first_join_str.replace("Z", "+00:00"))
                except Exception:
                    first_join_time = None

            # 1) Rename user if different nickname
            old_nick = member.display_name
            await rename_user(member, user_id_str, users_curr_points, first_name, last_name)
            new_nick = member.display_name  # might have changed after rename_user

            # 2) Assign saved roles (only add)
            await assign_roles(member, saved_roles)
            # Remove roles that the user currently has but are NOT in saved roles (except @everyone)
            current_roles = set(role.id for role in member.roles if role != member.guild.default_role)
            saved_role_ids = set(int(rid) for rid in saved_roles)

            roles_to_remove = [
                member.guild.get_role(rid)
                for rid in current_roles - saved_role_ids
                if member.guild.get_role(rid)
            ]

            if roles_to_remove:
                try:
                    await member.remove_roles(*roles_to_remove, reason="Removing roles not in saved data on rejoin")
                except discord.Forbidden:
                    print(f"Missing permissions to remove some roles from {member.display_name}")
                except Exception as e:
                    print(f"Unexpected error removing roles from {member.display_name}: {e}")


            # 3) Remove roles that user currently has but are NOT in saved roles (except @everyone)
            current_roles = set(role.id for role in member.roles if role != member.guild.default_role)
            saved_role_ids = set(int(rid) for rid in saved_roles)
            roles_to_remove = [member.guild.get_role(rid) for rid in current_roles - saved_role_ids if member.guild.get_role(rid)]
            if roles_to_remove:
                try:
                    await member.remove_roles(*roles_to_remove, reason="Removing roles not in saved data on rejoin")
                except discord.Forbidden:
                    pass

            # 4) Prepare embed for bot logs channel
            now_time = datetime.datetime.now(datetime.timezone.utc)

            # Format time difference if first_join_time is known
            if first_join_time:
                weeks, days, hours, minutes = self.format_time_diff(first_join_time, now_time)
                diff_str = f"{weeks} weeks, {days} days, {hours} hours, {minutes} minutes"
            else:
                diff_str = "Unknown"

            # Compare old and new nicknames for embed field
            nick_changed = old_nick != new_nick
            nick_field = f"{old_nick} → {new_nick}" if nick_changed else f"{old_nick} (no change)"
            
            
            # Compare roles for embed field
            # old roles mentions
            old_roles_mentions = [f"<@&{role.id}>" for role in member.roles if role.id in current_roles]

            saved_roles_mentions = []
            for rid in saved_role_ids:
                role = member.guild.get_role(rid)
                if role:
                    saved_roles_mentions.append(f"<@&{role.id}>")

            roles_changed = set(old_roles_mentions) != set(saved_roles_mentions)
            roles_field = (
                f"{', '.join(old_roles_mentions)} → {', '.join(saved_roles_mentions)}"
                if roles_changed else
                ", ".join(saved_roles_mentions)
            )


            embed = discord.Embed(
                title="🔄 | User Rejoined and Restored",
                colour=embed_color,
                timestamp=now_time
            )
            embed.add_field(name="User", value=f"{member.mention} (`{member}`)", inline=False)
            embed.add_field(name="First Joined", value=first_join_str or "Unknown", inline=True)
            embed.add_field(name="Rejoined", value=now_time.isoformat(), inline=True)
            embed.add_field(name="Time Gone", value=diff_str, inline=False)
            embed.add_field(name="Nickname", value=nick_field, inline=False)
            embed.add_field(name="Roles", value=roles_field, inline=False)

            logs_channel = self.client.get_channel(logs_channel_id)
            if logs_channel:
                await logs_channel.send(embed=embed)

        else:
            # Not in verified users, run original join flow below

            member_count = len(member.guild.members)

            # Create the welcome image using your utility function
            welcome_image_path = create_welcome_image(member, member_count, VSA_FAMILY_NAME)

            # Auto-role assignment
            role = member.guild.get_role(member_role_id)
            autoRole = discord.utils.get(member.guild.roles, name=str(role))

            # Send to welcome channel
            channel = self.client.get_channel(welcome_channel_id)
            file = discord.File(welcome_image_path)
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
            embed2.timestamp = datetime.datetime.now()
            embed2.set_footer(text=footer_text, icon_url=member.guild.icon.url)
            try:
                await member.send(embed=embed2)
            except:
                pass

            # Ping & purge in verification channel
            verif_chan = self.client.get_channel(VERIFICATION_CHANNEL_ID)
            if verif_chan:
                await verif_chan.send(f"{member.mention}")
                await verif_chan.purge(limit=1)

            # Send welcome image and embed
            await channel.send(f"||{member.mention}||")
            await channel.purge(limit=1)
            await channel.send(file=file, embed=embed)
            await member.add_roles(autoRole)
            
            # If user is not in verified data, track them as unverified
            if member.joined_at and member.created_at and (member.joined_at - member.created_at).total_seconds() > 60:
                now_time = datetime.datetime.now(datetime.timezone.utc)
                user_id_str = str(member.id)
                unverified_users = get_unverified_users()

                # Default values
                first_join = now_time
                left_at = None
                diff_str = "N/A"

                # If user existed in unverified data, pull timestamps
                if user_id_str in unverified_users:
                    profile = unverified_users[user_id_str]["discord_profile"]
                    first_join_str = profile.get("first_time_joined")
                    left_str = profile.get("user_left_timestamp")

                    if first_join_str:
                        try:
                            first_join = datetime.datetime.fromisoformat(first_join_str)
                        except:
                            pass
                    if left_str:
                        try:
                            left_at = datetime.datetime.fromisoformat(left_str)
                            diff = now_time - left_at
                            total_seconds = int(diff.total_seconds())

                            weeks = total_seconds // (7 * 24 * 3600)
                            days = (total_seconds % (7 * 24 * 3600)) // (24 * 3600)
                            hours = (total_seconds % (24 * 3600)) // 3600
                            minutes = (total_seconds % 3600) // 60
                            seconds = total_seconds % 60

                            diff_str = f"{weeks}w {days}d {hours}h {minutes}m {seconds}s"
                        except:
                            pass

                    # Build embed
                    embed = discord.Embed(
                        title="⚠️ | User Rejoined But Not Verified",
                        description=f"{member.mention} (`{member}`) rejoined the server but is not in verified data.",
                        colour=discord.Colour.orange(),
                        timestamp=now_time
                    )
                    embed.add_field(name="First Joined", value=first_join.isoformat(), inline=True)
                    embed.add_field(name="Last Left", value=left_at.isoformat() if left_at else "N/A", inline=True)
                    embed.add_field(name="Rejoined At", value=now_time.isoformat(), inline=True)
                    embed.add_field(name="Time Gone", value=diff_str, inline=False)

                    logs_channel = self.client.get_channel(logs_channel_id)
                    if logs_channel:
                        await logs_channel.send(embed=embed)

                    # Save or update unverified user entry
                    if user_id_str in unverified_users:
                        unverified_users[user_id_str] = {
                            "discord_profile": {
                                "discord_name": str(member),
                                "nickname": member.nick,
                                "first_time_joined": first_join.isoformat(),
                                "user_left_timestamp": None
                            }
                        }
                    else:
                        # Clear left timestamp now that they're back
                        unverified_users[user_id_str]["discord_profile"]["user_left_timestamp"] = None
                        unverified_users[user_id_str]["discord_profile"]["nickname"] = member.nick
                        unverified_users[user_id_str]["discord_profile"]["discord_name"] = str(member)

                save_unverified_users(unverified_users)



    # Remove user from verified_user_data.json when they leave
    @commands.Cog.listener()
    async def on_member_remove(self, member):
        now_time = datetime.datetime.now(datetime.timezone.utc).isoformat()
        user_id_str = str(member.id)

        # Attempt to update verified users
        verified_users = get_verified_users()
        if user_id_str in verified_users:
            verified_users[user_id_str]["discord_profile"]["user_left_timestamp"] = now_time
            verified_users[user_id_str]["discord_profile"]["still_in_server"] = False
            verified_users[user_id_str]["discord_profile"]["last_updated"] = now_time
            save_verified_users(verified_users)

            embed = discord.Embed(
                title=f"🚪 | Verified User Left",
                description=f"{member.mention} (`{member}`) has left the server.\n**Status:** Verified\n**Left at:** {now_time}",
                colour=discord.Colour.red()
            )

        else:
            # Attempt to update unverified users
            unverified_users = get_unverified_users()
            if user_id_str in unverified_users:
                unverified_users[user_id_str]["discord_profile"]["user_left_timestamp"] = now_time
                save_unverified_users(unverified_users)

                embed = discord.Embed(
                    title=f"🚪 | Unverified User Left",
                    description=f"{member.mention} (`{member}`) has left the server.\n**Status:** Unverified\n**Left at:** {now_time}",
                    colour=discord.Colour.orange()
                )
            else:
                # User not tracked at all
                embed = discord.Embed(
                    title=f"🚪 | Unknown User Left",
                    description=f"{member.mention} (`{member}`) has left the server.\n**Status:** Not Found in Records\n**Left at:** {now_time}",
                    colour=discord.Colour.greyple()
                )

        if member.avatar:
            embed.set_thumbnail(url=member.avatar.url)
        else:
            embed.set_thumbnail(url=member.guild.icon.url)

        channel = self.client.get_channel(logs_channel_id)
        if channel:
            await channel.send(embed=embed)


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
