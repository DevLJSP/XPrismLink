import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from database import update_balance, record_game
from logger import log_event
from cogs.utils_view import PlayAgainView
from cogs.theme import Color

# Payouts slashed — house edge ~44 %
# 0 or 3 heads: prob 12.5 % → payout 3.5x  (was 7.2x)
# 1 or 2 heads: prob 37.5 % → payout 1.5x  (was 2.4x)
MULT_RARE   = 3.5
MULT_COMMON = 1.5


class CoinsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="coins", description="Flip 3 coins and guess the number of heads!")
    @app_commands.describe(amount="Amount to bet", choice="Number of heads (0, 1, 2, or 3)")
    @app_commands.choices(choice=[
        app_commands.Choice(name="0 Heads — All Tails", value=0),
        app_commands.Choice(name="1 Head",              value=1),
        app_commands.Choice(name="2 Heads",             value=2),
        app_commands.Choice(name="3 Heads — All Heads", value=3),
    ])
    async def coins(self, interaction: discord.Interaction, amount: int, choice: app_commands.Choice[int]):
        from cogs.utils import acquire_game_lock, release_game_lock
        if not await acquire_game_lock(interaction.user.id, interaction):
            return
        try:
            from database import process_bet
            if not await process_bet(interaction, amount):
                return

            embed = discord.Embed(title="🪙  Triple Coin Toss", color=Color.PLAYING)
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
            embed.description = "Flipping 3 coins...  🪙 🪙 🪙"
            await interaction.response.send_message(embed=embed)

            await asyncio.sleep(2.0)

            flips       = [random.choice(["H", "T"]) for _ in range(3)]
            heads_count = flips.count("H")
            won         = heads_count == choice.value
            multiplier  = MULT_RARE if choice.value in (0, 3) else MULT_COMMON
            flip_visual = "  |  ".join("🪙 Heads" if f == "H" else "🪙 Tails" for f in flips)

            if won:
                winnings = int(amount * multiplier)
                profit   = winnings - amount
                await update_balance(interaction.user.id, winnings)
                embed.color = Color.WIN
                res_str = (
                    f">>> **Results:** `{flip_visual}`\n"
                    f"**Heads:** `{heads_count}`\n\n"
                    f"**Guess:** `{choice.name}`  ✅\n\n"
                    f"💰  **Profit:** +${profit:,}  (`{multiplier}x`)"
                )
                await log_event(self.bot, f"{interaction.user.name} WON ${profit} in Triple Coins ({choice.name})")
                await record_game(interaction.user.id, amount, profit, True)
            else:
                embed.color = Color.LOSS
                res_str = (
                    f">>> **Results:** `{flip_visual}`\n"
                    f"**Heads:** `{heads_count}`\n\n"
                    f"**Guess:** `{choice.name}`  ❌\n\n"
                    f"💸  **Loss:** -${amount:,}"
                )
                await log_event(self.bot, f"{interaction.user.name} LOST ${amount} in Triple Coins ({choice.name})")
                await record_game(interaction.user.id, amount, -amount, False)

            embed.description = res_str
            view = PlayAgainView(self.coins.callback, self, interaction, amount, choice)
            try:
                await interaction.edit_original_response(embed=embed, view=view)
            except Exception:
                pass
        finally:
            release_game_lock(interaction.user.id)


async def setup(bot):
    await bot.add_cog(CoinsCog(bot))