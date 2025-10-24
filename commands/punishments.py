# commands/punishments.py
import asyncio
import datetime
import json
import os
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import discord
from discord.ext import commands, tasks


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def utcnow() -> datetime.datetime:
    return discord.utils.utcnow()

def iso(dt: Optional[datetime.datetime]) -> Optional[str]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc).isoformat()

def from_iso(s: Optional[str]) -> Optional[datetime.datetime]:
    if not s:
        return None
    try:
        return discord.utils.parse_time(s)
    except Exception:
        try:
            return datetime.datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None

def atomic_write_json(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix="punish_", suffix=".json", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, separators=(",", ":"), sort_keys=False)
        os.replace(tmp, path)
    finally:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass

def human_duration(seconds: int) -> str:
    if seconds <= 0:
        return "permanent"
    mins, sec = divmod(seconds, 60)
    hours, mins = divmod(mins, 60)
    days, hours = divmod(hours, 24)
    parts = []
    if days: parts.append(f"{days}d")
    if hours: parts.append(f"{hours}h")
    if mins: parts.append(f"{mins}m")
    if sec and not parts: parts.append(f"{sec}s")
    return " ".join(parts) if parts else "0s"


# ──────────────────────────────────────────────────────────────────────────────
# Punishments Store (fast, indexed JSON)
# ──────────────────────────────────────────────────────────────────────────────

class PunishStore:
    """
    In-memory indices with atomic JSON persistence.

    Disk shape:
    {
      "cases_by_id": { case_id: CaseObj },
      "cases_by_user": { user_id: [case_id, ... newest->oldest] },
      "user_points": { user_id: { "points": float, "last_updated": ISO } },
      "meta": { "next_case_seq": int }
    }
    """
    def __init__(self, db_path: str):
        self.path = db_path
        self.cases_by_id: Dict[str, Dict[str, Any]] = {}
        self.cases_by_user: Dict[str, List[str]] = {}
        self.user_points: Dict[str, Dict[str, Any]] = {}
        self.meta: Dict[str, Any] = {"next_case_seq": 1}
        self._load()

    def _load(self):
        if not os.path.exists(self.path):
            self._persist()
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.cases_by_id = data.get("cases_by_id", {})
            self.cases_by_user = data.get("cases_by_user", {})
            self.user_points = data.get("user_points", {})
            self.meta = data.get("meta", {"next_case_seq": 1})
        except Exception:
            self.cases_by_id = {}
            self.cases_by_user = {}
            self.user_points = {}
            self.meta = {"next_case_seq": 1}
            self._persist()

    def _persist(self):
        payload = {
            "cases_by_id": self.cases_by_id,
            "cases_by_user": self.cases_by_user,
            "user_points": self.user_points,
            "meta": self.meta,
        }
        atomic_write_json(self.path, payload)

    # Public store API
    def list_recent_cases_for_guild(self, guild_id: int, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        """
        Return newest→oldest cases for a given guild. We sort by start_at desc.
        """
        items = [c for c in self.cases_by_id.values() if int(c.get("guild_id", 0)) == int(guild_id)]
        # Robust sort: fall back to created_at if start_at missing
        def _key(c):
            v = c.get("start_at") or c.get("created_at") or ""
            # ISO strings compare lexicographically fine for UTC; reverse later
            return v
        items.sort(key=_key, reverse=True)
        return items[offset : offset + max(1, min(limit, 100))]

    
    def next_case_id(self, prefix: str = "PK") -> str:
        seq = int(self.meta.get("next_case_seq", 1))
        case_id = f"{prefix}-{seq:06d}"
        self.meta["next_case_seq"] = seq + 1
        self._persist()
        return case_id

    def get_points(self, user_id: int) -> float:
        rec = self.user_points.get(str(user_id))
        return float(rec.get("points", 0.0)) if rec else 0.0

    def set_points(self, user_id: int, points: float):
        self.user_points[str(user_id)] = {"points": float(max(points, 0.0)), "last_updated": iso(utcnow())}
        self._persist()

    def incr_points(self, user_id: int, delta: float) -> float:
        cur = self.get_points(user_id)
        new = max(cur + float(delta), 0.0)
        self.set_points(user_id, new)
        return new

    def add_case(self, case: Dict[str, Any]):
        cid = case["case_id"]
        uid = str(case["user_id"])
        self.cases_by_id[cid] = case
        arr = self.cases_by_user.get(uid)
        if arr is None:
            arr = []
            self.cases_by_user[uid] = arr
        arr.insert(0, cid)  # newest first
        self._persist()

    def list_cases(self, user_id: int, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        ids = self.cases_by_user.get(str(user_id), [])
        slice_ids = ids[offset : offset + limit]
        return [self.cases_by_id[i] for i in slice_ids if i in self.cases_by_id]

    def get_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        return self.cases_by_id.get(case_id)


# ──────────────────────────────────────────────────────────────────────────────
# Cog
# ──────────────────────────────────────────────────────────────────────────────

class Punishments(commands.Cog):
    """Moderation punishments with points ladder (no decay), logging, DM, public announce, and API."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Load config.json
        with open("config.json", "r", encoding="utf-8") as f:
            self.cfg = json.load(f)

        # Config slices
        self.features = self.cfg.get("features", {})
        self.general = self.cfg.get("general", {})
        self.file_paths = self.cfg.get("file_paths", {})
        self.text_channels = self.cfg.get("text_channel_ids", {})
        self.role_ids = self.cfg.get("role_ids", {})

        self.pcfg = self.features.get("punishments", {})
        self.enabled = bool(self.pcfg.get("enable_feature", False))

        # Exemptions
        self.exempt_roles = set(self.pcfg.get("exempt_roles_id", []))
        self.exempt_users = set(self.pcfg.get("exempt_users_id", []))

        # Logging / comms
        log_cfg = self.pcfg.get("logging", {})
        self.dm_user_on_action: bool = bool(log_cfg.get("dm_user_on_action", True))
        self.log_in_bot_logs_channel: bool = bool(log_cfg.get("log_in_bot_logs_channel", True))
        self.announce_publicly: bool = bool(log_cfg.get("announce_publicly_in_bot_usage_channel", True))

        self.bot_logs_channel_id = int(self.text_channels.get("bot_logs", "0") or 0)
        self.public_usage_channel_id = int(self.text_channels.get("public_bot_usage_chat", "0") or 0)

        # Reasons / points
        r_cfg = self.pcfg.get("reasons", {})
        self.reason_presets: List[Dict[str, Any]] = r_cfg.get("presets", [])
        self.allow_custom_reason: bool = bool(r_cfg.get("allow_custom_reason", True))
        self.custom_reason_default_points: float = float(r_cfg.get("custom_reason_default_points", 1))

        # Escalation ladder (no decay)
        esc = self.pcfg.get("escalation", {})
        self.ladder: List[Dict[str, Any]] = esc.get("ladder", [])

        # Message templates
        m_cfg = self.pcfg.get("messages", {})
        self.dm_template: str = m_cfg.get("dm_template", "You received {ACTION} for {DURATION}. Reason: {REASON}. Case: {CASE_ID}.")
        self.mod_log_template: str = m_cfg.get("mod_log_template", "[{CASE_ID}] {MODERATOR} → {TARGET}: {ACTION} {DURATION} | {REASON} | Evidence: {EVIDENCE_LINK}")
        self.public_template: str = m_cfg.get("public_notice_template", "**Action:** {ACTION} • **User:** {TARGET} • **Duration:** {DURATION} • **Reason:** {REASON}")

        # DB path
        self.db_path: str = self.file_paths.get("punishments_db", "data/punishment_records.json")
        self.store = PunishStore(self.db_path)

        # Simple idempotency window to avoid double-actions when two mods click at once
        self._recent_targets: Dict[int, float] = {}  # user_id -> last action epoch
        self._idempotency_window = 5.0  # seconds

        # Maintenance loop: ONLY tempban expiry (no decay)
        self.maintenance_loop.start()

    # ───────────────────────— Internal utilities —─────────────────────────────
    
    def _case_line(self, c: Dict[str, Any]) -> str:
        dur = human_duration(int(c.get("duration_seconds", 0)))
        when = c.get("start_at", "unknown")
        uid = int(c.get("user_id", 0))
        return f"[{c['case_id']}] {c['action'].upper()} ({dur}) — <@{uid}> — {c.get('reason_text','')} — {when}"


    def _is_exempt(self, member: discord.Member) -> bool:
        if str(member.id) in self.exempt_users:
            return True
        if any(str(r.id) in self.exempt_roles for r in member.roles):
            return True
        return False

    @staticmethod
    def _has_higher_role(actor: discord.Member, target: discord.Member) -> bool:
        return actor.top_role > target.top_role

    def _resolve_reason(self, reason_code: Optional[str], custom_reason: Optional[str]) -> Tuple[str, float]:
        """
        Returns (final_reason_text, points_delta).
        """
        if reason_code:
            code = reason_code.strip().lower()
            for p in self.reason_presets:
                if p.get("code", "").lower() == code:
                    label = p.get("label") or code
                    pts = float(p.get("points", self.custom_reason_default_points))
                    return (label, pts)
        if self.allow_custom_reason and custom_reason:
            return (custom_reason.strip(), float(self.custom_reason_default_points))
        return ("Unspecified", float(self.custom_reason_default_points))

    def _pick_next_action(self, new_points: float) -> Tuple[str, int]:
        """
        Given the user's resulting points, choose action & duration from ladder.
        Assumes ladder sorted ascending by min_points.
        """
        chosen = ("warn", 0)
        for rung in self.ladder:
            mp = float(rung.get("min_points", 0))
            act = str(rung.get("action", "warn")).lower()
            dur = int(rung.get("duration_seconds", 0))
            if new_points >= mp:
                chosen = (act, dur)
            else:
                break
        return chosen

    def _channels(self, guild: discord.Guild) -> Tuple[Optional[discord.TextChannel], Optional[discord.TextChannel]]:
        bot_logs = guild.get_channel(self.bot_logs_channel_id) if self.bot_logs_channel_id else None
        public = guild.get_channel(self.public_usage_channel_id) if self.public_usage_channel_id else None
        return bot_logs, public

    async def _mod_log(self, guild: discord.Guild, content: str):
        ch, _ = self._channels(guild)
        if ch is None or not self.log_in_bot_logs_channel:
            return
        try:
            await ch.send(content, allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            pass
        
    # NEW: send a mod-log embed
    async def _send_mod_log_embed(self, guild: discord.Guild, embed: discord.Embed):
        ch, _ = self._channels(guild)
        if ch is None or not self.log_in_bot_logs_channel:
            return
        try:
            await ch.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            pass


    async def _public_announce(self, guild: discord.Guild, content: str):
        _, ch = self._channels(guild)
        if ch is None or not self.announce_publicly:
            return
        try:
            await ch.send(content, allowed_mentions=discord.AllowedMentions.none())
        except Exception:
            pass

    async def _dm_user(self, member: discord.Member, content: str) -> bool:
        if not self.dm_user_on_action:
            return False
        ok = True
        try:
            await member.send(content)
        except Exception:
            ok = False
        return ok

    def _format(self, template: str, **kwargs) -> str:
        x = {k: ("" if v is None else str(v)) for k, v in kwargs.items()}
        try:
            return template.format(**x)
        except Exception:
            return str(template)

    # ───────────────────────────── Public API ─────────────────────────────────

    def get_points(self, user_id: int) -> float:
        return self.store.get_points(user_id)

    def get_next_action(
        self,
        user_id: int,
        reason_code: Optional[str] = None,
        custom_reason: Optional[str] = None,
        points_override: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Preview the next action based on current points + delta.
        """
        reason_text, delta = self._resolve_reason(reason_code, custom_reason)
        if points_override is not None:
            delta = float(points_override)
        current = self.store.get_points(user_id)
        resulting = max(current + delta, 0.0)
        action, duration = self._pick_next_action(resulting)
        return {
            "current_points": current,
            "points_delta": delta,
            "resulting_points": resulting,
            "action": action,
            "duration_seconds": duration,
            "reason_text": reason_text,
        }

    async def apply_action(
        self,
        guild: discord.Guild,
        moderator: discord.abc.User,
        target_member: discord.Member,
        *,
        reason_code: Optional[str] = None,
        custom_reason: Optional[str] = None,
        evidence_link: Optional[str] = None,
        points_override: Optional[float] = None,
        force_action: Optional[str] = None,
        force_duration: Optional[int] = None,
        case_prefix: str = "PK",
    ) -> str:
        """
        Main entry point (other cogs call this).
        Executes action, DMs, logs, public announce, and persists case.
        """
        if not self.enabled:
            raise RuntimeError("Punishments feature disabled in config.")

        # Exemptions
        if self._is_exempt(target_member):
            raise RuntimeError("Target is exempt from automated punishments.")

        # Role hierarchy (only if moderator is a Member)
        if isinstance(moderator, discord.Member):
            if not self._has_higher_role(moderator, target_member):
                raise RuntimeError("You cannot act on a member with equal or higher role.")

        # Idempotency window
        now_epoch = utcnow().timestamp()
        last = self._recent_targets.get(target_member.id, 0.0)
        if (now_epoch - last) < self._idempotency_window:
            raise RuntimeError("Recent action already applied to this target; please wait a moment.")
        self._recent_targets[target_member.id] = now_epoch

        # Resolve reason & points
        reason_text, delta = self._resolve_reason(reason_code, custom_reason)
        if points_override is not None:
            delta = float(points_override)

        current_points = self.store.get_points(target_member.id)
        resulting_points = max(current_points + delta, 0.0)
        action, duration_seconds = self._pick_next_action(resulting_points)

        if force_action:
            action = force_action.lower()
        if force_duration is not None:
            duration_seconds = int(force_duration)

        # Build case
        case_id = self.store.next_case_id(prefix=case_prefix)
        started = utcnow()
        ends = None if duration_seconds <= 0 else started + datetime.timedelta(seconds=duration_seconds)

        # Compose comms
        # Compose comms
        duration_h = human_duration(duration_seconds)
        moderator_name = getattr(moderator, "mention", str(moderator))
        target_name = target_member.mention

        dm_text = self._format(
            self.dm_template,
            ACTION=action.upper(),
            DURATION=duration_h,
            REASON=reason_text,
            CASE_ID=case_id,
        )
        public_text = self._format(
            self.public_template,
            ACTION=action.upper(),
            TARGET=target_member.mention,
            DURATION=duration_h,
            REASON=reason_text,
        )

        # Execute moderation action (defensive) and collect any notes
        modlog_notes: List[str] = []
        try:
            if action == "warn":
                pass  # record-only

            elif action == "timeout":
                if duration_seconds <= 0:
                    duration_seconds = 60
                    ends = started + datetime.timedelta(seconds=duration_seconds)
                until = started + datetime.timedelta(seconds=duration_seconds)
                try:
                    await target_member.timeout(until, reason=f"{reason_text} | Case {case_id}")
                except AttributeError:
                    await target_member.edit(communication_disabled_until=until, reason=f"{reason_text} | Case {case_id}")

            elif action == "tempban":
                await guild.ban(target_member, reason=f"{reason_text} | Case {case_id}", delete_message_days=0)

            elif action == "ban":
                await guild.ban(target_member, reason=f"{reason_text} | Case {case_id}", delete_message_days=0)

            else:
                action = "warn"

        except discord.Forbidden:
            modlog_notes.append("⚠️ Action failed: missing permissions.")
        except discord.HTTPException as e:
            modlog_notes.append(f"⚠️ HTTP error while applying action: {e}")

        # DM user (best-effort)
        dm_success = False
        if self.dm_user_on_action:
            dm_success = await self._dm_user(target_member, dm_text)

        # Public announce (best-effort)
        public_announced = False
        if self.announce_publicly:
            await self._public_announce(guild, public_text)
            public_announced = True

        # Build rich embed for staff log
        # Color from config.general.embed_color (fallback white)
        color_hex = self.general.get("embed_color", "#ffffff")
        try:
            color_val = int(color_hex.strip("#"), 16)
        except Exception:
            color_val = 0xFFFFFF

        title_txt = f"{target_member} has been punished"
        embed = discord.Embed(title=title_txt, color=color_val, timestamp=utcnow())

        # Top author = staff member
        # Use staff avatar if present, else server icon
        author_icon = None
        if isinstance(moderator, discord.Member) and moderator.display_avatar:
            author_icon = moderator.display_avatar.url
        elif guild.icon:
            author_icon = guild.icon.url
        embed.set_author(name=str(moderator), icon_url=author_icon if author_icon else discord.Embed.Empty)

        # Corner image = punished user's avatar (thumbnail)
        try:
            if target_member.display_avatar:
                embed.set_thumbnail(url=target_member.display_avatar.url)
        except Exception:
            pass  # fine to skip

        # Core fields
        embed.add_field(name="User", value=f"{target_member.mention} (`{target_member.id}`)", inline=False)
        embed.add_field(name="Action", value=action.upper(), inline=True)
        embed.add_field(name="Duration", value=duration_h, inline=True)
        embed.add_field(name="Reason", value=reason_text or "Unspecified", inline=False)

        if evidence_link:
            embed.add_field(name="Evidence", value=evidence_link, inline=False)

        # Outcome flags
        embed.add_field(name="DM Sent", value=("Yes" if dm_success else "No"), inline=True)
        embed.add_field(name="Public Notice", value=("Yes" if public_announced else "No"), inline=True)

        # Case + moderator info
        embed.add_field(name="Case ID", value=case_id, inline=True)
        embed.add_field(name="Moderator", value=moderator_name, inline=True)

        # If temporary, show when it ends (Discord absolute timestamp)
        if ends:
            embed.add_field(name="Ends", value=f"<t:{int(ends.timestamp())}:F>", inline=False)

        # Any notes/errors captured
        if modlog_notes:
            embed.add_field(name="Notes", value="\n".join(modlog_notes)[:1000], inline=False)

        # Send to staff log as embed
        await self._send_mod_log_embed(guild, embed)

        
        

        # Persist points & case
        self.store.set_points(target_member.id, resulting_points)
        case_obj = {
            "case_id": case_id,
            "guild_id": guild.id,
            "user_id": target_member.id,
            "moderator_id": getattr(moderator, "id", 0),
            "reason_code": (reason_code or "custom"),
            "reason_text": reason_text,
            "points_delta": float(delta),
            "points_after": float(resulting_points),
            "action": action,
            "duration_seconds": int(duration_seconds),
            "start_at": iso(started),
            "end_at": iso(ends),
            "evidence_link": evidence_link or None,
            "announced_publicly": bool(public_announced),
            "dm_sent": bool(dm_success),
            "created_at": iso(utcnow()),
        }
        self.store.add_case(case_obj)

        await asyncio.sleep(0.4)  # gentle spacing if many ops happen

        return case_id

    def list_cases(self, user_id: int, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
        return self.store.list_cases(user_id, limit=limit, offset=offset)

    def get_case(self, case_id: str) -> Optional[Dict[str, Any]]:
        return self.store.get_case(case_id)

    # ───────────────────────────── Commands ───────────────────────────────────
    
    @commands.hybrid_command(
        name="punish_recent",
        with_app_command=True,
        description="Show the most recent punishment cases for this server."
    )
    @commands.has_permissions(moderate_members=True)
    async def punish_recent(self, ctx: commands.Context, limit: int = 20):
        if not self.enabled:
            return await ctx.reply("Punishments feature is disabled.", ephemeral=True if hasattr(ctx, "interaction") else False)

        limit = max(1, min(limit, 50))
        rows = self.store.list_recent_cases_for_guild(ctx.guild.id, limit=limit)

        if not rows:
            return await ctx.reply("No cases found.", ephemeral=True if hasattr(ctx, "interaction") else False)

        lines = [self._case_line(c) for c in rows]
        text = "\n".join(lines)
        if len(text) > 1900:
            text = text[:1870] + "\n… (truncated)"

        await ctx.reply(text, ephemeral=True if hasattr(ctx, "interaction") else False)

    
    @commands.hybrid_command(
        name="punish_report",
        with_app_command=True,
        description="Show a summary (totals) and the most recent cases for this server."
    )
    @commands.has_permissions(moderate_members=True)
    async def punish_report(self, ctx: commands.Context, limit: int = 20):
        if not self.enabled:
            return await ctx.reply("Punishments feature is disabled.", ephemeral=True if hasattr(ctx, "interaction") else False)

        limit = max(1, min(limit, 50))
        rows = self.store.list_recent_cases_for_guild(ctx.guild.id, limit=limit)

        # Totals by action & reason
        by_action: Dict[str, int] = {}
        by_reason: Dict[str, int] = {}
        for c in rows:
            by_action[c.get("action","unknown")] = by_action.get(c.get("action","unknown"), 0) + 1
            rtxt = c.get("reason_text","Unspecified")
            by_reason[rtxt] = by_reason.get(rtxt, 0) + 1

        # Build an embed report
        color_hex = self.general.get("embed_color", "#ffffff")
        try:
            color_val = int(color_hex.strip("#"), 16)
        except Exception:
            color_val = 0xFFFFFF

        emb = discord.Embed(
            title=f"Punishments Report — Last {len(rows)} case(s)",
            color=color_val,
            timestamp=utcnow()
        )

        # Totals by action
        if by_action:
            action_lines = [f"• **{k.upper()}**: {v}" for k, v in sorted(by_action.items(), key=lambda kv: (-kv[1], kv[0]))]
            emb.add_field(name="Totals by Action", value="\n".join(action_lines)[:1024], inline=False)

        # Top reasons (only if multiple)
        if by_reason and len(by_reason) > 1:
            reason_lines = [f"• **{k}**: {v}" for k, v in sorted(by_reason.items(), key=lambda kv: (-kv[1], kv[0]))[:10]]
            emb.add_field(name="Top Reasons", value="\n".join(reason_lines)[:1024], inline=False)

        # Recent list (compact)
        if rows:
            lines = [self._case_line(c) for c in rows]
            # Fit inside a single field; Discord 1024 char limit per field
            recent_text = "\n".join(lines)
            if len(recent_text) > 1024:
                # Truncate safely
                recent_text = recent_text[:1000] + "\n… (truncated)"
            emb.add_field(name="Most Recent", value=recent_text or "—", inline=False)
        else:
            emb.add_field(name="Most Recent", value="No cases found.", inline=False)

        # Ephemeral to staff
        await ctx.reply(embed=emb, ephemeral=True if hasattr(ctx, "interaction") else False)


    @commands.hybrid_command(name="punish_points", with_app_command=True, description="Show a user's current punishment points.")
    @commands.has_permissions(moderate_members=True)
    async def punish_points(self, ctx: commands.Context, member: discord.Member):
        if not self.enabled:
            return await ctx.reply("Punishments feature is disabled.", ephemeral=True if hasattr(ctx, "interaction") else False)
        pts = self.get_points(member.id)
        await ctx.reply(f"{member.mention} has **{pts:.2f}** points.", ephemeral=True if hasattr(ctx, "interaction") else False)

    @commands.hybrid_command(name="punish_cases", with_app_command=True, description="List recent punishment cases for a user.")
    @commands.has_permissions(moderate_members=True)
    async def punish_cases(self, ctx: commands.Context, member: discord.Member, limit: int = 10):
        if not self.enabled:
            return await ctx.reply("Punishments feature is disabled.", ephemeral=True if hasattr(ctx, "interaction") else False)
        cases = self.list_cases(member.id, limit=max(1, min(limit, 25)))
        if not cases:
            return await ctx.reply("No cases found.", ephemeral=True if hasattr(ctx, "interaction") else False)

        lines = []
        for c in cases:
            lines.append(f"[{c['case_id']}] {c['action'].upper()} ({human_duration(c['duration_seconds'])}) — {c['reason_text']} — {c['start_at']}")
        txt = "\n".join(lines)
        await ctx.reply(txt[:1900] or "No cases.", ephemeral=True if hasattr(ctx, "interaction") else False)

    @commands.hybrid_command(name="punish_case", with_app_command=True, description="Show a specific case by ID.")
    @commands.has_permissions(moderate_members=True)
    async def punish_case(self, ctx: commands.Context, case_id: str):
        if not self.enabled:
            return await ctx.reply("Punishments feature is disabled.", ephemeral=True if hasattr(ctx, "interaction") else False)
        c = self.get_case(case_id)
        if not c:
            return await ctx.reply("Case not found.", ephemeral=True if hasattr(ctx, "interaction") else False)
        text = (
            f"[{c['case_id']}] {c['action'].upper()} ({human_duration(c['duration_seconds'])})\n"
            f"User: <@{c['user_id']}> • Mod: <@{c['moderator_id']}> • When: {c['start_at']}\n"
            f"Reason: {c['reason_text']} • Points Δ: {c['points_delta']} → {c['points_after']}\n"
            f"Ends: {c['end_at'] or 'N/A'} • Evidence: {c.get('evidence_link') or 'N/A'}\n"
            f"DM: {'yes' if c.get('dm_sent') else 'no'} • Public: {'yes' if c.get('announced_publicly') else 'no'}"
        )
        await ctx.reply(text[:1900], ephemeral=True if hasattr(ctx, "interaction") else False)

    @commands.hybrid_command(name="punish_warn", with_app_command=True, description="Warn a user (adds points and logs).")
    @commands.has_permissions(moderate_members=True)
    async def punish_warn(self, ctx: commands.Context, member: discord.Member, reason_code: Optional[str] = None, *, custom_reason: Optional[str] = None):
        if not self.enabled:
            return await ctx.reply("Punishments feature is disabled.", ephemeral=True if hasattr(ctx, "interaction") else False)
        try:
            cid = await self.apply_action(ctx.guild, ctx.author, member, reason_code=reason_code, custom_reason=custom_reason)
            await ctx.reply(f"Warned {member.mention}. Case `{cid}`.", ephemeral=True if hasattr(ctx, "interaction") else False)
        except Exception as e:
            await ctx.reply(f"Failed: {e}", ephemeral=True if hasattr(ctx, "interaction") else False)

    @commands.hybrid_command(name="punish_timeout", with_app_command=True, description="Timeout a user for a given number of seconds.")
    @commands.has_permissions(moderate_members=True)
    async def punish_timeout(self, ctx: commands.Context, member: discord.Member, duration_seconds: int, reason_code: Optional[str] = None, *, custom_reason: Optional[str] = None):
        if not self.enabled:
            return await ctx.reply("Punishments feature is disabled.", ephemeral=True if hasattr(ctx, "interaction") else False)
        try:
            cid = await self.apply_action(ctx.guild, ctx.author, member, reason_code=reason_code, custom_reason=custom_reason, force_action="timeout", force_duration=duration_seconds)
            await ctx.reply(f"Timed out {member.mention} for {human_duration(duration_seconds)}. Case `{cid}`.", ephemeral=True if hasattr(ctx, "interaction") else False)
        except Exception as e:
            await ctx.reply(f"Failed: {e}", ephemeral=True if hasattr(ctx, "interaction") else False)

    @commands.hybrid_command(name="punish_tempban", with_app_command=True, description="Temp-ban a user for a given number of seconds.")
    @commands.has_permissions(ban_members=True)
    async def punish_tempban(self, ctx: commands.Context, member: discord.Member, duration_seconds: int, reason_code: Optional[str] = None, *, custom_reason: Optional[str] = None):
        if not self.enabled:
            return await ctx.reply("Punishments feature is disabled.", ephemeral=True if hasattr(ctx, "interaction") else False)
        try:
            cid = await self.apply_action(ctx.guild, ctx.author, member, reason_code=reason_code, custom_reason=custom_reason, force_action="tempban", force_duration=duration_seconds)
            await ctx.reply(f"Temp-banned {member.mention} for {human_duration(duration_seconds)}. Case `{cid}`.", ephemeral=True if hasattr(ctx, "interaction") else False)
        except Exception as e:
            await ctx.reply(f"Failed: {e}", ephemeral=True if hasattr(ctx, "interaction") else False)

    @commands.hybrid_command(name="punish_ban", with_app_command=True, description="Ban a user permanently.")
    @commands.has_permissions(ban_members=True)
    async def punish_ban(self, ctx: commands.Context, member: discord.Member, reason_code: Optional[str] = None, *, custom_reason: Optional[str] = None):
        if not self.enabled:
            return await ctx.reply("Punishments feature is disabled.", ephemeral=True if hasattr(ctx, "interaction") else False)
        try:
            cid = await self.apply_action(ctx.guild, ctx.author, member, reason_code=reason_code, custom_reason=custom_reason, force_action="ban", force_duration=0)
            await ctx.reply(f"Banned {member.mention}. Case `{cid}`.", ephemeral=True if hasattr(ctx, "interaction") else False)
        except Exception as e:
            await ctx.reply(f"Failed: {e}", ephemeral=True if hasattr(ctx, "interaction") else False)

    @commands.hybrid_command(name="punish_unban", with_app_command=True, description="Unban a user by ID.")
    @commands.has_permissions(ban_members=True)
    async def punish_unban(self, ctx: commands.Context, user_id: int, *, reason: Optional[str] = None):
        if not self.enabled:
            return await ctx.reply("Punishments feature is disabled.", ephemeral=True if hasattr(ctx, "interaction") else False)
        user = discord.Object(id=user_id)
        try:
            await ctx.guild.unban(user, reason=reason or "Manual unban")
            # Record unban case with zero delta
            case_id = self.store.next_case_id(prefix="PK")
            self.store.add_case({
                "case_id": case_id,
                "guild_id": ctx.guild.id,
                "user_id": user_id,
                "moderator_id": ctx.author.id,
                "reason_code": "unban",
                "reason_text": reason or "Unban",
                "points_delta": 0.0,
                "points_after": self.store.get_points(user_id),
                "action": "unban",
                "duration_seconds": 0,
                "start_at": iso(utcnow()),
                "end_at": None,
                "evidence_link": None,
                "announced_publicly": False,
                "dm_sent": False,
                "created_at": iso(utcnow()),
            })
            await self._mod_log(ctx.guild, f"[{case_id}] {ctx.author.mention} unbanned <@{user_id}>")
            await ctx.reply(f"Unbanned <@{user_id}>. Case `{case_id}`.", ephemeral=True if hasattr(ctx, "interaction") else False)
        except Exception as e:
            await ctx.reply(f"Failed: {e}", ephemeral=True if hasattr(ctx, "interaction") else False)

    @commands.hybrid_command(name="punish_reload", with_app_command=True, description="Reload punishments config.json (light reload).")
    @commands.has_permissions(administrator=True)
    async def punish_reload(self, ctx: commands.Context):
        try:
            with open("config.json", "r", encoding="utf-8") as f:
                new_cfg = json.load(f)
            self.cfg = new_cfg
            self.features = self.cfg.get("features", {})
            self.pcfg = self.features.get("punishments", {})
            self.enabled = bool(self.pcfg.get("enable_feature", False))
            await ctx.reply("Punishments config reloaded.", ephemeral=True if hasattr(ctx, "interaction") else False)
        except Exception as e:
            await ctx.reply(f"Reload failed: {e}", ephemeral=True if hasattr(ctx, "interaction") else False)

    # ───────────────────────── Maintenance loop ───────────────────────────────
    # No decay; only auto-unban expired tempbans.

    @tasks.loop(minutes=10)
    async def maintenance_loop(self):
        if not self.enabled:
            return
        try:
            now = utcnow()
            # Find tempbans whose end_at is in the past → unban
            for case_id, c in list(self.store.cases_by_id.items()):
                if c.get("action") != "tempban":
                    continue
                end_at = from_iso(c.get("end_at"))
                if not end_at or end_at > now:
                    continue

                guild = self.bot.get_guild(c.get("guild_id"))
                if not guild:
                    continue

                # Check if still banned (avoid errors if already unbanned)
                try:
                    bans = await guild.bans()
                    if not any(e.user.id == int(c["user_id"]) for e in bans):
                        continue
                except Exception:
                    continue

                # Unban
                try:
                    await guild.unban(discord.Object(id=int(c["user_id"])), reason=f"Tempban expired (Case {case_id})")
                    auto_case_id = self.store.next_case_id(prefix="PK")
                    self.store.add_case({
                        "case_id": auto_case_id,
                        "guild_id": guild.id,
                        "user_id": int(c["user_id"]),
                        "moderator_id": self.bot.user.id if self.bot.user else 0,
                        "reason_code": "auto_unban",
                        "reason_text": f"Tempban expired (from {case_id})",
                        "points_delta": 0.0,
                        "points_after": self.store.get_points(int(c["user_id"])),
                        "action": "unban",
                        "duration_seconds": 0,
                        "start_at": iso(utcnow()),
                        "end_at": None,
                        "evidence_link": None,
                        "announced_publicly": False,
                        "dm_sent": False,
                        "created_at": iso(utcnow()),
                    })
                    await self._mod_log(guild, f"[{auto_case_id}] Auto-unbanned <@{c['user_id']}> (expired tempban {case_id})")
                    await asyncio.sleep(0.4)
                except Exception:
                    continue

        except Exception:
            # Never let an exception kill the loop
            return

    @maintenance_loop.before_loop
    async def before_maintenance_loop(self):
        await self.bot.wait_until_ready()


# ──────────────────────────────────────────────────────────────────────────────
# Setup
# ──────────────────────────────────────────────────────────────────────────────

async def setup(bot: commands.Bot):
    await bot.add_cog(Punishments(bot))
