# cogs/family_stats.py
import discord
from discord.ext import commands, tasks
import json
from datetime import datetime, timedelta
import os

from utils.pillow import generate_fam_weekly_stats_report  # <-- import your function

CONFIG_PATH = "config.json"


class FamilyStats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config = {}
        self.vsa_db = {}

    async def cog_load(self):
        """Called when cog is loaded."""
        self.load_config()
        self.load_vsa_db()
        self.weekly_task.start()

    async def cog_unload(self):
        """Called when cog is unloaded."""
        self.weekly_task.cancel()

    def load_config(self):
        with open(CONFIG_PATH, "r") as f:
            self.config = json.load(f)

    def load_vsa_db(self):
        db_path = self.config["file_paths"]["parsed_vsa_member_data_and_events_info_file"]
        if os.path.exists(db_path):
            with open(db_path, "r") as f:
                self.vsa_db = json.load(f)
        else:
            self.vsa_db = {"parsed_members": {}, "family_stats": {}, "events_info": {}, "leaderboards": {}}

    async def send_weekly_report(self, start_date: datetime, end_date: datetime):
        """Generate and send the weekly report image."""
        channel_id = int(self.config["text_channel_ids"]["family_stat_reports"])
        channel = self.bot.get_channel(channel_id)
        if not channel:
            print(f"[ERROR] Weekly stats channel not found: {channel_id}")
            return

        members = self.vsa_db.get("parsed_members", {})
        events_info = list(self.vsa_db.get("events_info", {}).values())
        family_stats = self.vsa_db.get("family_stats", {})
        leaderboards = self.vsa_db.get("leaderboards", {})

        # Determine weekly points for each member
        weekly_member_points = {}
        for psid, member in members.items():
            weekly_points = 0
            for idx, event in enumerate(events_info):
                event_date = datetime.strptime(event["date"], "%m/%d/%Y").date()
                if start_date.date() <= event_date <= end_date.date():
                    weekly_points += member["event_points"][idx]
            weekly_member_points[psid] = weekly_points

        # Aggregate weekly stats per family
        weekly_family_stats = {}
        for psid, points in weekly_member_points.items():
            member = members[psid]
            fam_name = member.get("family_name") or "Not in a family"
            if fam_name not in weekly_family_stats:
                weekly_family_stats[fam_name] = {"total_points": 0, "member_count": 0}
            weekly_family_stats[fam_name]["total_points"] += points
            weekly_family_stats[fam_name]["member_count"] += 1

        # Compute weekly averages
        for fam_name, stats in weekly_family_stats.items():
            stats["avg_points"] = (
                stats["total_points"] / stats["member_count"] if stats["member_count"] > 0 else 0
            )

        # Compute top 5 weekly members
        # Compute top 5 weekly members
        weekly_top5_all = sorted(
            [
                {
                    "abbr": members[psid]["role_key"] or "N/A",
                    "first_name": members[psid]["first_name"],
                    "last_name": members[psid]["last_name"],
                    "points": pts,
                    "family_name": members[psid].get("family_name") or "N/A"
                }
                for psid, pts in weekly_member_points.items()
            ],
            key=lambda x: x["points"],
            reverse=True
        )

        # Compute top 5 overall members
        overall_top5_all = sorted(
            [
                {
                    "abbr": members[psid].get("role_key") or "N/A",
                    "first_name": members[psid]["first_name"],
                    "last_name": members[psid]["last_name"],
                    "points": members[psid]["points"],
                    "family_name": members[psid].get("family_name") or "N/A"
                }
                for psid in members
            ],
            key=lambda x: x["points"],
            reverse=True
        )

        # --- Filter for "Kuromi" members only for display ---
        weekly_top5 = [m for m in weekly_top5_all if m["family_name"] == "Kuromi"][:5]
        overall_top5 = [m for m in overall_top5_all if m["family_name"] == "Kuromi"][:5]

        # Weekly totals
        total_weekly_points = sum([stats["total_points"] for stats in weekly_family_stats.values()])
        total_family_members = sum([stats["member_count"] for stats in weekly_family_stats.values()])
        weekly_pts_per_member = total_weekly_points / total_family_members if total_family_members else 0

        # Overall totals
        total_overall_points = sum([member["points"] for member in members.values()])
        total_overall_members = len(members)
        overall_pts_per_member = total_overall_points / total_overall_members if total_overall_members else 0

        # Generate report image
        output_path = "./assets/outputs/weekly_fam_report.png"
        img_path = generate_fam_weekly_stats_report(
            start_date=start_date.date(),
            end_date=end_date.date(),
            output_path=output_path,
            # Weekly stats
            weekly_points=total_weekly_points,
            weekly_contributors=total_family_members,
            total_family_members=total_family_members,
            weekly_pts_per_member=weekly_pts_per_member,
            weekly_top5=weekly_top5,
            # Overall stats
            overall_points=total_overall_points,
            overall_members=total_overall_members,
            overall_pts_per_member=overall_pts_per_member,
            overall_top5=overall_top5,
        )

        if img_path and os.path.exists(img_path):
            await channel.send(file=discord.File(img_path))
        else:
            await channel.send("⚠️ Failed to generate weekly report image.")

    @tasks.loop(minutes=1)
    async def weekly_task(self):
        auto_stats = self.config.get("features", {}).get("auto_family_stats", {})
        weekly_cfg = auto_stats.get("send_schedule", {}).get("weekly", {})
        if not auto_stats.get("enable_feature") or not weekly_cfg.get("enable"):
            return

        now = datetime.now()
        report_time = datetime.strptime(
            weekly_cfg["time_to_send_24_hour_format_cst"], "%H:%M"
        ).time()
        week_day_name = now.strftime("%A")

        test_mode = True
        if (
            week_day_name == weekly_cfg.get("day_to_send")
            and now.time().hour == report_time.hour
            and now.time().minute == report_time.minute or test_mode
        ):
            # Define Mon–Sun week range
            start_date = now - timedelta(days=now.weekday())
            end_date = start_date + timedelta(days=6)
            await self.send_weekly_report(start_date, end_date)

    @weekly_task.before_loop
    async def before_weekly_task(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(FamilyStats(bot))
