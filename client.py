import discord
from discord.ext import commands
import os
from datetime import datetime, timezone
import pytz
import json                            # ← added
from pathlib import Path              # ← added
from utils.time_utils import format_cst, parse_cst_timestamp, time_ago, parse_iso_to_cst, CST
from utils.uptime_utils import record_session_info
from datetime import datetime, timedelta
import asyncio
from utils.discord_utils import (
    validate_text_channel,
    validate_role,
    validate_category,
)

from utils.uptime_utils import *

default_none_null_value_str = "-"
errors = []
loaded_cogs = {
    "tasks": [],
    "listeners": [],
    "commands": []
}
startup_time = None

# Status labels
STATUS_SUCCESS = "✅"
STATUS_FAILED = "❌"
STATUS_NO_COGS = "No cogs"


TASKS_COGS_FOLDER_NAME = "tasks"
LISTENER_COGS_FOLDER_NAME = "listeners"
COMMANDS_COGS_FOLDER_NAME = "commands"

TOTAL_LISTENER_COGS = 0
TOTAL_TASK_COGS = 0
TOTAL_COMMAND_COGS = 0

COGS_STARTUP_INFO = {}

def activateBot(discord_bot_token, config, bot_prefix, discord_application_id, server_guild_id):

    class MyBot(commands.Bot):
        def __init__(self, **kwargs):
            self.server_guild_id = kwargs.pop("server_guild_id")
            super().__init__(**kwargs)

        async def setup_hook(self):
            # Load all cogs first
            await load_cogs(self)

            # Sync slash commands to your single server (guild-only)
            guild = discord.Object(id=self.server_guild_id)
            await self.tree.sync(guild=guild)
            #print(f"✅ Synced slash commands to guild {self.server_guild_id}")

    intents = discord.Intents.all()
    bot = MyBot(
        command_prefix=bot_prefix,
        intents=intents,
        application_id=discord_application_id,
        server_guild_id=server_guild_id
    )

    bot.remove_command("help")

    @bot.event
    async def on_ready():
        global startup_time
        startup_time = datetime.now(pytz.timezone("America/Chicago"))

        print("|")
        print(f"│ Starting up bot client...")
        print("| [https://github.com/KevinTrinh1227]")

        # These are already loaded in setup_hook, so no need to reload cogs
        # await load_cogs(bot)

        await print_startup_stats(bot)

    async def load_cogs(bot):
        global COGS_STARTUP_INFO
        folder_labels = {
            TASKS_COGS_FOLDER_NAME: "TASK COGS",
            LISTENER_COGS_FOLDER_NAME: "LISTENER COGS",
            COMMANDS_COGS_FOLDER_NAME: "COMMAND COGS"
        }


        for folder_name in [TASKS_COGS_FOLDER_NAME, LISTENER_COGS_FOLDER_NAME, COMMANDS_COGS_FOLDER_NAME]:
            try:
                files = [f for f in os.listdir(f"./{folder_name}") if f.endswith(".py")]
            except FileNotFoundError:
                files = []

            total = len(files)
            
            # initialize dict for this folder_name if missing
            COGS_STARTUP_INFO.setdefault(folder_name, {})

            # Now safe to assign to keys inside
            COGS_STARTUP_INFO[folder_name]["load_failed"] = []
            COGS_STARTUP_INFO[folder_name]["load_success"] = []
            if folder_name == TASKS_COGS_FOLDER_NAME:
                global TOTAL_TASK_COGS
                TOTAL_TASK_COGS = total
                #print(f"↳{TOTAL_TASK_COGS}")
            elif folder_name == LISTENER_COGS_FOLDER_NAME:
                global TOTAL_LISTENER_COGS
                TOTAL_LISTENER_COGS = total
                #print(f"↳{TOTAL_LISTENER_COGS}")
            elif folder_name == COMMANDS_COGS_FOLDER_NAME:
                global TOTAL_COMMAND_COGS
                TOTAL_COMMAND_COGS = total
                #print(f"↳{TOTAL_COMMAND_COGS}")
            label_raw = folder_labels[folder_name]
            label_with_count = f"{label_raw} ({total})"

            spacing = max(24, len(label_with_count) + 1)
            print("|")
            print(f"| STATUS{'':<10}{label_with_count:<{spacing}}DESCRIPTION")
            
            
            COGS_STARTUP_INFO[folder_name]["load_failed"] = []
            COGS_STARTUP_INFO[folder_name]["load_success"] = []
            
            

            if total == 0:
                print(f"| * {STATUS_NO_COGS:<14}{default_none_null_value_str:<24}{default_none_null_value_str}")
                continue

            for file in files:
                name = file[:-3]
                cog_path = f"{folder_name}.{name}"
                cog_path_full = f"{folder_name}.{file}"
                try:
                    await bot.load_extension(cog_path)
                    description = get_cog_description(bot, name)
                    loaded_cogs[folder_name].append((file, description))
                    print(f"| * {STATUS_SUCCESS:<13}{file:<24}{description}")
                    success_cog_dict = {
                        "cog": name,
                        "cog_file": file,
                        "cog_file_path": cog_path_full,
                    }
                    COGS_STARTUP_INFO[folder_name]["load_success"].append(success_cog_dict)
                except Exception as e:
                    errors.append({
                        "cog": name,
                        "cog_file": file,
                        "cog_file_path": cog_path_full,
                        "error_type": type(e).__name__,
                        "error_message": str(e)
                    })
                    # print the failure line with a dash in the DESCRIPTION column...
                    print(f"| * {STATUS_FAILED:<13}{file:<24}{default_none_null_value_str}")
                    # ...and immediately print the actual error message, indented
                    print(f"|     ↳ Error loading {file}: {type(e).__name__}: {e}")
                    failed_cog_dict = {
                        "cog": name,
                        "cog_file": file,
                        "cog_file_path": cog_path_full,
                        "error_type": type(e).__name__,
                        "error_message": str(e)
                    }
                    
                    COGS_STARTUP_INFO[folder_name]["load_failed"].append(failed_cog_dict)


    def get_cog_description(bot, name):
        """
        Given a file base `name` (like 'daily_question'), convert it to the
        Cog class name ('DailyQuestion') and fetch its .description
        """
        try:
            # turn 'daily_question' → 'DailyQuestion'
            cog_name = "".join(part.title() for part in name.split("_"))
            cog = bot.get_cog(cog_name)
            desc = getattr(cog, "description", default_none_null_value_str)
            return format_description(desc)
        except Exception:
            return default_none_null_value_str


    def format_description(desc: str) -> str:
        max_description_length = 35
        if not desc or desc.strip() == "":
            return default_none_null_value_str
        if len(desc) > max_description_length:
            return desc[:max_description_length - 3] + "..."
        return desc


    async def print_startup_stats(bot):
        print("|")
        total_loaded = sum(len(v) for v in loaded_cogs.values())
        total_errors = len(errors)
        success_rate = int((total_loaded / (total_loaded + total_errors)) * 100) if (total_loaded + total_errors) > 0 else 0
        guilds = bot.guilds
        total_users = sum(g.member_count for g in guilds)
        latency_ms = round(bot.latency * 1000)


        print(f"| GENERAL INFO")
        print(f"| * Cogs loaded: {total_loaded} - Errors: {total_errors} - Total: {total_loaded + total_errors} ({success_rate}%)")
        print(f"| * Connected guild(s): {len(guilds)} (Server name: {guilds[0].name if guilds else 'N/A'})")
        print(f"| * Total users across guild(s): {total_users}")
        print(f"| * Session start time: {startup_time.strftime('%Y-%m-%d %I:%M:%S %p %Z')}")
        print(f"| * On Startup latency: {latency_ms}ms")
        print("|")
        
    bot.run(discord_bot_token)