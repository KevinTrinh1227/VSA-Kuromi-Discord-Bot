# commands/poll.py

import discord
from discord.ext import commands
from discord.ui import View, Button
import asyncio
import datetime
import json
import re
import os

# config
with open('config.json') as f:
    cfg = json.load(f)
FAMILY_ROLE_ID = int(cfg['role_ids']['family_member'])
STAFF_ROLE_ID = int(cfg['role_ids']['staff_member'])
TRANSCRIPTS_CHANNEL_ID = int(cfg['text_channel_ids']['bot_logs'])
POLL_STORE = cfg['file_paths']['server_polls']

# emoji numbers
NUMBER_EMOJIS = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]

# duration parser
def parse_duration(duration_str: str) -> int:
    units = {'d':86400,'h':3600,'m':60,'s':1}
    total = 0
    parts = duration_str.split()
    if not parts:
        raise ValueError("Duration is empty.")
    for part in parts:
        m = re.fullmatch(r"(\d+)([dhms])", part.lower())
        if not m:
            raise ValueError(f"Invalid token '{part}'")
        amt, unit = m.groups()
        total += int(amt) * units[unit]
    if total <= 0:
        raise ValueError("Duration must be positive.")
    return total

# helper store
def load_polls():
    if os.path.exists(POLL_STORE):
        return json.load(open(POLL_STORE))
    return {}

def save_polls(data):
    json.dump(data, open(POLL_STORE, 'w'), indent=2)

class PollView(View):
    def __init__(self, data: dict, persistent: bool = False):
        expires = datetime.datetime.fromisoformat(data['expires_at'])
        timeout = None if persistent else max((expires - datetime.datetime.now()).total_seconds(), 0)
        super().__init__(timeout=timeout)
        self.data = data
        self.data.setdefault('votes', {opt: [] for opt in data['options']})
        # option buttons
        for idx, opt in enumerate(data['options']):
            emoji = NUMBER_EMOJIS[idx]
            btn = Button(custom_id=f"poll_opt_{idx}", emoji=emoji, style=discord.ButtonStyle.secondary)
            btn.callback = self._make_cb(opt)
            self.add_item(btn)
        # remove vote button
        rem = Button(custom_id='poll_remove', label='❌ Remove Vote', style=discord.ButtonStyle.danger)
        rem.callback = self._remove_cb
        self.add_item(rem)
        # close poll button
        clo = Button(custom_id='poll_close', label='🔒 Close Poll', style=discord.ButtonStyle.primary)
        clo.callback = self._close_cb
        self.add_item(clo)

    def _persist(self):
        polls = load_polls()
        polls[str(self.data['message_id'])] = self.data
        save_polls(polls)

    def _make_cb(self, opt):
        async def cb(inter: discord.Interaction):
            uid = inter.user.id
            # remove old votes
            for lst in self.data['votes'].values():
                if uid in lst:
                    lst.remove(uid)
            # add new vote
            self.data['votes'][opt].append(uid)
            self._persist()
            await inter.response.edit_message(embed=self.build_embed(), view=self)
        return cb

    async def _remove_cb(self, inter: discord.Interaction):
        uid = inter.user.id
        changed = False
        for lst in self.data['votes'].values():
            if uid in lst:
                lst.remove(uid)
                changed = True
        if changed:
            self._persist()
            await inter.response.edit_message(embed=self.build_embed(), view=self)
        else:
            await inter.response.defer()

    async def _close_cb(self, inter: discord.Interaction):
        if not inter.user.guild_permissions.manage_messages:
            return await inter.response.send_message("🚫 You lack permission to close.", ephemeral=True)
        self.stop()
        msg_id = str(self.data['message_id'])
        polls = load_polls()
        polls.pop(msg_id, None)
        save_polls(polls)
        for c in self.children:
            c.disabled = True
        await inter.response.edit_message(embed=self.build_embed(final=True), view=self)
        await self._send_transcript(inter)

    def build_embed(self, final: bool = False) -> discord.Embed:
        q = self.data['question']
        votes = self.data['votes']
        total = sum(len(v) for v in votes.values())
        expires = datetime.datetime.fromisoformat(self.data['expires_at'])
        exp_str = expires.strftime('%b %d, %Y %I:%M %p CST')
        lines = []
        for idx, opt in enumerate(self.data['options'], start=1):
            cnt = len(votes[opt])
            pct = (cnt / total * 100) if total else 0.0
            lines.append(f"{idx}. {opt} — {cnt} vote(s) — {pct:.1f}%")
        desc = (
            f"Please click the corresponding button to vote. Only 1 vote allowed. **Expires {exp_str}.**\n\n"
            + "\n".join(lines)
        )
        emb = discord.Embed(
            title=f"📊 | {q}",
            description=desc,
            color=discord.Color.green(),
            timestamp=(expires if final else datetime.datetime.now())
        )
        emb.set_footer(text=f"Total votes: {total} • Expires: {exp_str}")
        return emb

    async def _send_transcript(self, inter: discord.Interaction):
        guild = inter.guild
        staff = guild.get_role(STAFF_ROLE_ID)
        votes = self.data['votes']
        total = sum(len(v) for v in votes.values())
        created = datetime.datetime.fromisoformat(self.data.get('created_at', self.data['expires_at']))
        expires = datetime.datetime.fromisoformat(self.data['expires_at'])
        duration = expires - created
        emb = discord.Embed(
            title=f"📊 Results: {self.data['question']}",
            color=discord.Color.gold(),
            timestamp=datetime.datetime.utcnow()
        )
        # detailed per-option stats
        for idx, opt in enumerate(self.data['options'], start=1):
            vl = votes[opt]
            cnt = len(vl)
            pct = (cnt / total * 100) if total else 0.0
            fam_count = sum(1 for u in vl if guild.get_member(u) and any(r.id == FAMILY_ROLE_ID for r in guild.get_member(u).roles))
            fam_pct = (fam_count / cnt * 100) if cnt else 0.0
            mentions = ", ".join(f"<@{u}>" for u in vl) or "None"
            emb.add_field(
                name=f"{idx}. {opt}",
                value=(f"• Total Votes: {cnt} ({pct:.1f}%)\n"
                       f"• Family Votes: {fam_count} ({fam_pct:.1f}%)\n"
                       f"• Users: {mentions}"),
                inline=False
            )
        fam_total = sum(1 for vl in votes.values() for u in vl if guild.get_member(u) and any(r.id == FAMILY_ROLE_ID for r in guild.get_member(u).roles))
        most_total = max(votes.items(), key=lambda kv: len(kv[1]))[0] if votes else "None"
        most_fam = max(votes.items(), key=lambda kv: sum(1 for u in kv[1] if guild.get_member(u) and any(r.id == FAMILY_ROLE_ID for r in guild.get_member(u).roles)))[0] if votes else "None"
        emb.add_field(name="Misc Stats", value=(
            f"• Most Votes Overall: {most_total}\n"
            f"• Most Votes (Family): {most_fam}\n"
            f"• Poll Duration: {duration}"),
            inline=False
        )
        ch = guild.get_channel(TRANSCRIPTS_CHANNEL_ID)
        await ch.send(f"{staff.mention}", embed=emb)

class Polls(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.loop.create_task(self._load_polls())

    async def _load_polls(self):
        await self.bot.wait_until_ready()
        polls = load_polls()
        now = datetime.datetime.now()
        for msg_id, data in polls.items():
            expires = datetime.datetime.fromisoformat(data['expires_at'])
            if expires <= now:
                continue
            ch = self.bot.get_channel(data['channel_id'])
            try:
                msg = await ch.fetch_message(int(msg_id))
            except:
                continue
            view = PollView(data, persistent=True)
            self.bot.add_view(view, message_id=int(msg_id))
            rem = (expires - now).total_seconds()
            self.bot.loop.create_task(self._schedule_close(view, msg, rem))

    async def _schedule_close(self, view, msg, delay):
        await asyncio.sleep(delay)
        if not view.is_finished():
            view.stop()
            for c in view.children:
                c.disabled = True
            await msg.edit(embed=view.build_embed(final=True), view=view)
            fake_ctx = await self.bot.get_context(msg)
            await view._send_transcript(fake_ctx)

    @commands.has_permissions(manage_messages=True)
    @commands.hybrid_command(name="poll", description="Create persistent poll")
    async def poll(self, ctx, channel: discord.TextChannel, question: str, duration: str, role: discord.Role = None, *, options: str):
        try:
            timeout = parse_duration(duration)
        except ValueError as e:
            return await ctx.send(f"🚫 {e}", ephemeral=True)
        opts = [o.strip() for o in options.split(';') if o.strip()]
        if not (2 <= len(opts) <= len(NUMBER_EMOJIS)):
            return await ctx.send(f"🚫 Provide 2–{len(NUMBER_EMOJIS)} options.", ephemeral=True)
        if role:
            pm = await channel.send(f"||{role.mention}||")
            await pm.delete()
        expires = datetime.datetime.now() + datetime.timedelta(seconds=timeout)
        created = datetime.datetime.now().isoformat()
        data = {
            'channel_id': channel.id,
            'message_id': None,
            'question': question,
            'options': opts,
            'created_at': created,
            'expires_at': expires.isoformat(),
            'votes': {opt: [] for opt in opts}
        }
        view = PollView(data)
        msg = await channel.send(embed=view.build_embed(), view=view)
        data['message_id'] = msg.id
        view._persist()
        await ctx.send(f"✅ The poll has been posted in {channel.mention} ({msg.jump_url})", delete_after=8)

    @poll.error
    async def poll_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("🚫 Manage Messages permission needed.", ephemeral=True)
        else:
            raise error

async def setup(bot):
    await bot.add_cog(Polls(bot))