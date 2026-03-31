import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from database import update_balance, record_game
from logger import log_event
from cogs.utils_view import PlayAgainView
from cogs.theme import Color

EMOJIS = ["🍒", "🍋", "🍉", "🍇", "🔔", "⭐", "💎"]

# Multipliers heavily reduced — house edge ~55 %
# Two-of-a-kind no longer refunds — pure loss
MULTIPLIERS = {
    "🍒": 1.2,
    "🍋": 1.5,
    "🍉": 2.0,
    "🍇": 3.0,
    "🔔": 4.0,
    "⭐": 6.0,
    "💎": 12.0,
}


class SlotsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="slots", description="Play a 3-reel slot machine")
    @app_commands.describe(amount="Amount to bet")
    async def slots(self, interaction: discord.Interaction, amount: int):
        from cogs.utils import acquire_game_lock, release_game_lock
        if not await acquire_game_lock(interaction.user.id, interaction):
            return
        try:
            from database import process_bet
            await interaction.response.defer()
            if not await process_bet(interaction, amount):
                return

            embed = discord.Embed(title="🎰  Slots", color=Color.PLAYING)
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
            embed.description = "Spinning...  🔄 | 🔄 | 🔄\n\n**Bet:** **${}**".format(amount)
            await interaction.edit_original_response(embed=embed)

            await asyncio.sleep(1.0)

            r1, r2, r3 = (random.choice(EMOJIS) for _ in range(3))
            winnings   = 0
            result_str = "No match."

            if r1 == r2 == r3:
                mult       = MULTIPLIERS[r1]
                winnings   = int(amount * mult)
                result_str = f"Jackpot!  {mult}x multiplier!"
                embed.color = Color.WIN
                await log_event(self.bot, f"{interaction.user.name} WON ${winnings - amount} in Slots (Jackpot x{mult})")
                await record_game(interaction.user.id, amount, winnings - amount, True)
            else:
                # Two-of-a-kind: no longer a push — it's a loss
                embed.color = Color.LOSS
                await log_event(self.bot, f"{interaction.user.name} LOST ${amount} in Slots")
                await record_game(interaction.user.id, amount, -amount, False)

            if winnings > 0:
                await update_balance(interaction.user.id, winnings)

            profit = winnings - amount
            if profit > 0:
                pf_display = f"💰  **Profit:** +${profit:,}"
            else:
                pf_display = f"💸  **Loss:** -${abs(profit):,}"

            embed.description = (
                f">>> **Roll:**\n"
                f"🎰  **[ {r1} | {r2} | {r3} ]**\n\n"
                f"**Result:** {result_str}\n\n"
                f"{pf_display}"
            )

            view = PlayAgainView(self.slots.callback, self, interaction, amount)
            await interaction.edit_original_response(embed=embed, view=view)
        finally:
            release_game_lock(interaction.user.id)


async def setup(bot):
    await bot.add_cog(SlotsCog(bot))