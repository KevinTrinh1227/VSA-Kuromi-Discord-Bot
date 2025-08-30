import discord
from discord.ext import commands

class rules(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.has_permissions(administrator=True)
    @commands.hybrid_command(
        aliases=["r", "rule"], 
        brief="rules",
        description="View server rules",
        with_app_command=True
    )
    async def rules(self, ctx):

        # Send the file with buttons
        file = discord.File("./assets/outputs/rules.png", filename="rules.png")
        await ctx.send(file=file)

async def setup(client):
    await client.add_cog(rules(client))
