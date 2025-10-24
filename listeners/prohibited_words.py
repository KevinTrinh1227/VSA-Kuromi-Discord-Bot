import os
import re
import json
import datetime
from typing import List, Optional

import discord
from discord.ext import commands

# Optional: load .env if python-dotenv is installed; otherwise os.getenv still works
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

"""
CHAT FILTER (Local Blacklist, No API)

- Reads BLACKLISTED_WORDS from .env (comma/semicolon/newline separated).
- Respects config.json:
    features.filtered_chat.enable_feature (bool)
    features.filtered_chat.omit_channels_id (list of str channel IDs)
    general.embed_color (hex string)
- Precompiles one efficient regex with small, safe fuzz:
    * case-insensitive
    * leet variants: a/@/4, e/3, i/1/!, o/0, s/$/5, t/7, b/8, g/9
    * up to 2 non-alphanumerics allowed between letters of each phrase
- Skips DMs, webhooks, bots, and omitted channels. Enforces len <= 4096.
- Default blacklist ["fuck you"] if feature enabled and env is empty/missing.

NOTE: Requires MESSAGE_CONTENT intent to read message.content.
"""

CONFIG_PATH = "config.json"
MAX_CHECK_LEN = 4096  # skip very long messages for speed & safety
DEFAULT_FALLBACK_LIST = ["fuck you"]


def _utcnow() -> datetime.datetime:
    return discord.utils.utcnow()


def _load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_env_blacklist(raw: Optional[str]) -> List[str]:
    """
    Split by comma, semicolon, or newline; strip whitespace; drop empties.
    """
    if not raw:
        return []
    parts = re.split(r"[,\n;]+", raw)
    return [p.strip() for p in parts if p.strip()]


def _leet_charclass(c: str) -> str:
    """
    For a single ASCII letter, return a character class covering simple leet variants.
    Non-letters are escaped literally.
    """
    mapping = {
        "a": "[aA@4]",
        "e": "[eE3]",
        "i": "[iI1!]",
        "o": "[oO0]",
        "s": "[sS$5]",
        "t": "[tT7]",
        "b": "[bB8]",
        "g": "[gG9]",
    }
    if c.isalpha():
        c_low = c.lower()
        if c_low in mapping:
            return mapping[c_low]
        # generic alphabetic: allow both cases
        return f"[{c_low}{c_low.upper()}]"
    # Escape regex metacharacters
    return re.escape(c)


def _phrase_to_pattern(phrase: str) -> str:
    """
    Convert a phrase like 'fuck you' into a fuzzy regex:
    - Expand each character with a small leet charclass.
    - Between characters/words, allow up to 2 non-alphanumerics: [^a-zA-Z0-9]{0,2}
      (catches 'f.u.c.k', 'f__uck', 'f-uck', 'f u c k', etc.)
    - Wrap with word-ish boundaries via lookarounds to reduce false positives.
    """
    # Normalize internal whitespace to single spaces
    cleaned = " ".join(phrase.split())
    if not cleaned:
        return ""

    sep = r"[^a-zA-Z0-9]{0,2}"
    parts: List[str] = []

    for ch in cleaned:
        if ch.isspace():
            # treat a space in the phrase as an allowed separator in text
            parts.append(sep)
        else:
            parts.append(_leet_charclass(ch))
            parts.append(sep)

    # Remove trailing separator
    if parts and parts[-1] == sep:
        parts.pop()

    core = "".join(parts)

    # Word-ish boundaries: avoid matching inside long alphanumeric runs
    # Negative lookbehind/ahead for alnum to reduce false positives
    return rf"(?<![A-Za-z0-9])(?:{core})(?![A-Za-z0-9])"


def _compile_blacklist_regex(phrases: List[str]) -> Optional[re.Pattern]:
    """
    Compile a single alternation regex from all phrases. Returns None if no valid phrases.
    """
    patterns = []
    for p in phrases:
        pat = _phrase_to_pattern(p)
        if pat:
            patterns.append(pat)
    if not patterns:
        return None
    big = "|".join(patterns)
    return re.compile(rf"(?:{big})", re.IGNORECASE)


class BadWordCheck(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client

        # Load config
        self._config = _load_config()
        self._enabled = bool(
            self._config.get("features", {})
            .get("filtered_chat", {})
            .get("enable_feature", False)
        )
        self._omit_channels = set(
            str(cid)
            for cid in self._config.get("features", {})
            .get("filtered_chat", {})
            .get("omit_channels_id", [])
        )

        # Embed color
        color_hex = self._config.get("general", {}).get("embed_color", "#ffffff")
        try:
            self._embed_color = int(color_hex.strip("#"), 16)
        except Exception:
            self._embed_color = int("ffffff", 16)

        # Build blacklist from env (with fallback if enabled)
        env_list = _parse_env_blacklist(os.getenv("BLACKLISTED_WORDS"))
        if self._enabled and not env_list:
            env_list = DEFAULT_FALLBACK_LIST[:]

        self._blacklist = env_list
        self._regex = _compile_blacklist_regex(self._blacklist)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # --- basic guards ---
        if message.author.bot or message.webhook_id is not None:
            return
        if not isinstance(message.channel, (discord.TextChannel, discord.Thread)):  # skip DMs
            return

        # Feature flag
        if not self._enabled:
            await self.client.process_commands(message)
            return

        # Omit certain channels by ID (config stores strings)
        if str(message.channel.id) in self._omit_channels:
            await self.client.process_commands(message)
            return

        content = message.content or ""
        if not content:
            await self.client.process_commands(message)
            return

        # Length guard
        if len(content) > MAX_CHECK_LEN:
            await self.client.process_commands(message)
            return

        # If no regex (empty env & feature off, or only blanks), skip
        if not self._regex:
            await self.client.process_commands(message)
            return

        # Quick test
        if not self._regex.search(content):
            await self.client.process_commands(message)
            return

        # --- action: delete & notify ---
        guild = message.guild

        # Short preview for the embed (don’t leak full content)
        preview = content.replace("`", "ˋ")
        if len(preview) > 200:
            preview = preview[:200] + f"\n… (+{len(content) - 200} chars)"

        embed = discord.Embed(
            title=f"**Prohibited Word Warning | {message.author}**",
            description=(
                "Your message was deleted because it contained prohibited words. "
                "If you believe this is a mistake, please contact staff.\n\n"
                f"**Preview:**\n```{preview}```"
            ),
            colour=self._embed_color,
            timestamp=_utcnow(),
        )
        # Footer and thumbnail
        if guild and guild.icon:
            embed.set_footer(text=f"© {guild.name}", icon_url=guild.icon.url)
        else:
            embed.set_footer(text=f"© {guild.name if guild else 'Server'}")
        embed.set_thumbnail(url=message.author.display_avatar.url)

        # Delete message (ignore if no perms)
        try:
            await message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass

        # Send warning (no mentions)
        try:
            await message.channel.send(
                embed=embed,
                allowed_mentions=discord.AllowedMentions.none()
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

        # Continue processing commands (if any)
        await self.client.process_commands(message)


async def setup(client: commands.Bot):
    await client.add_cog(BadWordCheck(client))
