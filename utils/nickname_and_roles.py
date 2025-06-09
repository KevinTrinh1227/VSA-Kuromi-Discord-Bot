import json
import discord
from utils.users_utils import get_verified_users

CONFIG_FILE = "config.json"

async def rename_user(member: discord.Member):
    """
    Rename a Discord member according to the nickname template in config
    based on their saved verified user data.
    """
    user_id_str = str(member.id)

    # Load verified user data
    try:
        verified_data = get_verified_users()
    except (FileNotFoundError, json.JSONDecodeError):
        return  # No data, skip

    if user_id_str not in verified_data:
        return  # No saved data for this user

    user_info = verified_data[user_id_str]

    # Load config file
    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return

    nickname_templates = config.get("nickname_templates", {})
    format_before = nickname_templates.get("format_before_seperator", "")
    separator = nickname_templates.get("seperator_symbol", " | ")
    format_after = nickname_templates.get("format_after_seperator", "")

    # Extract info to replace placeholders, fallback to empty strings or zeroes
    level = user_info.get("level", 0)
    if level == 0:
        level = user_info.get("general", {}).get("level", 0)
    first_name = user_info.get("first_name", "") or user_info.get("general", {}).get("first_name", "")
    last_name = user_info.get("last_name", "") or user_info.get("general", {}).get("last_name", "")

    # Replace placeholders in format strings
    before_text = format_before.replace("{level}", str(level))
    after_text = format_after.replace("{first_name}", first_name).replace("{last_name}", last_name)

    new_nick = f"{before_text}{separator}{after_text}".strip()

    if new_nick and new_nick != member.display_name:
        try:
            await member.edit(nick=new_nick)
        except discord.Forbidden:
            pass
        except Exception as e:
            print(f"Error renaming user {member}: {e}")

async def assign_roles(user_id: int, role_ids: list[str], guild: discord.Guild):
    """
    Assign roles from role_ids list (strings) to user specified by user_id in the given guild.
    """
    member = guild.get_member(user_id)
    if not member:
        try:
            member = await guild.fetch_member(user_id)
        except discord.NotFound:
            return  # User not found in guild
        except Exception as e:
            print(f"Error fetching member {user_id}: {e}")
            return

    roles_to_add = []
    guild_roles = {role.id: role for role in guild.roles}

    for role_id_str in role_ids:
        try:
            role_id = int(role_id_str)
        except ValueError:
            continue  # Skip invalid role IDs

        role = guild_roles.get(role_id)
        if role and role not in member.roles:
            roles_to_add.append(role)

    if roles_to_add:
        try:
            await member.add_roles(*roles_to_add, reason="Restoring roles on rejoin")
        except discord.Forbidden:
            pass
        except Exception as e:
            print(f"Error assigning roles to {member}: {e}")
