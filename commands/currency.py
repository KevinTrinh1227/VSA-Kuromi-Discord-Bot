import discord
from discord.ext import commands
import json
import random
import datetime

CONFIG_FILE = 'config.json'
USER_DATA_FILE = 'verified_user_data.json'

# Load configuration
with open(CONFIG_FILE) as json_file:
    config = json.load(json_file)

embed_color = int(config["general"]["embed_color"].strip("#"), 16)
currency_name = config.get("features", {}).get("coin_level_system", {}).get("currency_name", "coins")
currency_label = currency_name.capitalize()
win_chance = config.get("features", {}).get("coin_level_system", {}).get("coin_flip_chance_of_winning", 0.5)
coinflip_enabled = config.get("features", {}).get("coin_level_system", {}).get("enable_feature", False)
cool_down_time = 5

class CoinflipCog(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.hybrid_command(
        name="coinflip",
        aliases=["cf"],
        brief="coinflip",
        description="Gamble using coinflip",
        with_app_command=True
    )
    @discord.app_commands.describe(
        bet="Amount of coins to bet (e.g., 200)",
        choice="Your call: heads or tails"
    )
    @commands.cooldown(1, cool_down_time, commands.BucketType.user)
    async def coinflip(self, ctx: commands.Context, bet: int, choice: str):
        with open(USER_DATA_FILE, 'r') as f:
            user_data = json.load(f)

        if not coinflip_enabled:
            await ctx.send("❌ The coin and level system is disabled.")
            return

        user_id = str(ctx.author.id)

        if user_id not in user_data:
            await ctx.send("❌ You are not verified yet.")
            return

        stats = user_data[user_id].setdefault("stats", {})
        user_balance = stats.get("coins", 0)

        if bet <= 0:
            await ctx.send("❌ Please bet a positive amount.")
            return

        if bet > user_balance:
            embed = discord.Embed(
                title="**❌ | INSUFFICIENT FUNDS**",
                description=(
                    f"{ctx.author.mention}, you tried to bet `{bet}` {currency_name} but only have `{user_balance}` {currency_name} available.\n\n"
                    f"To earn more {currency_name}, try sending more messages, gambling, or ask someone to pay you."
                ),
                color=embed_color
            )
            embed.timestamp = datetime.datetime.now()
            embed.set_thumbnail(url=str(ctx.author.avatar.url))
            embed.set_footer(text=f"©️ {ctx.guild.name} • {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", icon_url=ctx.guild.icon.url)
            await ctx.send(embed=embed)
            return

        if choice.lower() not in ["heads", "tails"]:
            await ctx.send("❌ Please choose either 'heads' or 'tails'.")
            return

        balance_before_bet = user_balance
        opposite = "tails" if choice.lower() == "heads" else "heads"

        stats.setdefault("coinflips_won", 0)
        stats.setdefault("coinflips_lost", 0)

        random_number = random.random()
        did_win = random_number < win_chance

        if did_win:
            stats["coins"] += bet * 2
            stats["coinflips_won"] += 1
            embed = discord.Embed(
                title="**🏆 | CONGRATULATIONS YOU WON!**",
                description=f"{ctx.author.mention} bet `{bet}` {currency_name} and won `{bet * 2}` {currency_name}. You guessed {choice.lower()} and the coinflip landed on {choice.lower()}! You can try again in {cool_down_time} second(s).",
                color=embed_color
            )
            embed.add_field(name='Before Balance', value=f"{balance_before_bet}", inline=True)
            embed.add_field(name='Net Profit', value=f"{bet:.2f}", inline=True)
            embed.add_field(name='Current Balance', value=f"{stats['coins']} {currency_name}", inline=True)
        else:
            stats["coins"] -= bet
            stats["coinflips_lost"] += 1
            embed = discord.Embed(
                title="**☹️ | SORRY, YOU LOST!**",
                description=f"{ctx.author.mention} bet `{bet}` {currency_name} and lost. You chose {choice.lower()} and the coinflip landed on {opposite}. You can try again in {cool_down_time} second(s).",
                color=embed_color
            )
            embed.add_field(name='Before Balance', value=f"{balance_before_bet}", inline=True)
            embed.add_field(name='Loss Amount', value=f"{bet:.2f}", inline=True)
            embed.add_field(name='Current Balance', value=f"{stats['coins']}", inline=True)

        embed.timestamp = datetime.datetime.now()
        embed.set_thumbnail(url=str(ctx.author.avatar.url))
        embed.set_footer(text=f"©️ {ctx.guild.name} • {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", icon_url=ctx.guild.icon.url)
        await ctx.send(embed=embed)

        with open(USER_DATA_FILE, 'w') as f:
            json.dump(user_data, f, indent=2)

    @commands.hybrid_command(
        name="pay",
        aliases=["send", "transfer"],
        brief="pay",
        description="Send coins to another user.",
        with_app_command=True
    )
    @discord.app_commands.describe(
        member="The user you want to send coins to",
        amount="Amount of coins to send (e.g., 150)"
    )
    async def pay(self, ctx: commands.Context, member: discord.Member, amount: int):
        if amount <= 0:
            await ctx.send("❌ Please enter a positive amount to send.")
            return

        with open(USER_DATA_FILE, 'r') as f:
            user_data = json.load(f)

        sender_id = str(ctx.author.id)
        receiver_id = str(member.id)

        if sender_id == receiver_id:
            await ctx.send("❌ You cannot pay yourself.")
            return

        if sender_id not in user_data:
            await ctx.send("❌ You are not verified.")
            return

        if receiver_id not in user_data:
            await ctx.send("❌ The recipient is not verified yet.")
            return

        # Initialize sender/receiver stats and coins if missing
        sender_stats = user_data[sender_id].setdefault("stats", {})
        receiver_stats = user_data[receiver_id].setdefault("stats", {})

        sender_coins = sender_stats.setdefault("coins", 0)
        receiver_coins = receiver_stats.setdefault("coins", 0)

        if amount > sender_coins:
            embed = discord.Embed(
                title="**❌ | INSUFFICIENT FUNDS**",
                description=(
                    f"{ctx.author.mention}, you tried to pay `{amount}` {currency_name}, but you only have `{sender_coins}` {currency_name}.\n\n"
                    f"Earn more by messaging, gambling, or asking someone to pay you."
                ),
                color=embed_color
            )
            embed.timestamp = datetime.datetime.now()
            embed.set_thumbnail(url=str(ctx.author.avatar.url))
            embed.set_footer(text=f"©️ {ctx.guild.name}", icon_url=ctx.guild.icon.url)
            await ctx.send(embed=embed)
            return

        # Process payment
        sender_stats["coins"] -= amount
        receiver_stats["coins"] += amount

        embed = discord.Embed(
            title="**✅ | PAYMENT SUCCESSFUL**",
            description=(
                f"{ctx.author.mention} sent `{amount}` {currency_name} to {member.mention}!\n\n"
                f"**{ctx.author.display_name}**: {sender_coins} → {sender_stats['coins']}\n"
                f"**{member.display_name}**: {receiver_coins} → {receiver_stats['coins']}"
            ),
            color=embed_color
        )
        embed.timestamp = datetime.datetime.now()
        embed.set_thumbnail(url=str(ctx.author.avatar.url))
        embed.set_footer(text=f"©️ {ctx.guild.name}", icon_url=ctx.guild.icon.url)
        await ctx.send(embed=embed)

        with open(USER_DATA_FILE, 'w') as f:
            json.dump(user_data, f, indent=2)


async def setup(client):
    await client.add_cog(CoinflipCog(client))
