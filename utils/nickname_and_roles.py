import discord
import json
import os

# ─── Load config safely ───────────────────────────────────────────
try:
    with open("config.json", "r") as f:
        config = json.load(f)
except (FileNotFoundError, json.JSONDecodeError) as e:
    print(f"[Config] Failed to load config.json: {e}")
    config = {}

async def rename_user(member: discord.Member, user_id_str: str, points: int, first_name: str, last_name: str):
    """
    Rename a member using a nickname template from config.json.
    """
    try:
        nick_config = config.get("nickname_templates", {})
        if not nick_config.get("rename_nickname_feature", False):
            return  # Feature disabled

        before = nick_config.get("format_before_seperator", "{points}")
        sep    = nick_config.get("seperator_symbol", " | ")
        after  = nick_config.get("format_after_seperator", "{first_name} {last_name} ✔")

        nickname = (
            before.replace("{points}", str(points))
            + sep
            + after
                .replace("{first_name}", first_name)
                .replace("{last_name}", last_name)
        )

        if member.nick != nickname:
            try:
                await member.edit(nick=nickname, reason="Auto-renamed via verification system")
            except discord.Forbidden:
                print(f"[Rename] Permission denied renaming user {user_id_str}.")
            except discord.HTTPException as http_err:
                print(f"[Rename] HTTP error renaming {user_id_str}: {http_err}")
    except Exception as e:
        print(f"[Rename] Unexpected error in rename_user for {user_id_str}: {e}")

async def assign_roles(member: discord.Member, role_ids):
    """
    Assign each role in role_ids to the member, ignoring any missing roles
    or permission errors.
    """
    guild = member.guild  # we can always get guild from member
    for role_id in role_ids:
        try:
            role = discord.utils.get(guild.roles, id=role_id)
            if role:
                await member.add_roles(role, reason="Verified VSA Member")
            else:
                print(f"[Roles] Role ID {role_id} not found in guild {guild.id}.")
        except discord.Forbidden:
            print(f"[Roles] Permission denied adding role {role_id} to {member.id}.")
        except discord.HTTPException as http_err:
            print(f"[Roles] HTTP error adding role {role_id} to {member.id}: {http_err}")
        except Exception as e:
            print(f"[Roles] Unexpected error for role {role_id}, member {member.id}: {e}")
