# commands/setup.py

import discord
from discord.ext import commands
from discord.ui import View
import json, traceback

class YesNo(View):
    def __init__(self, *, timeout=60):
        super().__init__(timeout=timeout)
        self.value = None

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.green)
    async def yes(self, i: discord.Interaction, b: discord.ui.Button):
        self.value = True
        await i.response.defer()
        self.stop()

    @discord.ui.button(label="No", style=discord.ButtonStyle.red)
    async def no(self, i: discord.Interaction, b: discord.ui.Button):
        self.value = False
        await i.response.defer()
        self.stop()

async def get_choice(ctx, question):
    view = YesNo()
    await ctx.send(question, view=view)
    await view.wait()
    return view.value

async def get_or_create_text_channel(ctx, prompt, default_name):
    guild = ctx.guild
    await ctx.send(f"{prompt}\n• Mention it, or type `create` to make **#{default_name}**.")
    msg = await ctx.bot.wait_for("message", check=lambda m: m.author==ctx.author)
    if msg.channel_mentions:
        return msg.channel_mentions[0]
    else:
        return await guild.create_text_channel(default_name)

async def get_or_create_role(ctx, prompt, default_name):
    guild = ctx.guild
    await ctx.send(f"{prompt}\n• Mention it, or type `create` to make **{default_name}**.")
    msg = await ctx.bot.wait_for("message", check=lambda m: m.author==ctx.author)
    if msg.role_mentions:
        return msg.role_mentions[0]
    else:
        return await guild.create_role(name=default_name)

class initialsetup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.has_permissions(administrator=True)
    @commands.hybrid_command(name="setup", with_app_command=True,
                             description="Run initial VSA-Family setup.")
    async def setup(self, ctx):
        with open('config.json') as f:
            config = json.load(f)

        if config["config"]["bool"] != 0:
            return await ctx.send("⚠️ Bot is already configured.")

        try:
            # 1) Features
            config["features"]["filtered_chat"]     = int(await get_choice(ctx, "Enable filtered chat?"))
            config["features"]["inactivity_cmd"]    = int(await get_choice(ctx, "Enable inactivity command?"))
            config["features"]["punishments_cmd"]   = int(await get_choice(ctx, "Enable punishments command?"))
            config["features"]["server_stats"]      = int(await get_choice(ctx, "Enable server-stats voice channels?"))
            config["features"]["coin_level_system"] = int(await get_choice(ctx, "Enable chat coin & level system?"))

            guild = ctx.guild

            # 2) Text channels
            ch_welcome = await get_or_create_text_channel(
                ctx, "Where should I send **welcome** messages?", "welcome"
            )
            config["text_channel_ids"]["welcome"] = str(ch_welcome.id)

            if config["features"]["inactivity_cmd"]:
                ch_inact = await get_or_create_text_channel(
                    ctx, "Where should I send **inactivity notice**?", "inactivity-notice"
                )
                config["text_channel_ids"]["inactivity_notice"] = str(ch_inact.id)
            else:
                config["text_channel_ids"]["inactivity_notice"] = "0"

            ch_tickets = await get_or_create_text_channel(
                ctx, "Where should I post **ticket transcripts**?", "tickets-transcripts"
            )
            config["text_channel_ids"]["tickets_transcripts"] = str(ch_tickets.id)

            ch_logs = await get_or_create_text_channel(
                ctx, "Where should I send **bot logs**?", "bot-logs"
            )
            config["text_channel_ids"]["bot_logs"] = str(ch_logs.id)

            # 3) Roles
            role_family  = await get_or_create_role(ctx, "Which role is **Family Member**?", "Family Member")
            role_lead    = await get_or_create_role(ctx, "Which role is **Family Lead**?", "Family Lead")
            role_staff   = await get_or_create_role(ctx, "Which role is **Staff Member**?", "Staff Member")
            role_verified= await get_or_create_role(ctx, "Which role is **Verified VSA Member**?", "Verified VSA Member")
            role_unverif = await get_or_create_role(ctx, "Which role is **Unverified VSA Member**?", "Unverified VSA Member")

            config["role_ids"]["family_member"]        = str(role_family.id)
            config["role_ids"]["family_lead"]          = str(role_lead.id)
            config["role_ids"]["staff_member"]         = str(role_staff.id)
            config["role_ids"]["verified_vsa_member"]  = str(role_verified.id)
            config["role_ids"]["unverified_vsa_member"]= str(role_unverif.id)

            # 4) Tickets category
            cat_tix = await guild.create_category("TICKETS")
            config["category_ids"]["tickets_category"] = str(cat_tix.id)

            # 5) Server-stats voice channels
            if config["features"]["server_stats"]:
                cat_stats = await guild.create_category("SERVER INFO")
                # a) Server Members
                ch1 = await guild.create_voice_channel(
                    f"Server Members: {guild.member_count}",
                    overwrites={guild.default_role: discord.PermissionOverwrite(connect=False)},
                    category=cat_stats
                )
                # b) In Family (initial)
                ch2 = await guild.create_voice_channel(
                    "In Family: 0/0",
                    overwrites={guild.default_role: discord.PermissionOverwrite(connect=False)},
                    category=cat_stats
                )
                # c) Fam Leads Online (initial)
                ch3 = await guild.create_voice_channel(
                    "Fam Leads Online: 0/0",
                    overwrites={guild.default_role: discord.PermissionOverwrite(connect=False)},
                    category=cat_stats
                )
                config["voice_channel_ids"]["member_count"]     = str(ch1.id)
                config["voice_channel_ids"]["online_in_family"] = str(ch2.id)
                config["voice_channel_ids"]["fam_leads_online"] = str(ch3.id)
            else:
                for k in ("member_count","online_in_family","fam_leads_online"):
                    config["voice_channel_ids"][k] = "0"

            # finalize
            config["config"]["bool"] = 1
            with open('config.json','w') as f:
                json.dump(config, f, indent=2)

            await ctx.send("✅ Setup complete! Please restart the bot to apply changes.")

        except Exception as e:
            traceback.print_exc()
            await ctx.send(f"❌ Setup failed: {e}")

async def setup(bot):
    await bot.add_cog(initialsetup(bot))
