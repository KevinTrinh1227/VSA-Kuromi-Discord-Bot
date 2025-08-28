# ─── json_backups.py ───────────────────────────────
# Cog: JSON Auto-Backup
# Description: Automatically backs up all important JSON files
# to a GitHub repository (submodule) once on bot startup.
# Reads settings from config.json:
# - enable_feature: enable/disable auto backup
# - show_git_outputs_in_terminal: prints git logs to terminal
# - log_in_bot_logs_channel: sends an embed to bot logs channel
# Updates recent_saved_timestamp in config.json after the backup.

import discord
from discord.ext import commands
from discord.ui import View, Button
from pathlib import Path
import json
import subprocess
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import logging
import shutil
import re
import os

logger = logging.getLogger("JSONBackup")

guild_id = os.getenv("DISCORD_SERVER_GUILD_ID", "0")

class JSONBackup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.cfg_path = Path("config.json")
        if not self.cfg_path.exists():
            raise FileNotFoundError(f"Missing config.json at {self.cfg_path}")
        self.load_config()
        # Run backup once on startup
        self.bot.loop.create_task(self.run_backup_on_startup())
        
        

    def load_config(self):
        self.cfg = json.loads(self.cfg_path.read_text())
        self.features = self.cfg.get("features", {}).get("auto_save_json_backups", {})
        self.enable_feature = self.features.get("enable_feature", True)
        self.show_terminal = self.features.get("show_git_outputs_in_terminal", False)
        self.log_in_channel = self.features.get("log_in_bot_logs_channel", True)
        self.time_between_saves = self.features.get("time_between_saves_minutes", 5)  # Default: 5 min
        self.git_submodule_folder_name = f"VSA-FAM-{guild_id}"
        self.github_repo_link = f"https://github.com/{self.features.get('github_auth_user_name')}/VSA-FAM-{guild_id}"
        self.file_paths = self.cfg.get("file_paths", {})
        self.embed_color = int(self.cfg.get("general", {}).get("embed_color", "#ff69ae").lstrip("#"), 16)
        self.bot_logs_channel_id = int(self.cfg.get("text_channel_ids", {}).get("bot_logs", 0))

    async def run_backup_on_startup(self):
        await self.bot.wait_until_ready()
        if not self.enable_feature:
            if self.show_terminal:
                print("[JSONBackup] Feature disabled in config.json. Skipping backup.")
            return

        try:
            now_utc = datetime.utcnow()
            now_cst = now_utc.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("America/Chicago"))
            formatted_now = now_cst.strftime("%-m/%-d/%Y @ %-I:%M %p CST")

            repo_path = Path(self.git_submodule_folder_name)
            repo_path.mkdir(parents=True, exist_ok=True)

            total_files = 0
            changed_files = []
            unchanged_files = []

            # List of files to backup
            files_to_backup = {
                "config.json": Path("config.json"),
                "requirements.txt": Path("requirements.txt"),
                ".env": Path(".env"),
                f"{self.cfg.get('file_paths', {}).get('vsa_family_db')}": Path(self.cfg.get('file_paths', {}).get('vsa_family_db')),
                f"{self.cfg.get('file_paths', {}).get('all_discord_user_member_database_json_path')}": Path(self.cfg.get('file_paths', {}).get('all_discord_user_member_database_json_path')),
                f"{self.cfg.get('file_paths', {}).get('server_polls')}": Path(self.cfg.get('file_paths', {}).get('server_polls'))
            }


            # Copy files into backups folder
            for rel_path, file_path in files_to_backup.items():
                if not file_path.exists():
                    if file_path.suffix == ".json":
                        file_path.parent.mkdir(parents=True, exist_ok=True)
                        file_path.write_text("{}")
                        if self.show_terminal:
                            print(f"[JSONBackup] Created missing JSON file: {file_path}")
                    else:
                        file_path.touch()
                        if self.show_terminal:
                            print(f"[JSONBackup] Created missing file: {file_path}")

                # Determine destination path inside backups/
                if file_path.parent == Path("."):
                    dest_path = repo_path / file_path.name
                else:
                    dest_path = repo_path / file_path.parent / file_path.name
                    dest_path.parent.mkdir(parents=True, exist_ok=True)

                if dest_path.exists() and dest_path.read_text() == file_path.read_text():
                    unchanged_files.append(str(file_path))
                else:
                    shutil.copy2(file_path, dest_path)
                    changed_files.append(str(file_path))
                total_files += 1

            # Initialize git repo if it doesn't exist
            if not (repo_path / ".git").exists():
                subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_path))
                if self.show_terminal:
                    print(f"[JSONBackup] Initialized new Git repo in {repo_path}")

            # Git username/email
            github_username = self.features.get("github_auth_user_name", "KevinTrinh1227")
            github_email = self.features.get("github_auth_user_email", "kevintrinh1227@gmail.com")
            subprocess.run(["git", "config", "user.name", github_username], cwd=str(repo_path))
            subprocess.run(["git", "config", "user.email", github_email], cwd=str(repo_path))

            # GitHub authentication
            github_token = os.getenv("GITHUB_TOKEN", "")
            if not github_token:
                raise ValueError("[JSONBackup] No GitHub token found in GITHUB_TOKEN!")

            guild_id = os.getenv("DISCORD_SERVER_GUILD_ID", "0")
            repo_name = f"VSA-FAM-{guild_id}"
            repo_with_auth = f"https://{github_username}:{github_token}@github.com/{github_username}/{repo_name}.git"

            # Set remote if not already set
            remotes = subprocess.run(["git", "remote"], cwd=str(repo_path), capture_output=True, text=True).stdout.strip()
            if "origin" not in remotes:
                subprocess.run(["git", "remote", "add", "origin", repo_with_auth], cwd=str(repo_path))
                if self.show_terminal:
                    print(f"[JSONBackup] Remote 'origin' set to {repo_with_auth}")

            # Add, commit, push
            git_status = subprocess.run(["git", "status", "--porcelain"], cwd=str(repo_path), capture_output=True, text=True)
            changes_detected = bool(git_status.stdout.strip())

            if changes_detected:
                stdout_setting = None if self.show_terminal else subprocess.DEVNULL
                stderr_setting = None if self.show_terminal else subprocess.DEVNULL

                subprocess.run(["git", "add", "."], cwd=str(repo_path), stdout=stdout_setting, stderr=stderr_setting)
                subprocess.run(["git", "commit", "-m", "Auto-backup JSON and .env files"], cwd=str(repo_path), stdout=stdout_setting, stderr=stderr_setting)
                subprocess.run(["git", "push", "-u", "origin", "main", "--force"], cwd=str(repo_path), stdout=stdout_setting, stderr=stderr_setting)


                if self.show_terminal:
                    print("[JSONBackup] Backup pushed successfully.")

            # Send embed to bot logs channel
            if self.log_in_channel:
                channel = self.bot.get_channel(self.bot_logs_channel_id)
                if channel and len(changed_files) > 0:

                    next_save_dt = datetime.utcnow().replace(tzinfo=ZoneInfo("UTC")) + timedelta(minutes=self.time_between_saves)
                    next_save_formatted = next_save_dt.astimezone(ZoneInfo("America/Chicago")).strftime("%-m/%-d/%Y @ %-I:%M %p CST")

                    files_field_value = "\n".join(
                        [f"- `{f}` (Changes detected 🟢)" for f in changed_files] +
                        [f"- `{f}` (No changes detected 🔴)" for f in unchanged_files]
                    )

                    stats_field_value = (
                        f"- Changed: **{len(changed_files)}** / **{total_files}** "
                        f"({(len(changed_files)/total_files)*100:.0f}%)\n"
                        f"- Unchanged: **{len(unchanged_files)}** / **{total_files}** "
                        f"({(len(unchanged_files)/total_files)*100:.0f}%)"
                    )

                    feature_field_value = (
                        f"- Auto-save enabled: {'`On 🟢`' if self.enable_feature else '`Off 🔴`'}\n"
                        f"- Save Interval: **{self.time_between_saves} min** (Next: {next_save_formatted})\n"
                        f"- Show git outputs in terminal: `{'True 🟢' if self.show_terminal else 'False 🔴'}`\n"
                        f"- Log alert in bot logs: `{'True 🟢' if self.log_in_channel else 'False 🔴'}`"
                    )

                    embed = discord.Embed(
                        title=f"💾 | All {total_files} JSON Files Backed Up!",
                        description=f"**{total_files}** Files ({len(changed_files)} Changed / {len(unchanged_files)} Unchanged) were checked.",
                        color=self.embed_color
                    )

                    embed.add_field(name=f"Files Backed Up ({total_files}):", value=files_field_value or "No files detected.", inline=False)
                    embed.add_field(name="Data Backup Stats", value=stats_field_value, inline=False)
                    embed.add_field(name="Backup Feature Settings", value=feature_field_value, inline=False)

                    view = discord.ui.View()
                    view.add_item(discord.ui.Button(
                        label="View Priv. Repo (Only Accessible To Dev)",
                        url=self.github_repo_link,
                        style=discord.ButtonStyle.link
                    ))

                    await channel.send(embed=embed, view=view)
                else:
                    print(f"| NO saves were made to GitHub cause length of changed files: {len(changed_files)}")

        except Exception as e:
            logger.error(f"[JSONBackup] Backup failed: {e}")
            if self.show_terminal:
                print(f"[JSONBackup] Backup failed: {e}")

async def setup(bot):
    await bot.add_cog(JSONBackup(bot))
