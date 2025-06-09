import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from datetime import datetime
from typing import Optional


# Helper functions for loading and saving JSON data
def load_json(path):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def utcnow():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")

class Punishments(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.users_db_path = "users_database.json"
        self.config_path = "config.json"
        self.users_db = load_json(self.users_db_path)
        self.config = load_json(self.config_path)
        self.guild_id = int(self.config.get("general", {}).get("discord_server_guild_id", 0))
        self.bot_prefix = self.config.get("general", {}).get("bot_prefix", "!")
        self.embed_color = int(self.config.get("general", {}).get("embed_color", "#55ff55").strip("#"), 16)
        self.logs_channel_id = int(self.config.get("text_channel_ids", {}).get("bot_logs", 0))

    async def cog_load(self):
        # Reload JSON periodically or add a command to reload if needed
        self.users_db = load_json(self.users_db_path)
        self.config = load_json(self.config_path)

    # Utility: get guild object
    def get_guild(self):
        return self.bot.get_guild(self.guild_id)

    # Utility: format datetime string with fallback
    def parse_datetime(self, dt_str):
        try:
            return datetime.fromisoformat(dt_str)
        except Exception:
            return None

    # Utility: Build footer with server icon, name, timestamp
    def embed_footer(self, embed):
        guild = self.get_guild()
        if guild:
            embed.set_footer(
                text=f"{guild.name} | {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
                icon_url=guild.icon.url if guild.icon else None,
            )

    # Utility: get user profile data and punishments safely
    def get_user_data(self, user_id: int):
        user_id_str = str(user_id)
        user_data = self.users_db.get(user_id_str, {})
        punishments = user_data.get("punishments", {})
        return user_data, punishments

    # --- COMMAND: Show all punishments for a user ---
    @commands.hybrid_command(name="punishments", with_app_command=True, description="Show all punishments for a user")
    @commands.guild_only()
    async def punishments(self, ctx: commands.Context, user: Optional[discord.Member] = None):
        """Show all punishments for a user. Defaults to invoking user."""
        user = user or ctx.author
        user_data, punishments = self.get_user_data(user.id)

        if not punishments:
            await ctx.send(f"No punishments found for {user.display_name}.")
            return

        embed = discord.Embed(
            title=f"⚖️ | Punishments for {user.display_name}",
            color=self.embed_color,
            timestamp=datetime.utcnow(),
        )

        # Add author as user avatar
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)

        # Add each punishment category
        def format_entry(entry):
            lines = []
            date = entry.get("date_time_cst") or entry.get("date_time") or "Unknown date"
            reason = entry.get("reason", "No reason provided")
            issued_by = entry.get("issued_by_nickname") or entry.get("issued_by_username") or "Unknown staff"
            notes = entry.get("notes", "")
            extra = ""

            if "duration_seconds" in entry:
                dur = entry["duration_seconds"]
                extra = f"Duration: {dur//60} minutes" if dur else ""
            if "duration_minutes" in entry:
                dur = entry["duration_minutes"]
                extra = f"Duration: {dur} minutes" if dur else ""

            pardoned = entry.get("pardoned")
            if pardoned:
                pardon_by = pardoned.get("pardoned_by_nickname") or pardoned.get("pardoned_by_username", "Unknown")
                pardon_date = pardoned.get("date_time_cst", "Unknown")
                pardon_reason = pardoned.get("reason", "No reason")
                extra += f"\nPardoned by {pardon_by} on {pardon_date} Reason: {pardon_reason}"

            notes_str = f"\nNotes: {notes}" if notes else ""
            return f"**Date:** {date}\n**Reason:** {reason}\n**Issued by:** {issued_by}\n{extra}{notes_str}"

        # Categories to display and order
        categories = [
            ("Mutes", "mutes"),
            ("Warnings", "warnings"),
            ("Kicks", "kicks"),
            ("Bans", "bans"),
            ("Notes", "notes"),
        ]

        for display_name, key in categories:
            data = punishments.get(key)
            if data:
                if key == "notes":
                    # Notes is a list of strings
                    if len(data) == 0:
                        continue
                    notes_str = "\n".join(f"- {note}" for note in data)
                    embed.add_field(name=f"📝 {display_name}", value=notes_str[:1024], inline=False)
                else:
                    # List of dict punishments
                    if len(data) == 0:
                        continue
                    value = ""
                    for entry in data:
                        value += format_entry(entry) + "\n\n"
                    embed.add_field(name=f"🛑 {display_name}", value=value[:1024], inline=False)

        self.embed_footer(embed)
        await ctx.send(embed=embed)

    # --- COMMAND: Warn a user ---
    @commands.hybrid_command(name="warn", with_app_command=True, description="Warn a user with a reason")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def warn(self, ctx: commands.Context, user: discord.Member, *, reason: str):
        """Warn a user with a reason."""
        await self.add_punishment(ctx, user, "warnings", reason, ctx.author)
        await ctx.send(f"Warned {user.mention} for: {reason}")

    # --- COMMAND: Mute a user ---
    @commands.hybrid_command(name="mute", with_app_command=True, description="Mute a user for a duration (seconds)")
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def mute(self, ctx: commands.Context, user: discord.Member, duration_seconds: int, *, reason: str):
        """Mute a user for a certain duration in seconds."""
        # Check for Muted role or create it
        guild = ctx.guild
        muted_role = discord.utils.get(guild.roles, name="Muted")
        if not muted_role:
            try:
                muted_role = await guild.create_role(name="Muted", reason="For muting users")
                # Deny send messages in all text channels for Muted role
                for channel in guild.channels:
                    try:
                        await channel.set_permissions(muted_role, send_messages=False, speak=False)
                    except Exception:
                        pass
            except Exception as e:
                await ctx.send(f"Failed to create Muted role: {e}")
                return

        # Assign muted role
        await user.add_roles(muted_role, reason=reason)

        await self.add_punishment(ctx, user, "mutes", reason, ctx.author, duration_seconds=duration_seconds)
        await ctx.send(f"Muted {user.mention} for {duration_seconds} seconds. Reason: {reason}")

    # --- COMMAND: Unmute user ---
    @commands.hybrid_command(name="unmute", with_app_command=True, description="Unmute a user")
    @commands.has_permissions(moderate_members=True)
    @commands.guild_only()
    async def unmute(self, ctx: commands.Context, user: discord.Member):
        """Unmute a user by removing the Muted role."""
        guild = ctx.guild
        muted_role = discord.utils.get(guild.roles, name="Muted")
        if muted_role and muted_role in user.roles:
            await user.remove_roles(muted_role, reason=f"Unmuted by {ctx.author}")
            await ctx.send(f"Unmuted {user.mention}.")
            # Optionally add an unmute note or punishment history entry?
            await self.add_punishment(ctx, user, "notes", f"Unmuted by {ctx.author}", ctx.author)
        else:
            await ctx.send(f"{user.mention} is not muted.")

    # --- COMMAND: Kick user ---
    @commands.hybrid_command(name="kick", with_app_command=True, description="Kick a user from the server")
    @commands.has_permissions(kick_members=True)
    @commands.guild_only()
    async def kick(self, ctx: commands.Context, user: discord.Member, *, reason: str):
        """Kick a user from the server with a reason."""
        try:
            await user.kick(reason=reason)
        except Exception as e:
            await ctx.send(f"Failed to kick user: {e}")
            return
        await self.add_punishment(ctx, user, "kicks", reason, ctx.author)
        await ctx.send(f"Kicked {user.mention} from the server. Reason: {reason}")

    # --- COMMAND: Ban user ---
    @commands.hybrid_command(name="ban", with_app_command=True, description="Ban a user from the server")
    @commands.has_permissions(ban_members=True)
    @commands.guild_only()
    async def ban(self, ctx: commands.Context, user: discord.Member, duration_minutes: Optional[int] = None, *, reason: str = "No reason provided"):
        """Ban a user from the server, optionally with a duration in minutes."""
        try:
            await user.ban(reason=reason)
        except Exception as e:
            await ctx.send(f"Failed to ban user: {e}")
            return
        # Save ban with duration if provided
        await self.add_punishment(ctx, user, "bans", reason, ctx.author, duration_minutes=duration_minutes)
        await ctx.send(f"Banned {user.mention}. Reason: {reason} Duration: {duration_minutes if duration_minutes else 'Indefinite'} minutes")

    # --- COMMAND: Unban user ---
    @commands.hybrid_command(name="unban", with_app_command=True, description="Unban a user by username#discriminator")
    @commands.has_permissions(ban_members=True)
    @commands.guild_only()
    async def unban(self, ctx: commands.Context, user_name: str):
        """Unban a user by their username#discriminator."""
        banned_users = await ctx.guild.bans()
        user_name_lower = user_name.lower()
        user_to_unban = None
        for ban_entry in banned_users:
            user = ban_entry.user
            full_name = f"{user.name}#{user.discriminator}".lower()
            if full_name == user_name_lower:
                user_to_unban = user
                break
        if user_to_unban:
            try:
                await ctx.guild.unban(user_to_unban)
            except Exception as e:
                await ctx.send(f"Failed to unban user: {e}")
                return
            await ctx.send(f"Unbanned {user_to_unban.mention}.")
            # Optionally add unban note
            await self.add_punishment(ctx, user_to_unban, "notes", f"Unbanned by {ctx.author}", ctx.author)
        else:
            await ctx.send("User not found in ban list.")

    # --- COMMAND: Edit a note on a punishment ---
    @commands.hybrid_command(name="editnote", with_app_command=True, description="Edit a note on a user's punishment")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def editnote(self, ctx: commands.Context, user: discord.Member, category: str, punishment_number: int, *, new_note: str):
        """
        Edit a note on a punishment.
        category: mutes, warnings, kicks, bans, notes
        punishment_number: integer punishment index (1-based)
        """
        category = category.lower()
        user_data, punishments = self.get_user_data(user.id)
        if not punishments or category not in punishments:
            await ctx.send(f"No punishments found in category `{category}` for {user.display_name}.")
            return

        if category == "notes":
            # For notes, punishment_number is index in list
            notes_list = punishments["notes"]
            if punishment_number < 1 or punishment_number > len(notes_list):
                await ctx.send(f"Note number {punishment_number} is out of range.")
                return
            notes_list[punishment_number - 1] = new_note
        else:
            # List of punishment dicts
            entries = punishments[category]
            if punishment_number < 1 or punishment_number > len(entries):
                await ctx.send(f"Punishment number {punishment_number} is out of range.")
                return
            entries[punishment_number - 1]["notes"] = new_note

        # Save
        self.users_db[str(user.id)]["punishments"] = punishments
        save_json(self.users_db_path, self.users_db)
        await ctx.send(f"Updated note on {category} #{punishment_number} for {user.display_name}.")

    # --- COMMAND: Remove a punishment entry ---
    @commands.hybrid_command(name="removepunishment", with_app_command=True, description="Remove a punishment from a user")
    @commands.has_permissions(manage_messages=True)
    @commands.guild_only()
    async def removepunishment(self, ctx: commands.Context, user: discord.Member, category: str, punishment_number: int):
        """
        Remove a punishment entry by category and number.
        category: mutes, warnings, kicks, bans, notes
        punishment_number: integer index (1-based)
        """
        category = category.lower()
        user_data, punishments = self.get_user_data(user.id)
        if not punishments or category not in punishments:
            await ctx.send(f"No punishments found in category `{category}` for {user.display_name}.")
            return

        if category == "notes":
            notes_list = punishments["notes"]
            if punishment_number < 1 or punishment_number > len(notes_list):
                await ctx.send(f"Note number {punishment_number} is out of range.")
                return
            removed = notes_list.pop(punishment_number - 1)
            msg = f"Removed note: {removed}"
        else:
            entries = punishments[category]
            if punishment_number < 1 or punishment_number > len(entries):
                await ctx.send(f"Punishment number {punishment_number} is out of range.")
                return
            removed = entries.pop(punishment_number - 1)
            msg = f"Removed punishment: Reason `{removed.get('reason', 'No reason')}`"

        # Save changes
        if len(punishments.get(category, [])) == 0:
            punishments.pop(category)
        self.users_db[str(user.id)]["punishments"] = punishments
        save_json(self.users_db_path, self.users_db)

        await ctx.send(msg)

    # --- INTERNAL: Add a punishment helper ---
    async def add_punishment(self, ctx, user: discord.Member, category: str, reason: str, issued_by: discord.Member,
                             duration_seconds: Optional[int] = None, duration_minutes: Optional[int] = None):
        user_id_str = str(user.id)
        if user_id_str not in self.users_db:
            # Create user entry skeleton
            self.users_db[user_id_str] = {
                "general": {"first_name": user.name, "last_name": "", "timestamp": utcnow()},
                "discord_profile": {"nickname": user.display_name, "roles": [str(r.id) for r in user.roles], "first_time_joined": utcnow(), "last_updated": utcnow(), "still_in_server": True},
                "punishments": {}
            }
        if "punishments" not in self.users_db[user_id_str]:
            self.users_db[user_id_str]["punishments"] = {}

        if category not in self.users_db[user_id_str]["punishments"]:
            if category == "notes":
                self.users_db[user_id_str]["punishments"][category] = []
            else:
                self.users_db[user_id_str]["punishments"][category] = []

        punish_list = self.users_db[user_id_str]["punishments"][category]

        punishment_number = len(punish_list) + 1

        # Compose punishment entry dict
        entry = {
            "punishment_number": punishment_number,
            "date_time_cst": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S-06:00"),  # CST offset -6
            "reason": reason,
            "issued_by_id": str(issued_by.id),
            "issued_by_nickname": issued_by.display_name,
            "issued_by_username": str(issued_by),
            "notes": ""
        }
        if duration_seconds:
            entry["duration_seconds"] = duration_seconds
        if duration_minutes:
            entry["duration_minutes"] = duration_minutes

        if category == "notes":
            self.users_db[user_id_str]["punishments"][category].append(reason)
        else:
            self.users_db[user_id_str]["punishments"][category].append(entry)

        save_json(self.users_db_path, self.users_db)

        # Log in bot logs channel if enabled
        if self.config.get("features", {}).get("punishments", {}).get("log_all_punishments_in_bot_logs_channel", False):
            channel = self.bot.get_channel(self.logs_channel_id)
            if channel:
                embed = discord.Embed(
                    title=f"⚠️ | New punishment added: {category.capitalize()}",
                    description=f"User: {user.mention} ({user.id})\nBy: {issued_by.mention}\nReason: {reason}",
                    color=0xFF0000,
                    timestamp=datetime.utcnow(),
                )
                embed.set_author(name=str(user), icon_url=user.display_avatar.url)
                self.embed_footer(embed)
                await channel.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Punishments(bot))