# bad_word_check.py
import os
import re
import json
import datetime
import unicodedata
import time
from typing import List, Optional, Tuple
from collections import defaultdict

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
    features.filtered_chat.punishments_mode (bool)  # if true, call Punishments cog
    general.embed_color (hex string)  # used nowhere now, but kept for compat
- Precompiles one efficient regex with small, safe fuzz:
    * case-insensitive
    * leet variants: a/@/4, e/3, i/1/!, o/0, s/$/5, t/7, b/8, g/9
    * up to 2 non-alphanumerics allowed between letters of each phrase
- Normalizes content (NFKD, strip diacritics, remove zero-width chars) before matching.
- Skips DMs, webhooks, bots, and omitted channels. Enforces len <= MAX_CHECK_LEN.
- Default blacklist ["fuck you"] if feature enabled and env is empty/missing.
- Deletes offending messages, posts a concise channel warning (rate-limited),
  and DMs the user a private notice (rate-limited).
- If punishments_mode is enabled, additionally calls Punishments cog to apply ladder.

NOTE: Requires MESSAGE_CONTENT intent to read message.content.
"""

CONFIG_PATH = "config.json"

# Performance / safety caps
MAX_CHECK_LEN = 4096       # Only scan the first 4096 chars; prevents worst-case CPU
MAX_PHRASES   = 200        # Cap number of phrases from env
MAX_PHRASE_LEN = 64        # Cap length per phrase

DEFAULT_FALLBACK_LIST = ["fuck you"]

# Cooldowns to prevent warning spam (seconds)
WARN_COOLDOWN_SECONDS = 15   # per-user per-channel public warning
DM_COOLDOWN_SECONDS   = 30   # per-user DM notice

# How many context words around the match to show in the snippet
SNIPPET_WORDS_BEFORE = 5
SNIPPET_WORDS_AFTER  = 5


def _utcnow() -> datetime.datetime:
    return discord.utils.utcnow()


def _load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_env_blacklist(raw: Optional[str]) -> List[str]:
    """
    Split by comma, semicolon, or newline; strip whitespace; drop empties.
    Apply caps for performance safety.
    """
    if not raw:
        return []
    parts = re.split(r"[,\n;]+", raw)
    out: List[str] = []
    for p in parts:
        s = p.strip()
        if not s:
            continue
        if len(s) > MAX_PHRASE_LEN:
            s = s[:MAX_PHRASE_LEN]
        out.append(s)
        if len(out) >= MAX_PHRASES:
            break
    return out


def _remove_zero_width(s: str) -> str:
    # Common zero-width characters attackers use to split words invisibly
    ZW = {"\u200b", "\u200c", "\u200d", "\ufeff", "\u2060"}
    return "".join(ch for ch in s if ch not in ZW)


def _normalize_content(s: str) -> str:
    """
    Normalize input to catch obfuscations:
      - Unicode NFKD
      - strip diacritics (á -> a)
      - remove zero-width chars
    """
    s = _remove_zero_width(s)
    # Decompose accents and drop combining marks
    nfkd = unicodedata.normalize("NFKD", s)
    stripped = "".join(ch for ch in nfkd if not unicodedata.combining(ch))
    return stripped


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
    - Word-ish boundaries via lookarounds to reduce false positives.
    """
    cleaned = " ".join(phrase.split())
    if not cleaned:
        return ""

    sep = r"[^a-zA-Z0-9]{0,2}"
    parts: List[str] = []

    for ch in cleaned:
        if ch.isspace():
            parts.append(sep)
        else:
            parts.append(_leet_charclass(ch))
            parts.append(sep)

    if parts and parts[-1] == sep:
        parts.pop()

    core = "".join(parts)
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


def _build_tagged_snippet(original: str, match_span: Tuple[int, int]) -> Tuple[str, int, int]:
    """
    Produce a human-friendly snippet around the match:
    - Take a few words before and after from the ORIGINAL text.
    - Replace the matched range with the token: [BLACKLISTED WORD]
    - Return (snippet, leading_hidden_chars, trailing_hidden_chars).
    The snippet is plain text (we'll wrap it in a blockquote when composing messages).
    """
    start, end = match_span
    leading_hidden = start
    trailing_hidden = max(0, len(original) - end)

    left_text = original[:start]
    right_text = original[end:]

    left_words = re.findall(r"\S+", left_text)
    right_words = re.findall(r"\S+", right_text)

    ctx_left = " ".join(left_words[-SNIPPET_WORDS_BEFORE:]) if left_words else ""
    ctx_right = " ".join(right_words[:SNIPPET_WORDS_AFTER]) if right_words else ""

    token = "[BLACKLISTED WORD]"

    left_prefix = "… " if leading_hidden > 0 else ""
    right_suffix = " …" if trailing_hidden > 0 else ""

    snippet = f"{left_prefix}{ctx_left} {token} {ctx_right}{right_suffix}".strip()
    snippet = re.sub(r"\s{2,}", " ", snippet)

    return snippet, leading_hidden, trailing_hidden


class BadWordCheck(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client

        # Load config
        self._config = _load_config()
        fc = (
            self._config.get("features", {})
            .get("filtered_chat", {})
        )
        self._enabled = bool(fc.get("enable_feature", False))
        self._omit_channels = set(str(cid) for cid in fc.get("omit_channels_id", []))
        # Punishments mode flag
        self._punishments_mode = bool(fc.get("punishments_mode", False))

        # Back-compat color (not used in plain text messages, kept for future)
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

        # Cooldowns to prevent channel/DM spam
        self._warn_cooldowns = defaultdict(float)  # user_id -> last public warn ts
        self._dm_cooldowns = defaultdict(float)    # user_id -> last DM ts

    # --------------------------- Event Handlers ---------------------------

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        await self._handle_message_filter(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        # Re-check edited messages for filter bypass
        await self._handle_message_filter(after)

    # --------------------------- Core Logic ---------------------------

    async def _handle_message_filter(self, message: discord.Message):
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

        # Length guard (performance)
        if len(content) > MAX_CHECK_LEN:
            await self.client.process_commands(message)
            return

        # If no regex (empty env & feature off, or only blanks), skip
        if not self._regex:
            await self.client.process_commands(message)
            return

        # Normalize text for matching
        normalized = _normalize_content(content)

        # Try to find a match
        m = self._regex.search(normalized)
        if not m:
            await self.client.process_commands(message)
            return

        # --- action: delete first ---
        try:
            await message.delete()
        except (discord.Forbidden, discord.HTTPException):
            pass  # we still treat it as blocked

        # Best-effort re-match on original string for accurate span
        m_orig = self._regex.search(content)
        if m_orig:
            span = m_orig.span()
        else:
            # Fallback to normalized span; if out-of-range, mask a small middle slice
            span = m.span()
            if not (0 <= span[0] < len(content)) or not (0 < span[1] <= len(content)):
                mid = min(len(content)//2, 100)
                span = (max(0, mid - 3), min(len(content), mid + 3))

        # Build tagged snippet and counts
        snippet, lead_hidden, trail_hidden = _build_tagged_snippet(content, span)

        # Rate-limited public warning (mention the user; preview as a blockquote)
        now = time.monotonic()
        last_warn = self._warn_cooldowns[message.author.id]
        if (now - last_warn) >= WARN_COOLDOWN_SECONDS:
            self._warn_cooldowns[message.author.id] = now
            warning_text = (
                f"{message.author.mention} **Prohibited language detected.** Your message was removed.\n"
                f"> ({lead_hidden} chars)… {snippet} …(+{trail_hidden} chars)\n"
                f"If you believe this is a mistake, please contact staff."
            )
            try:
                await message.channel.send(
                    warning_text,
                    allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False)
                )
            except (discord.Forbidden, discord.HTTPException):
                pass

        # Rate-limited private DM notice (also shows preview as a blockquote)
        last_dm = self._dm_cooldowns[message.author.id]
        if (now - last_dm) >= DM_COOLDOWN_SECONDS:
            self._dm_cooldowns[message.author.id] = now
            dm_text = (
                f"Hi {message.author.display_name}, your message in **#{message.channel.name}** "
                f"was removed for prohibited language.\n"
                f"> ({lead_hidden} chars)… {snippet} …(+{trail_hidden} chars)\n"
                f"If this was an error, please contact the moderators."
            )
            try:
                await message.author.send(dm_text)
            except (discord.Forbidden, discord.HTTPException):
                pass

        # ──────────────────────────────────────────────────────────────
        # Punishments integration (only if enabled in config)
        # ──────────────────────────────────────────────────────────────
        if self._punishments_mode:
            pun = self.client.get_cog("Punishments")
            if pun and getattr(pun, "enabled", False):
                try:
                    await pun.apply_action(
                        guild=message.guild,
                        moderator=self.client.user,          # system-initiated
                        target_member=message.author,
                        reason_code="harassment",            # aligns with your presets
                        custom_reason=None,
                        evidence_link=message.jump_url       # handy for staff audit
                    )
                except Exception:
                    pass

        # IMPORTANT: do NOT process commands if content was filtered.
        return


async def setup(client: commands.Bot):
    await client.add_cog(BadWordCheck(client))
