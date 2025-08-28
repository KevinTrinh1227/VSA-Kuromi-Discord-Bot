import discord
from discord.ext import commands
import asyncio
import json
from datetime import datetime, timezone

# Load config
with open('config.json') as json_file:
    data = json.load(json_file)

embed_color = int(data["general"]["embed_color"].strip("#"), 16)  # hex -> int
bot_logs_channel_id = int(data["text_channel_ids"]["bot_logs"])


class Purge(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.has_permissions(manage_messages=True)
    @commands.hybrid_command(
        aliases=["del", "delete", "clear"],
        brief="purge [integer value]",
        description="Clear a specified amount of chat messages",
        with_app_command=True
    )
    async def purge(self, ctx, amount: int):
        MAX_DELETE = 50  # capped max delete amount
        DELAY_BETWEEN_DELETES = 0.35  # delay in seconds

        if amount > MAX_DELETE:
            return await self.safe_send(ctx, f"⚠ You can only delete up to {MAX_DELETE} messages at a time.")

        # Defer if slash command
        if getattr(ctx, "interaction", None):
            try:
                if not ctx.interaction.is_expired():
                    await ctx.interaction.response.defer()
            except:
                pass

        # Log the purge command usage in the bot logs channel
        await self.log_purge_usage(ctx, amount)

        messages_to_delete = []
        async for msg in ctx.channel.history(limit=amount + 1):
            # skip the command message itself if it exists
            if msg.id == getattr(ctx.message, "id", None):
                continue
            messages_to_delete.append(msg)

        deleted_count = 0

        # Delete messages one-by-one with delay to avoid rate limits
        for msg in messages_to_delete:
            try:
                await msg.delete()
                deleted_count += 1
            except discord.HTTPException:
                pass  # ignore failures
            await asyncio.sleep(DELAY_BETWEEN_DELETES)

        await self.safe_send(
            ctx,
            embed=discord.Embed(
                title="✅ Purge Complete",
                description=f"Deleted {deleted_count} messages.",
                color=embed_color
            ),
            auto_delete=5
        )

    async def log_purge_usage(self, ctx, amount):
        """Send a log message to bot logs channel with info about the purge command usage."""
        channel = self.client.get_channel(bot_logs_channel_id)
        if channel is None:
            return  # channel not found or bot has no access

        user = ctx.author
        member = ctx.guild.get_member(user.id) if ctx.guild else None

        # Gather user's permissions and roles if member object exists
        if member:
            perms = [perm for perm, value in member.guild_permissions if value]
            roles = [role.mention for role in member.roles if role.name != "@everyone"]
            has_admin = member.guild_permissions.administrator
        else:
            perms = []
            roles = []
            has_admin = False

        embed = discord.Embed(
            title=f"🚨 | {user} used the purge command!",
            color=embed_color,  # bright red color
            timestamp=datetime.now(timezone.utc)
        )


        list_of_perms_str = ", ".join(perms) or "None"
        embed.add_field(name="User", value=f"{user.mention} - `{user.id}`", inline=False)
        embed.add_field(name="Channel", value=ctx.channel.mention, inline=False)
        embed.add_field(name="Purge Amount Requested", value=str(amount), inline=False)
        embed.add_field(name="Has Admin Powers", value=str(has_admin), inline=False)
        embed.add_field(name=f"{user}'s Roles ({len(roles)})", value=", ".join(roles) or "None", inline=False)
        embed.add_field(name=f"{user}'s Permissions ({len(perms)})", value=f"```{list_of_perms_str }```", inline=False)

        embed.set_thumbnail(url=user.display_avatar.url if user.display_avatar else None)

        await channel.send(embed=embed)

    async def safe_send(self, ctx, *args, auto_delete=None, **kwargs):
        if getattr(ctx, "interaction", None) and not ctx.interaction.is_expired():
            try:
                msg = await ctx.interaction.followup.send(*args, **kwargs)
            except discord.NotFound:
                # Interaction expired or message deleted, fallback to regular send
                msg = await ctx.send(*args, **kwargs)
            if auto_delete:
                await asyncio.sleep(auto_delete)
                try:
                    await msg.delete()
                except discord.NotFound:
                    pass
            return msg
        else:
            return await ctx.send(*args, delete_after=auto_delete, **kwargs)


async def setup(client):
    await client.add_cog(Purge(client))
