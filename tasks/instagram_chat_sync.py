# tasks/instagram_chat_sync.py
import os
import json
import asyncio
import random
import datetime
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord.ext import commands, tasks

# Unofficial IG lib (⚠️ ToS risk; use at your own risk)
from instagrapi import Client
from instagrapi.exceptions import DirectThreadNotFound

# Optional .env loader for INSTAGRAM_USERNAME / INSTAGRAM_PASSWORD
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Use a module logger with a NullHandler (no root/basicConfig here)
import logging
log = logging.getLogger(__name__)
if not log.handlers:
    log.addHandler(logging.NullHandler())


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(tz=datetime.timezone.utc)


# ---------- Small JSON helpers (atomic write) ----------
def _read_json(path: str, default: Any) -> Any:
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json_atomic(path: str, payload: Any) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# ---------- Interaction-safe responder (avoids 10062) ----------
async def _safe_reply(ctx: commands.Context, content: Optional[str] = None, *, ephemeral: bool = True, **kwargs):
    try:
        if getattr(ctx, "interaction", None) and not ctx.interaction.response.is_done():
            await ctx.interaction.response.send_message(content=content, ephemeral=ephemeral, **kwargs)
        elif getattr(ctx, "interaction", None):
            await ctx.interaction.followup.send(content=content, ephemeral=ephemeral, **kwargs)
        else:
            await ctx.reply(content=content, **kwargs)
    except Exception:
        try:
            await ctx.send(content or "Done.", **kwargs)
        except Exception:
            pass


class InstagramDMChatSync(commands.Cog):
    """
    Inbox-only DM chat sync between ONE Instagram thread and ONE Discord text channel.

    Config (config.json):
      - features.instagram_sync.dm_chat_sync:
          enable_feature: bool
          chat_thread_id: str
          discord_to_instagram: bool
          instagram_to_discord: bool
          poll_interval_seconds: int
          max_messages_per_poll: int
      - features.instagram_sync.logging.debug_to_console: bool
      - text_channel_ids.instagram_chat_sync: str (Discord channel ID)
      - file_paths.instagram_db: str (single DB file for all Instagram features)

    Credentials: .env -> INSTAGRAM_USERNAME / INSTAGRAM_PASSWORD
    """

    # IG user to ignore (no mirroring to Discord)
    IG_IGNORE_USER_ID = 73979742685

    # Small grace period after bot is ready (ensures full boot before first poll)
    BOOT_GRACE_SECONDS = 5

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Quiet down noisy third-party loggers regardless of global config
        for name in ("instagrapi", "instagrapi.http", "instagrapi.mixins", "urllib3", "httpx", "requests"):
            lg = logging.getLogger(name)
            lg.setLevel(logging.ERROR)
            lg.propagate = False

        # Load config.json
        self.cfg: Dict[str, Any] = _read_json("config.json", {})
        features = self.cfg.get("features", {}).get("instagram_sync", {})
        dm_cfg = features.get("dm_chat_sync", {}) or {}
        logging_cfg = features.get("logging", {}) or {}

        self.enabled: bool = bool(dm_cfg.get("enable_feature", False))
        self.thread_id: str = (dm_cfg.get("chat_thread_id") or "").strip()
        self.ig_to_dc: bool = bool(dm_cfg.get("instagram_to_discord", True))
        self.dc_to_ig: bool = bool(dm_cfg.get("discord_to_instagram", True))
        self.poll_interval: int = int(dm_cfg.get("poll_interval_seconds", 60))
        self.window_size: int = int(dm_cfg.get("max_messages_per_poll", 50))

        # Console logging toggle (true = print, false = stay quiet)
        self.debug_console: bool = bool(logging_cfg.get("debug_to_console", False))

        # Channel & DB path
        text_ids = self.cfg.get("text_channel_ids", {}) or {}
        self.sync_channel_id: int = int(text_ids.get("instagram_chat_sync", "0") or "0")

        file_paths = self.cfg.get("file_paths", {}) or {}
        self.db_path: str = file_paths.get("instagram_db", "data/instagram_db.json")

        # .env credentials
        self.ig_user = (os.getenv("INSTAGRAM_USERNAME") or "").strip()
        self.ig_pass = (os.getenv("INSTAGRAM_PASSWORD") or "").strip()

        # In-memory DB (read once, then kept in sync)
        self.db: Dict[str, Any] = _read_json(self.db_path, {}) or {}
        self.db.setdefault("session", {})
        self.db.setdefault("dm_sync", {})
        self.db.setdefault("posts_sync", {})
        self.db.setdefault("meta", {})

        # Slots we use often (minimal persistence)
        self.db["dm_sync"].setdefault("thread_id", self.thread_id)
        self.db["dm_sync"].setdefault("last_seen_message_id", "0")
        self.db["dm_sync"].setdefault("participants", [])
        self._last_error: Optional[str] = None

        # IG client + locks/backoff
        self.cl: Optional[Client] = None
        self._login_lock = asyncio.Lock()
        self._backoff_seconds = 0  # dynamic backoff on errors

        # Outbound (Discord → IG) throttling
        self._user_last_sent: Dict[int, float] = {}     # discord user id -> last epoch time
        self._global_last_sent: float = 0.0
        self._user_cooldown = 5.0                       # seconds between user's messages to IG
        self._global_cooldown = 1.0                     # seconds between any messages to IG

        # Cached thread title (for startup announcement)
        self._thread_title: str = "(Instagram Group)"

        # Start background poller only if enabled
        if self.enabled:
            self.poll_loop.change_interval(seconds=max(5, self.poll_interval))
            self.poll_loop.start()
        else:
            self._log("instagram_sync.dm_chat_sync disabled; poll loop not started.", important=True)

    # --------------- Utility Logging ---------------
    def _log(self, msg: str, important: bool = False):
        """
        Only prints when:
          - important=True, OR
          - debug_to_console=True
        Never configures root logger; uses module logger instead.
        """
        if important or self.debug_console:
            try:
                log.info(msg)
            except Exception:
                pass

    def _save_db(self):
        self.db["dm_sync"]["thread_id"] = self.thread_id  # keep in sync
        self.db["meta"]["last_poll_at"] = _utcnow().isoformat()
        self.db["meta"]["last_error"] = self._last_error
        _write_json_atomic(self.db_path, self.db)

    # --------------- Commands ---------------
    @commands.hybrid_command(name="ig_status", description="Show Instagram DM chat sync status.")
    @commands.has_permissions(moderate_members=True)
    async def ig_status(self, ctx: commands.Context):
        dm = self.db.get("dm_sync", {})
        parts = dm.get("participants", [])
        last_seen = dm.get("last_seen_message_id", "0")
        meta = self.db.get("meta", {})
        last_poll = meta.get("last_poll_at") or "n/a"
        last_error = meta.get("last_error") or "n/a"

        txt = (
            f"**IG DM Chat Sync Status**\n"
            f"- Enabled: `{self.enabled}`\n"
            f"- IG → Discord: `{self.ig_to_dc}`\n"
            f"- Discord → IG: `{self.dc_to_ig}`\n"
            f"- Thread ID: `{self.thread_id or 'not set'}`\n"
            f"- Poll interval: `{self.poll_interval}s` • Window: `{self.window_size}`\n"
            f"- Backoff: `{self._backoff_seconds}s`\n"
            f"- Participants cached: `{len(parts)}`\n"
            f"- Last seen message id: `{last_seen}`\n"
            f"- Last poll at (UTC): `{last_poll}`\n"
            f"- Last error: `{last_error}`\n"
            f"- DB file: `{self.db_path}`\n"
            f"- Discord channel: `{self.sync_channel_id}`\n"
        )
        await _safe_reply(ctx, txt, ephemeral=True)

    @commands.hybrid_command(name="ig_fetch_recent", description="Fetch and display last N messages from the IG thread (without storing).")
    @commands.has_permissions(moderate_members=True)
    async def ig_fetch_recent(self, ctx: commands.Context, count: int = 10):
        count = max(1, min(int(count), 50))
        if not self.thread_id:
            return await _safe_reply(ctx, "Thread is not set.", ephemeral=True)
        ok = await self._ensure_client()
        if not ok:
            return await _safe_reply(ctx, "Instagram login failed. Check console for details.", ephemeral=True)

        # Fetch participants for name lookup
        try:
            thread = await asyncio.to_thread(self.cl.direct_thread, self.thread_id)
            users = thread.users or []
        except Exception as e:
            return await _safe_reply(ctx, f"Failed to fetch thread: {e!r}", ephemeral=True)

        # Fetch messages (newest first), slice count
        try:
            msgs = await asyncio.to_thread(self.cl.direct_messages, self.thread_id, amount=count)
        except Exception as e:
            return await _safe_reply(ctx, f"Failed to fetch messages: {e!r}", ephemeral=True)

        # Post newest → oldest as embeds (ignore blocked user)
        ch = self.bot.get_channel(self.sync_channel_id)
        for m in msgs:
            author_id = getattr(m, "user_id", None)
            if int(author_id or 0) == self.IG_IGNORE_USER_ID:
                continue

            uname = None
            for u in users:
                if int(getattr(u, "pk", 0)) == int(author_id or 0):
                    uname = getattr(u, "username", None)
                    break
            text = getattr(m, "text", None) or ""
            item_type = getattr(m, "item_type", None)

            await self._send_discord_embed(uname or f"user_id:{author_id}", text, ch, item_type=item_type, recent_fetch=True)
            await asyncio.sleep(0.15)

        await _safe_reply(ctx, f"Posted last {len(msgs)} message(s) from IG.", ephemeral=True)

    # --------------- Background Poller ---------------
    @tasks.loop(seconds=60)
    async def poll_loop(self):
        # fast guards
        if not self.enabled:
            return
        if not self.ig_user or not self.ig_pass:
            self._last_error = "Missing INSTAGRAM_USERNAME/PASSWORD"
            self._save_db()
            self._log("Missing IG credentials; skipping poll.", important=True)
            return
        if not self.thread_id:
            self._last_error = "Thread ID not set"
            self._save_db()
            self._log("No IG thread set; skipping poll.", important=True)
            return

        # Respect backoff if set
        if self._backoff_seconds > 0:
            await asyncio.sleep(self._backoff_seconds)

        # Ensure IG client
        ok = await self._ensure_client()
        if not ok:
            self._save_db()
            return

        try:
            # On first run, prime last_seen to newest to avoid history spam.
            first_boot = (self.db["dm_sync"].get("last_seen_message_id", "0") == "0")
            await self._sync_thread_once(prime_only=first_boot)
            if first_boot:
                # Announce live in Discord only (no Instagram-side announcement)
                await self._announce_live_discord_only()
            self._last_error = None
            self._backoff_seconds = 0
        except DirectThreadNotFound:
            self._last_error = "Thread not found (404). Check chat_thread_id."
            self._backoff_seconds = min(max(30, self.poll_interval), 600)
        except Exception as e:
            self._last_error = repr(e)
            self._backoff_seconds = min(max(10, int(self._backoff_seconds * 2) or 15), 600)

        self._save_db()

    @poll_loop.before_loop
    async def before_loop(self):
        # Wait for full bot readiness, then a short grace period
        await self.bot.wait_until_ready()
        await asyncio.sleep(self.BOOT_GRACE_SECONDS)
        self.poll_loop.change_interval(seconds=max(5, self.poll_interval))
        self._log("Instagram DM chat sync loop started.", important=True)

    # --------------- Discord → Instagram listener ---------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Only when enabled and dc->ig is true
        if not self.enabled or not self.dc_to_ig:
            return
        if message.author.bot or message.webhook_id is not None:
            return
        if not isinstance(message.channel, discord.TextChannel):
            return
        if message.channel.id != self.sync_channel_id:
            return

        content = (message.content or "").strip()
        if not content:
            return

        # Rate limits: per-user + global
        now = asyncio.get_event_loop().time()
        last_user = getattr(self, "_user_last_sent", {}).get(message.author.id, 0.0)
        if now - last_user < self._user_cooldown:
            return
        if now - self._global_last_sent < self._global_cooldown:
            return

        ok = await self._ensure_client()
        if not ok or not self.thread_id:
            return  # silent

        out = f"[Discord] {message.author.display_name} \u2192 {content}"
        await asyncio.sleep(random.uniform(0.25, 0.6))
        try:
            await asyncio.to_thread(self.cl.direct_send, text=out, thread_ids=[self.thread_id])
            # stamp cooldowns
            self._user_last_sent[message.author.id] = now
            self._global_last_sent = now
        except Exception:
            pass  # silent

    # --------------- IG internals ---------------
    async def _ensure_client(self) -> bool:
        """Create/login the instagrapi Client once, reusing cached session from DB if present."""
        async with self._login_lock:
            if self.cl is not None:
                return True

            if not self.ig_user or not self.ig_pass:
                return False

            cl = Client()

            # Try restore session settings from DB
            sess = self.db.get("session", {}).get("settings")
            if sess:
                try:
                    await asyncio.to_thread(cl.set_settings, sess)
                except Exception:
                    pass

            try:
                await asyncio.to_thread(cl.login, self.ig_user, self.ig_pass)
            except Exception:
                # Try once with fresh settings
                try:
                    await asyncio.to_thread(cl.set_settings, {})
                    await asyncio.to_thread(cl.login, self.ig_user, self.ig_pass)
                except Exception:
                    return False

            # Save session into same DB file
            try:
                settings_obj = await asyncio.to_thread(cl.get_settings)
                self.db.setdefault("session", {})["settings"] = settings_obj
                self.db["session"]["last_login_at"] = _utcnow().isoformat()
                self._save_db()
            except Exception:
                pass

            self.cl = cl
            return True

    async def _announce_live_discord_only(self):
        """Post once on startup: Discord-only live message; also caches title & participants."""
        ch = self.bot.get_channel(self.sync_channel_id)
        if not isinstance(ch, discord.TextChannel):
            return

        # Fetch thread for title + participants
        title, part_count = "(Instagram Group)", 0
        try:
            thread = await asyncio.to_thread(self.cl.direct_thread, self.thread_id)
            title = getattr(thread, "thread_title", None) or title
            users = thread.users or []
            part_count = len(users)
            self._thread_title = title
            # cache participants into DB (handy for names)
            self.db["dm_sync"]["participants"] = [
                {"user_id": int(getattr(u, "pk", 0)), "username": getattr(u, "username", None), "full_name": getattr(u, "full_name", None)}
                for u in users
            ]
            self._save_db()
        except Exception:
            self._thread_title = title

        # Discord announcement only
        try:
            await ch.send(
                f"🔗 Instagram chat sync for **{self._thread_title}** with **{part_count}** participants is now live.",
                allowed_mentions=discord.AllowedMentions.none()
            )
        except Exception:
            pass

    async def _sync_thread_once(self, prime_only: bool = False):
        """
        Fetch newest messages, set last_seen on first run (prime_only).
        Otherwise mirror only NEW messages IG → Discord (as embeds), handle polls, and advance last_seen.
        """
        if self.cl is None:
            return

        # Pull a small window
        amount = max(1, min(int(self.window_size), 50))
        msgs = await asyncio.to_thread(self.cl.direct_messages, self.thread_id, amount=amount)

        # Load last seen id
        last_seen = str(self.db["dm_sync"].get("last_seen_message_id", "0"))

        # On prime, set last_seen to newest and bail (no mirroring)
        if prime_only:
            newest = None
            for m in msgs:
                mid = str(getattr(m, "id", getattr(m, "pk", "")) or "")
                if mid and (newest is None or mid > newest):
                    newest = mid
            if newest:
                self.db["dm_sync"]["last_seen_message_id"] = newest
            return

        # Otherwise, process only NEW items (oldest→newest)
        try:
            thread = await asyncio.to_thread(self.cl.direct_thread, self.thread_id)
            users = thread.users or []
            # update cached title just in case it changed
            self._thread_title = getattr(thread, "thread_title", None) or self._thread_title
        except Exception:
            users = []

        new_items: List[Tuple[str, Any]] = []  # (item_type, message_obj)
        for m in reversed(msgs):
            mid = str(getattr(m, "id", getattr(m, "pk", "")) or "")
            if not mid:
                continue
            if mid <= last_seen:
                continue
            new_items.append((getattr(m, "item_type", None), m))

        if not new_items:
            return

        ch = self.bot.get_channel(self.sync_channel_id)
        if not isinstance(ch, discord.TextChannel):
            # Still advance last_seen to avoid repeats if channel missing
            newest_id = str(getattr(new_items[-1][1], "id", getattr(new_items[-1][1], "pk", "")) or last_seen)
            if newest_id:
                self.db["dm_sync"]["last_seen_message_id"] = newest_id
            return

        # Mirror new items
        for item_type, m in new_items:
            author_id = getattr(m, "user_id", None)

            # Ignore specific IG user
            if int(author_id or 0) == self.IG_IGNORE_USER_ID:
                continue

            uname = None
            for u in users:
                if int(getattr(u, "pk", 0)) == int(author_id or 0):
                    uname = getattr(u, "username", None)
                    break
            uname = uname or f"user_id:{author_id}"

            if item_type == "text":
                text = getattr(m, "text", None) or ""
                await self._send_discord_embed(uname, text, ch)
            else:
                # Heuristic for poll-like items
                if str(item_type).lower() in {"poll", "poll_vote", "story_poll", "story_poll_vote", "action_log"}:
                    note = f"**{uname}** voted in a group poll."
                    try:
                        await ch.send(note, allowed_mentions=discord.AllowedMentions.none())
                    except Exception:
                        pass
                # else: ignore for now

            await asyncio.sleep(random.uniform(0.12, 0.3))

        # Advance last_seen
        newest_id = str(getattr(new_items[-1][1], "id", getattr(new_items[-1][1], "pk", "")) or last_seen)
        if newest_id:
            self.db["dm_sync"]["last_seen_message_id"] = newest_id

    async def _send_discord_embed(
        self,
        ig_username: str,
        text: str,
        ch: Optional[discord.TextChannel],
        *,
        item_type: Optional[str] = None,
        recent_fetch: bool = False
    ):
        """Send an embed for an IG text message with only a description (no author/timestamp/icons)."""
        if not ch:
            return

        # Discord hard cap is 4096 chars in description; clip just in case.
        body = (text or "")
        if len(body) > 4096:
            body = body[:4093] + "..."

        # Your requested format:
        # **[INSTA] {instagram username}** ➜ {message}
        desc = f"**[INSTA] {ig_username}** ➜ {body}"

        embed = discord.Embed(
            description=desc,
            colour=discord.Colour.blurple() if not recent_fetch else discord.Colour.dark_grey()
        )
        # No set_author, no timestamp, no images/icons.

        try:
            await ch.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            pass


async def setup(bot: commands.Bot):
    await bot.add_cog(InstagramDMChatSync(bot))
