import discord
from discord.ext import commands, tasks
import json
import os
from dotenv import load_dotenv
from instagrapi import Client
from datetime import datetime, timezone
import asyncio

load_dotenv()

CONFIG_PATH = "config.json"
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

INSTAGRAM_CONFIG = config["features"]["instagram_notifications"]
INSTAGRAM_ACCOUNTS = INSTAGRAM_CONFIG["instagram_accounts_to_track"]
CHANNEL_ID = int(config["text_channel_ids"]["instagram_post_notifications"])
CHECK_INTERVAL = int(INSTAGRAM_CONFIG["check_interval_min"]) * 60
SHOW_TERMINAL_OUTPUT = INSTAGRAM_CONFIG.get("show_outputs_in_terminal", True)
ANNOUNCE_COMMENT = INSTAGRAM_CONFIG.get("announcement_comment", {"include_comment": False, "comment": ""})

POST_HISTORY_PATH = config["file_paths"]["instagram_post_announcements_history"]

INSTAGRAM_USERNAME = os.getenv("INSTAGRAM_USERNAME")
INSTAGRAM_PASSWORD = os.getenv("INSTAGRAM_PASSWORD")
SESSION_FILE = config["file_paths"]["instagram_session"]

class InstagramCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.client = Client()
        self.user_id_cache = {}
        self.last_posted_id = {}
        self.posts_cache = {}

        # Load history
        if os.path.exists(POST_HISTORY_PATH):
            try:
                with open(POST_HISTORY_PATH, "r") as f:
                    self.last_posted_id = json.load(f)
                if SHOW_TERMINAL_OUTPUT:
                    print("[Instagram] Loaded post history.")
            except Exception as e:
                if SHOW_TERMINAL_OUTPUT:
                    print(f"[Instagram] Error loading post history: {e}")

        # Login session
        try:
            if os.path.exists(SESSION_FILE):
                self.client.load_settings(SESSION_FILE)
                self.client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                if SHOW_TERMINAL_OUTPUT:
                    print("[Instagram] Session loaded successfully.")
            else:
                self.client.login(INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD)
                self.client.dump_settings(SESSION_FILE)
                if SHOW_TERMINAL_OUTPUT:
                    print("[Instagram] Logged in and session saved.")
        except Exception as e:
            if SHOW_TERMINAL_OUTPUT:
                print(f"[Instagram] Login/session error: {e}")

        if INSTAGRAM_CONFIG.get("enable_feature", False):
            self.bot.loop.create_task(self.wait_until_ready())

    async def wait_until_ready(self):
        await self.bot.wait_until_ready()
        self.fetch_instagram_posts.start()

    @tasks.loop(seconds=CHECK_INTERVAL)
    async def fetch_instagram_posts(self):
        for account in INSTAGRAM_ACCOUNTS:
            try:
                user_id = self.user_id_cache.get(account)
                if not user_id:
                    user_id = self.client.user_id_from_username(account)
                    self.user_id_cache[account] = user_id

                try:
                    posts = self.client.user_medias(user_id, 1)
                except Exception as e:
                    if SHOW_TERMINAL_OUTPUT:
                        print(f"[Instagram] fetch failed for {account}: {e}")
                    continue

                if not posts:
                    continue

                latest_post = posts[0]
                prev_id = self.last_posted_id.get(account)
                if prev_id == latest_post.pk:
                    continue  # already announced

                # Save new post ID
                self.last_posted_id[account] = latest_post.pk
                try:
                    with open(POST_HISTORY_PATH, "w") as f:
                        json.dump(self.last_posted_id, f)
                except Exception as e:
                    if SHOW_TERMINAL_OUTPUT:
                        print(f"[Instagram] File write error: {e}")

                self.posts_cache[account] = latest_post

                if SHOW_TERMINAL_OUTPUT:
                    t = latest_post.taken_at.strftime("%m/%d/%Y %I:%M %p UTC")
                    print(f"[Instagram] New post for {account} at {t} — ID: {latest_post.pk}")
                    print(latest_post.__dict__)

                channel = self.bot.get_channel(CHANNEL_ID)
                if channel:
                    embed = self.build_recent_embed(latest_post, account)
                    view = discord.ui.View()
                    view.add_item(discord.ui.Button(
                        label="View Instagram Post",
                        url=f"https://www.instagram.com/p/{latest_post.code}/",
                        style=discord.ButtonStyle.link
                    ))
                    content_msg = ANNOUNCE_COMMENT["comment"] if ANNOUNCE_COMMENT.get("include_comment") else None
                    await channel.send(content=content_msg, embed=embed, view=view)

                await asyncio.sleep(1)

            except Exception as e:
                if SHOW_TERMINAL_OUTPUT:
                    print(f"[Instagram] Error processing account {account}: {e}")

    def build_recent_embed(self, post, account):
        caption = getattr(post, "caption_text", "") or ""
        tagged_users = getattr(post, "usertags", [])
        tagged_str = ", ".join([
            f"[{u.user.username}](https://www.instagram.com/{u.user.username}/)" for u in tagged_users
        ]) if tagged_users else ""
        thumbnail_url = getattr(post, "thumbnail_url", None) or post.image_versions2.candidates[0].url
        account_link = f"[@{account}](https://www.instagram.com/{account}/)"
        posted_time = post.taken_at.strftime("%m/%d/%Y, %I:%M %p UTC") if hasattr(post, "taken_at") else "Unknown"

        desc_lines = [f"**Posted:** {posted_time} ({account_link.upper()})"]
        if caption:
            desc_lines.append(f"**Caption:** {caption}")
        if tagged_str:
            desc_lines.append(f"**Tagged User(s):** {tagged_str}")

        description = "\n".join(desc_lines)
        if len(description) > 4096:
            description = description[:4093] + "..."

        embed = discord.Embed(
            title=f"📷 | New {account.upper()} Instagram Post!",
            description=description,
            color=int(config["general"]["embed_color"].lstrip("#"), 16)
        )

        if thumbnail_url:
            embed.set_image(url=thumbnail_url)
        return embed

    @commands.group(name="insta", invoke_without_command=True)
    async def insta(self, ctx):
        await ctx.send("Use `!insta list` for recent posts or `!insta recent` for the latest.")

    @insta.command(name="list")
    async def insta_list(self, ctx):
        if not self.posts_cache:
            return await ctx.send("No recent posts cached.")
        for acc, post in self.posts_cache.items():
            desc = f"{acc}: {post.taken_at.strftime('%m/%d/%Y')} {post.code} – Likes: {post.like_count}, Comments: {post.comment_count}"
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="View Post", url=f"https://www.instagram.com/p/{post.code}/"))
            await ctx.send(desc, view=view)

    @insta.command(name="recent")
    async def insta_recent(self, ctx):
        if not self.posts_cache:
            return await ctx.send("No recent posts cached.")
        recent = max(self.posts_cache.values(), key=lambda p: p.taken_at or datetime.min)
        acc = next(k for k, v in self.posts_cache.items() if v.pk == recent.pk)
        embed = self.build_recent_embed(recent, acc)
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="View Post", url=f"https://www.instagram.com/p/{recent.code}/"))
        await ctx.send(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(InstagramCog(bot))
