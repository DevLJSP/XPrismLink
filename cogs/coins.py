import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from database import update_balance, record_game
from logger import log_event
from cogs.utils_view import PlayAgainView

class CoinsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="coins", description="Flip 3 coins and guess the number of heads!")
    @app_commands.describe(amount="Amount to bet", choice="Number of heads (0, 1, 2, or 3)")
    @app_commands.choices(choice=[
        app_commands.Choice(name="0 Heads (All Tails)", value=0),
        app_commands.Choice(name="1 Head", value=1),
        app_commands.Choice(name="2 Heads", value=2),
        app_commands.Choice(name="3 Heads (All Heads)", value=3)
    ])
    async def coins(self, interaction: discord.Interaction, amount: int, choice: app_commands.Choice[int]):
        from cogs.utils import acquire_game_lock
        if not await acquire_game_lock(interaction.user.id, interaction): return
        try:
            from database import process_bet
            if not await process_bet(interaction, amount):
                return
    
            embed = discord.Embed(title="🪙 Triple Coin Toss", color=discord.Color.blue())
            embed.set_author(name=f"{interaction.user.display_name} is playing", icon_url=interaction.user.display_avatar.url)
            embed.description = "Flipping 3 coins... 🪙 🪙 🪙"
            await interaction.response.send_message(embed=embed)
            
            await asyncio.sleep(2.0)
            
            # Simulate 3 coin flips
            flips = [random.choice(["H", "T"]) for _ in range(3)]
            heads_count = flips.count("H")
            
            won = (heads_count == choice.value)
            
            # Calculate Payouts for a 10% house edge
            # Probabilities: 
            # 0 or 3 Heads: 1/8 (12.5%) -> EV: 0.125 * Payout = 0.90 -> Payout: 7.2x
            # 1 or 2 Heads: 3/8 (37.5%) -> EV: 0.375 * Payout = 0.90 -> Payout: 2.4x
            if choice.value in [0, 3]:
                multiplier = 7.2
            else:
                multiplier = 2.4
                
            flip_visual = " | ".join([("🪙 Heads" if f == "H" else "🪙 Tails") for f in flips])
            
            if won:
                winnings = int(amount * multiplier)
                profit = winnings - amount
                await update_balance(interaction.user.id, winnings)
                
                embed.color = discord.Color.green()
                res_str = (
                    f">>> **Results:** `{flip_visual}`\n"
                    f"**Total Heads:** `{heads_count}`\n\n"
                    f"**You guessed:** `{choice.name}`\n"
                    f"**Status:** Correct! (`{multiplier}x`)\n\n"
                    f"💰 **Profit:** +${profit}"
                )
                await log_event(self.bot, f"{interaction.user.name} WON ${profit} in Triple Coins (Guessed {choice.name})")
                await record_game(interaction.user.id, amount, profit, True)
            else:
                embed.color = discord.Color.red()
                res_str = (
                    f">>> **Results:** `{flip_visual}`\n"
                    f"**Total Heads:** `{heads_count}`\n\n"
                    f"**You guessed:** `{choice.name}`\n"
                    f"**Status:** Incorrect.\n\n"
                    f"💸 **Loss:** -${amount}"
                )
                await log_event(self.bot, f"{interaction.user.name} LOST ${amount} in Triple Coins (Guessed {choice.name})")
                await record_game(interaction.user.id, amount, -amount, False)
    
            embed.description = res_str
            
            view = PlayAgainView(self.coins.callback, self, interaction, amount, choice)
            try:
                await interaction.edit_original_response(embed=embed, view=view)
            except:
                pass
        finally:
            from cogs.utils import release_game_lock
            release_game_lock(interaction.user.id)

async def setup(bot):
    await bot.add_cog(CoinsCog(bot))
