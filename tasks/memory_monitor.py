# cogs/memory_monitor.py

import os
import psutil
import tracemalloc
import objgraph
import json
from collections import defaultdict
from discord.ext import commands, tasks

# --- Load config once at import time ---
CONFIG_PATH = os.path.join(os.path.dirname(__file__), '..', 'config.json')
with open(CONFIG_PATH, 'r') as f:
    CONFIG = json.load(f)

class MemoryMonitor(commands.Cog):
    def __init__(self, bot, config):
        self.bot = bot
        self.config = config

        tracemalloc.start()

        feature_conf = self.config["features"]["bot_memory_monitor"]
        if feature_conf.get("enable_feature", False):
            # interval in minutes → seconds (default 5 min, min 60s)
            interval = max(60, feature_conf.get("interval_minutes", 5) * 60)
            self.log_memory.change_interval(seconds=interval)
            self.log_memory.start()

    def cog_unload(self):
        if self.log_memory.is_running():
            self.log_memory.cancel()

    @commands.command()
    async def mem(self, ctx, lines: int = 10):
        """
        Show concise memory usage report.
        Example: !mem 20 (shows top 20 allocations instead of 10)
        """
        process = psutil.Process(os.getpid())
        mem = process.memory_info().rss / 1024**2  # MB

        report_lines = [f"[MEMORY REPORT] Total usage: {mem:.2f} MB"]

        # --- Object growth (objgraph) ---
        growth = objgraph.growth(limit=5)
        if growth:
            report_lines.append("Top growing objects:")
            for name, count, delta in growth:
                report_lines.append(f"- {name}: {count} (+{delta})")

        # --- Tracemalloc snapshot (top allocations) ---
        snapshot = tracemalloc.take_snapshot()
        stats = snapshot.statistics("lineno")[:lines]

        report_lines.append("Top allocations:")
        for stat in stats:
            report_lines.append(str(stat))

        # --- File totals (grouped) ---
        file_totals = defaultdict(int)
        for stat in snapshot.statistics("lineno"):
            frame = stat.traceback[0]
            file_totals[os.path.relpath(frame.filename)] += stat.size

        top_files = sorted(file_totals.items(), key=lambda x: x[1], reverse=True)[:5]
        report_lines.append("Top files:")
        for file, size in top_files:
            report_lines.append(f"- {file}: {size/1024/1024:.2f} MB")

        # --- Discord-safe output ---
        out = "\n".join(report_lines)
        if len(out) > 1900:
            out = out[:1900] + "\n... (truncated)"
        await ctx.send(f"```{out}```")

    @tasks.loop()
    async def log_memory(self):
        """Logs concise memory info if enabled in config."""
        feature_conf = self.config["features"]["bot_memory_monitor"]
        if not feature_conf.get("show_outputs_in_terminal", True):
            return  # skip printing if disabled

        process = psutil.Process(os.getpid())
        mem = process.memory_info().rss / 1024**2

        report = [f"[MEMORY SNAPSHOT] Total = {mem:.2f} MB"]

        growth = objgraph.growth(limit=5)
        if growth:
            report.append("Top growth:")
            for name, count, delta in growth:
                report.append(f"- {name}: {count} (+{delta})")

        snapshot = tracemalloc.take_snapshot()
        for stat in snapshot.statistics("lineno")[:5]:
            report.append(str(stat))

        # Group by file totals
        file_totals = defaultdict(int)
        for stat in snapshot.statistics("lineno"):
            frame = stat.traceback[0]
            file_totals[os.path.relpath(frame.filename)] += stat.size
        top_files = sorted(file_totals.items(), key=lambda x: x[1], reverse=True)[:3]
        for file, size in top_files:
            report.append(f"- {file}: {size/1024/1024:.2f} MB")

        print("\n".join(report) + "\n")

async def setup(bot):
    await bot.add_cog(MemoryMonitor(bot, CONFIG))
