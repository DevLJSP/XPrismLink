import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from database import get_balance, update_balance, record_game
from cogs.linker import is_linked
from logger import log_event
from cogs.utils_view import PlayAgainView

EMOJIS = ["🍒", "🍋", "🍉", "🍇", "🔔", "⭐", "💎"]
MULTIPLIERS = {
    "🍒": 1.5,
    "🍋": 2.0,
    "🍉": 3.0,
    "🍇": 5.0,
    "🔔": 7.5,
    "⭐": 10.0,
    "💎": 20.0
}

class SlotsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="slots", description="Play a 3-reel slot machine")
    @app_commands.describe(amount="Amount to bet")
    async def slots(self, interaction: discord.Interaction, amount: int):
        from cogs.utils import acquire_game_lock
        if not await acquire_game_lock(interaction.user.id, interaction): return
        try:
            from database import process_bet
            await interaction.response.defer()
            if not await process_bet(interaction, amount):
                return
            
            # Initial spin visual
            embed = discord.Embed(title="🎰 Slots 🎰", color=discord.Color.gold())
            embed.set_author(name=f"{interaction.user.display_name} is playing", icon_url=interaction.user.display_avatar.url)
            embed.description = "Spinning: 🔄 | 🔄 | 🔄\n\nBet: **${}**".format(amount)
            await interaction.edit_original_response(embed=embed)
            
            await asyncio.sleep(1.0)
            
            r1 = random.choice(EMOJIS)
            r2 = random.choice(EMOJIS)
            r3 = random.choice(EMOJIS)
            
            winnings = 0
            payout_str = "No match."
            color = discord.Color.red()
            
            # Win Condition:
            if r1 == r2 == r3:
                mult = MULTIPLIERS[r1]
                winnings = int(amount * mult)
                payout_str = f"Jackpot! {mult}x multiplier!"
                color = discord.Color.green()
                await log_event(self.bot, f"{interaction.user.name} WON ${winnings - amount} in Slots (Jackpot x{mult})")
                await record_game(interaction.user.id, amount, winnings - amount, True)
            elif r1 == r2 or r2 == r3 or r1 == r3:
                # 2 of a kind pays back 1x (no loss, no gain)
                winnings = amount
                payout_str = "Two of a kind! Bet returned."
                color = discord.Color.orange()
                await log_event(self.bot, f"{interaction.user.name} tied in Slots (Two matching)")
            else:
                await log_event(self.bot, f"{interaction.user.name} LOST ${amount} in Slots")
                await record_game(interaction.user.id, amount, -amount, False)
                
            if winnings > 0:
                await update_balance(interaction.user.id, winnings)
                
            embed = discord.Embed(title="🎰 Slots 🎰", color=color)
            
            result_str = f"**[ {r1} | {r2} | {r3} ]**"
            
            final_profit = winnings - amount
            if final_profit > 0:
                profit_display = f"💰 **Profit:** +${final_profit}"
            else:
                profit_display = f"💸 **Loss:** -${abs(final_profit)}"
                
            embed.description = (
                f">>> **Roll:**\n"
                f"🎰 {result_str}\n\n"
                f"**Result:** {payout_str}\n\n"
                f"{profit_display}"
            )
            
            view = PlayAgainView(self.slots.callback, self, interaction, amount)
            await interaction.edit_original_response(embed=embed, view=view)
        finally:
            from cogs.utils import release_game_lock
            release_game_lock(interaction.user.id)

async def setup(bot):
    await bot.add_cog(SlotsCog(bot))
