import discord
from discord.ext import commands
import discord.ui
import datetime
import json
import traceback
from typing import Optional

# Open the JSON file and read in the data
with open('config.json') as json_file:
    data = json.load(json_file)

# json data to run bot
bot_prefix = data["general"]["bot_prefix"]
# convert hex color "#RRGGBB" -> int
embed_color = int(data["general"]["embed_color"].strip("#"), 16)
bot_logs_channel_id = int(data["text_channel_ids"]["bot_logs"])


class commend_error(commands.Cog):
    """Global command error handler cog (clean messages for users, rich logs for staff)."""

    def __init__(self, client: commands.Bot):
        self.client = client

    # --------- helpers ---------
    @staticmethod
    def _utcnow() -> datetime.datetime:
        # timezone-aware (Discord embeds expect aware timestamps)
        return discord.utils.utcnow()

    @staticmethod
    def _footer_author(embed: discord.Embed, author: discord.abc.User) -> None:
        # use display_avatar for reliability (default avatar-safe)
        embed.set_footer(text=f"Requested by {author}", icon_url=author.display_avatar.url)

    async def _send_user_embed(
        self,
        ctx: commands.Context,
        title: str,
        description: str,
        colour: Optional[int] = None
    ) -> None:
        colour = colour if colour is not None else embed_color
        embed = discord.Embed(title=title, description=description, colour=colour, timestamp=self._utcnow())
        self._footer_author(embed, ctx.author)
        try:
            await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.Forbidden:
            # If we cannot speak in the channel, silently ignore (avoid cascading errors)
            pass

    async def _log_to_bot_channel(self, embed: discord.Embed) -> None:
        log_ch = self.client.get_channel(bot_logs_channel_id)
        if log_ch:
            try:
                await log_ch.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            except discord.Forbidden:
                pass

    def _build_log_embed(self, ctx: commands.Context, title: str, description: str) -> discord.Embed:
        embed = discord.Embed(
            title=title,
            description=description,
            colour=discord.Colour.orange(),
            timestamp=self._utcnow()
        )
        embed.add_field(name="User", value=f"{ctx.author} (`{ctx.author.id}`)", inline=False)
        if ctx.guild:
            embed.add_field(name="Guild", value=f"{ctx.guild.name} (`{ctx.guild.id}`)", inline=True)
            embed.add_field(name="Channel", value=f"#{ctx.channel}", inline=True)
        else:
            embed.add_field(name="Context", value="DM", inline=True)
        return embed

    # --------- global error listener ---------
    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: Exception):
        """Centralized error handler. Attempts to be quiet, helpful, and safe."""

        # 0) Respect local overrides to avoid double-handling
        if hasattr(ctx.command, "on_error"):
            return
        if ctx.cog and commands.Cog._get_overridden_method(getattr(ctx.cog, "cog_command_error", None)):
            return

        # Unwrap CommandInvokeError to original for easier checks
        original = getattr(error, "original", error)

        # 1) Common, user-facing errors (nicely formatted)
        if isinstance(error, commands.CommandNotFound):
            return await self._send_user_embed(
                ctx,
                "**🔎 | Command does not exist!**",
                f"The command you used does not exist. Use `{bot_prefix}help` to check syntax."
            )

        if isinstance(error, commands.CommandOnCooldown):
            return await self._send_user_embed(
                ctx,
                "⏳ **| This command is on cooldown!**",
                f"Please wait `{error.retry_after:.2f}` more second(s) before trying again."
            )

        if isinstance(error, commands.MissingPermissions):
            missing = ", ".join(error.missing_permissions) if getattr(error, "missing_permissions", None) else "required permissions"
            return await self._send_user_embed(
                ctx,
                "🚫 **| You are lacking permissions!**",
                f"You are missing: `{missing}`."
            )

        if isinstance(error, commands.BotMissingPermissions):
            missing = ", ".join(error.missing_permissions) if getattr(error, "missing_permissions", None) else "required permissions"
            return await self._send_user_embed(
                ctx,
                "🤖 **| I am lacking permissions!**",
                f"I am missing: `{missing}`. Please adjust my role permissions."
            )

        if isinstance(error, commands.MissingRole):
            return await self._send_user_embed(
                ctx,
                "🚫 **| Missing role.**",
                f"You must have the `{error.missing_role}` role to use this command."
            )

        if isinstance(error, commands.MissingAnyRole):
            roles = ", ".join(map(str, getattr(error, "missing_roles", []))) or "required roles"
            return await self._send_user_embed(
                ctx,
                "🚫 **| Missing role(s).**",
                f"You must have one of: `{roles}`."
            )

        if isinstance(error, commands.NotOwner):
            return await self._send_user_embed(
                ctx,
                "🔒 **| Owner-only command.**",
                "Only the bot owner can use this command."
            )

        if isinstance(error, commands.NoPrivateMessage):
            return await self._send_user_embed(
                ctx,
                "📛 **| Guild-only command.**",
                "This command can only be used in a server channel."
            )

        if isinstance(error, commands.PrivateMessageOnly):
            return await self._send_user_embed(
                ctx,
                "📩 **| DM-only command.**",
                "This command can only be used in DMs."
            )

        if isinstance(error, commands.MaxConcurrencyReached):
            per = str(error.per.name).lower() if getattr(error, "per", None) else "unknown scope"
            return await self._send_user_embed(
                ctx,
                "⚠️ **| Too many concurrent uses.**",
                f"This command is already running the maximum number of times for `{per}`."
            )

        if isinstance(error, commands.MissingRequiredArgument):
            missing = f"`{error.param.name}`" if getattr(error, "param", None) else "one or more arguments"
            return await self._send_user_embed(
                ctx,
                "🟡 **| Missing arguments.**",
                f"The command is missing {missing}. Use `{bot_prefix}help` to check syntax."
            )

        if isinstance(error, (commands.BadArgument, commands.BadUnionArgument)):
            return await self._send_user_embed(
                ctx,
                "🧩 **| Invalid argument(s).**",
                f"One or more arguments were invalid. Use `{bot_prefix}help` to check syntax and types."
            )

        if isinstance(error, commands.CheckFailure):
            # Generic check failure (covers custom @checks)
            return await self._send_user_embed(
                ctx,
                "🚫 **| You cannot use this command.**",
                "Your account does not meet the requirements to use this command."
            )

        # 2) HTTP 429 handling (rate limits), sometimes wrapped in CommandInvokeError
        if isinstance(original, discord.HTTPException) and original.status == 429:
            now = self._utcnow()
            retry_after = getattr(original, "retry_after", "Unknown")
            url = getattr(getattr(original, "response", None), "url", None)
            route = str(url) if url else "Unknown"

            # user-facing heads-up
            await self._send_user_embed(
                ctx,
                "⚠️ **| Rate limit hit.**",
                f"Please try again shortly. (Route: `{route}`, retry_after: `{retry_after}`)"
            )

            # staff log
            embed = self._build_log_embed(ctx, "⚠️ Rate Limit Hit", f"Route: `{route}`")
            embed.add_field(name="Retry After", value=str(retry_after), inline=True)
            await self._log_to_bot_channel(embed)
            # Also persist to file for auditing
            log_data = {
                "time": now.isoformat(),
                "status": 429,
                "retry_after": retry_after,
                "route": route,
            }
            try:
                with open("rate_limit_log.json", "a") as f:
                    f.write(json.dumps(log_data) + "\n")
            except Exception:
                pass
            print(f"[RATE LIMIT] {json.dumps(log_data, indent=2)}")
            return

        # 3) Fallback: quietly inform user, log details for staff
        await self._send_user_embed(
            ctx,
            "❗ **| An error occurred.**",
            "Something went wrong while running that command. Please contact the bot developer."
        )

        # Build concise staff log (do not leak sensitive info to users)
        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        short_tb = tb[-1500:]  # avoid massive messages; keep tail where the cause usually is

        log_embed = self._build_log_embed(
            ctx,
            f"❗ Unhandled Error: {type(original).__name__}",
            f"```py\n{short_tb}\n```"
        )
        await self._log_to_bot_channel(log_embed)
        # Also print to console for devs running locally
        print(tb)


async def setup(client: commands.Bot):
    await client.add_cog(commend_error(client))
