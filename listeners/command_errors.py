import discord
from discord.ext import commands
import discord.ui
import datetime
import json
import discord.errors


# Open the JSON file and read in the data
with open('config.json') as json_file:
    data = json.load(json_file)
    
#json data to run bot
bot_prefix = data["general"]["bot_prefix"]
embed_color = int(data["general"]["embed_color"].strip("#"), 16) #convert hex color to hexadecimal format
bot_logs_channel_id = int(data["text_channel_ids"]["bot_logs"]) 


class commend_error(commands.Cog):
    def __init__(self, client):
        self.client = client
    

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        # ERROR: if command doesnt exist
        if isinstance(error, commands.CommandNotFound):
            embed = discord.Embed(
                title=(f"**🔎 | Command does not exist!**"),
                description=f"The command you just issued does not exist. Please use `{bot_prefix}help` to double check the correct syntax. Contact staff if this is a mistake.",
                colour= embed_color
                )
            embed.timestamp = datetime.datetime.now()
            if(ctx.author.avatar):  # if user does have an avatar
                embed.set_footer(text=f"Requested by {ctx.author}", icon_url = ctx.author.avatar.url)
            else:                   # if user DOES NOT have an avatar
                embed.set_footer(text=f"Requested by {ctx.author}")
            await ctx.send(embed=embed)

        # ERROR: if user has a command cooldown
        elif isinstance(error, commands.CommandOnCooldown):
            embed = discord.Embed(
                title=(f"⏳ ** | This command is on cooldown!**"),
                description=f"Please wait `{error.retry_after:.2f}` more second(s) before trying to run the command again. If you believe this to be a mistake, please contact a staff member.",
                colour= embed_color
                )
            embed.timestamp = datetime.datetime.now()
            if(ctx.author.avatar):  # if user does have an avatar
                embed.set_footer(text=f"Requested by {ctx.author}", icon_url = ctx.author.avatar.url)
            else:                   # if user DOES NOT have an avatar
                embed.set_footer(text=f"Requested by {ctx.author}")
            await ctx.send(embed=embed)
        # ERROR: if user does not have the permission node
        elif isinstance(error, commands.MissingPermissions):
            embed = discord.Embed(
                title="🚫** | You are lacking permissions!**",
                description="You are lacking permissions to perform this action. If you believe this to be a mistake, please contact a staff member.",
                color = embed_color

            )
            embed.timestamp = datetime.datetime.now()
            if(ctx.author.avatar):  # if user does have an avatar
                embed.set_footer(text=f"Requested by {ctx.author}", icon_url = ctx.author.avatar.url)
            else:                   # if user DOES NOT have an avatar
                embed.set_footer(text=f"Requested by {ctx.author}")
            await ctx.send(embed=embed)
        # ERROR: if the command was missing arguments
        elif isinstance(error, commands.MissingRequiredArgument):
            embed = discord.Embed(
                title="🟡** | Missing arguments in command.**",
                description=f"The command you just ran is missing one or more arguments. Please use `{bot_prefix}help` to double check the command syntax, and try again.",
                color = embed_color
            )
            embed.timestamp = datetime.datetime.now()
            if(ctx.author.avatar):  # if user does have an avatar
                embed.set_footer(text=f"Requested by {ctx.author}", icon_url = ctx.author.avatar.url)
            else:                   # if user DOES NOT have an avatar
                embed.set_footer(text=f"Requested by {ctx.author}")
            await ctx.send(embed=embed)
        elif isinstance(error, discord.errors.HTTPException) and getattr(error, 'status', None) == 429:
            now = datetime.datetime.utcnow()
            retry_after = getattr(error, 'retry_after', 'Unknown')
            route_info = getattr(error, 'response', None)

            # Prepare log embed
            embed = discord.Embed(
                title="⚠ Rate Limit Hit!",
                description=f"Route: `{str(route_info.url) if route_info else 'Unknown'}`",
                color=discord.Color.orange()
            )
            embed.add_field(name="Retry After", value=str(retry_after))
            embed.timestamp = now

            # Send to the channel where the command was used
            try:
                await ctx.send(embed=embed)
            except discord.errors.Forbidden:
                pass  # Ignore if the bot can't send in that channel

            # Send to bot logs channel
            log_channel = self.client.get_channel(bot_logs_channel_id)
            if log_channel:
                try:
                    await log_channel.send(embed=embed)
                except discord.errors.Forbidden:
                    pass

            # Save to file for permanent record
            log_data = {
                "time": now.strftime("%Y-%m-%d %H:%M:%S"),
                "status": 429,
                "retry_after": retry_after,
                "route": str(route_info.url) if route_info else "Unknown",
            }
            with open("rate_limit_log.json", "a") as f:
                f.write(json.dumps(log_data) + "\n")

            print(f"[RATE LIMIT] {json.dumps(log_data, indent=2)}")

        else:
            print(error) # for other errors so they dont get suppressed
            await ctx.send("An error has occured, please contact the bot dev.")


    
        
async def setup(client):
    await client.add_cog(commend_error(client))
    
    

