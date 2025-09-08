import discord
from discord.ext import commands

class information(commands.Cog):
    def __init__(self, client):
        self.client = client

    # information command
    @commands.has_permissions(administrator=True)
    @commands.hybrid_command(
        aliases=["i", "inform", "info"], 
        brief="information",
        description="View server information",
        with_app_command=True
    )
    async def information(self, ctx):
        # Define the buttons
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Website", url="https://www.projectkuromi.com"))
        view.add_item(discord.ui.Button(label="Instagram", url="https://instagram.com/project.kuromi"))
        view.add_item(discord.ui.Button(label="TikTok", url="https://www.tiktok.com/@project.kuromi"))

        # Send the file with buttons
        file = discord.File("./assets/outputs/information.png", filename="information.png")
        await ctx.send(file=file, view=view)

async def setup(client):
    await client.add_cog(information(client))
