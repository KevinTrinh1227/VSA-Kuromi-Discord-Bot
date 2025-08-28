"""
# 1. Create a new venv directory called “venv”
python3 -m venv venv

pip install -r requirements.txt


# 2. Activate it
source venv/bin/activate
"""

import os
import json
from dotenv import load_dotenv
from client import activateBot


def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

def main():
    # Load environment variables
    load_dotenv()
    token = os.getenv("DISCORD_BOT_TOKEN")
    application_id = int(os.getenv("DISCORD_APPLICATION_ID"))
    server_guild_id = int(os.getenv("DISCORD_SERVER_GUILD_ID"))

    # Load config.json to get the prefix
    config = load_config()
    prefix = config["general"].get("prefix", "!")

    # Start the bot
    activateBot(token, config, prefix, application_id, server_guild_id)

if __name__ == "__main__":
    main()