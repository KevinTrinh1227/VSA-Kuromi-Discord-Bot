import discord
from discord.ext import commands
import discord.ui
import os
from dotenv import load_dotenv
import json
from discord import app_commands

""" ==========================================
* CONFIG.JSON SECTION
*
* Creates a config.json on first run with your
* VSA-Family default schema.
========================================== """
if not os.path.exists('config.json'):
    default_config = {
        "config": {
            "bool": 0
        },
        "general": {
            "bot_prefix": "!",
            "embed_color": "#FF69AE",
            "discord_server_guild_id": ""
        },
        "features": {
            "filtered_chat": 0,
            "inactivity_cmd": 0,
            "punishments_cmd": 0,
            "server_stats": 0,
            "coin_level_system": 0
        },
        "category_ids": {
            "tickets_category": ""
        },
        "voice_channel_ids": {
            "member_count": "",
            "online_in_family": "",
            "fam_leads_online": ""
        },
        "text_channel_ids": {
            "welcome": "",
            "inactivity_notice": "",
            "tickets_transcripts": "",
            "bot_logs": ""
        },
        "role_ids": {
            "family_member": "",
            "family_lead": "",
            "staff_member": "",
            "verified_vsa_member": "",
            "unverified_vsa_member": ""
        },
        "embed_templates": {
            "welcome_embed": {
                "embed_description": "Welcome to {guild_name}, {member.mention}!",
                "photo_title": "{member.name} has joined! (#{member_count})",
                "photo_footer": "Enjoy your stay in {guild_name}!"
            },
            "selection_roles": {
                "title": "**🔔 | PUBLIC SELF SELECTION ROLES**",
                "description": "Click the buttons below to claim or unclaim roles.",
                "list_of_roles": [],
                "footer_text": "\u00a9\ufe0f {guild_name}"
            },
            "ticket_system": {
                "title": "**🎟️ | Ticket Support**",
                "description": "Need help? Pick a category below to open a private ticket.",
                "ticket_type_list": [],
                "footer_text": "\u00a9\ufe0f {guild_name}"
            }
        }
    }
    with open('config.json', 'w') as config_file:
        json.dump(default_config, config_file, indent=2)

errors = []


def activateBot (discord_bot_token, bot_prefix, discord_application_id):
    intents = discord.Intents.all()
    client = commands.Bot(command_prefix = bot_prefix, case_insensitive=True, intents=intents, application_id = discord_application_id)
    client.remove_command("help") #removes the default help command
            

    # If the bot is already configured meaning that inside the config.json
    # ["config"]["bool"] == 1, then we run as normal.


    """ ==========================================
    * BOT START UP SECTION
    *
    * This block starts up the bot. Here it 
    * checks if the config.json has already been
    * configured. If it hasnt, then it only loads
    * loads up the listeners.command_errors, and
    * commands.setup cog.
    ========================================== """
    @client.event
    async def on_ready():
    
        
        # Open the JSON file and read in the data
        with open('config.json') as json_file:
            data = json.load(json_file)
        
        name = client.user.name.upper()
        discriminator = client.user.discriminator.upper()
        print("--------------------------------------------------")
        print(f"* LOGGED IN AS: {name}#{discriminator}")
        
        if data["config"]["bool"] == 0:
            await client.load_extension("listeners.command_errors")
            await client.load_extension('commands.setup')
            await client.tree.sync()
            print("YOUR BOT REQUIRES AN INITIAL SETUP. 🟡")
            print("--------------------------------------------------")
            for x in range(0, 10):
                print("* USE: \"/setup\" or \"!setup\" IN YOUR SERVER TO BEGIN.")
            print("--------------------------------------------------")
                
        else:
            print("--------------------------------------------------")
            await load_cogs()
            print(f"* {os.path.splitext(os.path.basename(__file__))[0]:<30}{'Successful':<12}🟢")

            # Sync the commands to Discord.
            await client.tree.sync()

            print("--------------------------------------------------")
            await print_errors()
            #change_stats_channels.start()
            

    async def load_cogs():
        # Load in all listeners
        print(f"{'LISTENER FILES':<30}  {'LOAD STATUS':<30}")
        for filename in os.listdir("./listeners"):
            if filename.endswith(".py"):
                try:
                    await client.load_extension(f"listeners.{filename[:-3]}")
                    print(f"* {os.path.splitext(filename)[0]:<30}{'Successful':<12}🟢")
                except Exception as e:
                    errors.append(e)
                    print(f"* {os.path.splitext(filename)[0]:<30}{'Failed':<12}🔴")
        print(f"\n{'COMMAND FILES':<30}  {'LOAD STATUS':<30}")
        # Load in all commands
        for filename in os.listdir("./commands"):
            if filename.endswith(".py"):
                try:
                    await client.load_extension(f"commands.{filename[:-3]}")
                    print(f"* {os.path.splitext(filename)[0]:<30}{'Successful':<12}🟢")
                except Exception as e:
                    errors.append(e)
                    print(f"* {os.path.splitext(filename)[0]:<30}{'Failed':<12}🔴")
        print(f"\n{'OTHER FILES':<30}  {'LOAD STATUS':<30}")
        

    async def print_errors():
        if len(errors) != 0:
            print("ERRORS occured during startup:")
            for error in errors:
                print(error)
        else:
            pass
            
            
    client.run(discord_bot_token)
        