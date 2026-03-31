import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from database import update_balance, record_game
from logger import log_event
from cogs.utils_view import PlayAgainView
from cogs.theme import Color

# House edge ~55 % — 0x lands 68.4 % of the time
MULTIPLIERS = [1.2,  1.5,  3.0,  6.0,  0.0]
WEIGHTS     = [250,   55,    8,    3,  684]

def get_wheel_visual(mult):
    if mult == 1.2: return "🔵 1.2x"
    if mult == 1.5: return "🟩 1.5x"
    if mult == 3.0: return "🟪 3.0x"
    if mult == 6.0: return "🌟 6.0x"
    return "💀 0.0x"


class WheelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="wheel", description="Spin the Big Wheel!")
    @app_commands.describe(amount="Amount to bet")
    async def wheel(self, interaction: discord.Interaction, amount: int):
        from cogs.utils import acquire_game_lock, release_game_lock
        if not await acquire_game_lock(interaction.user.id, interaction):
            return
        try:
            from database import process_bet
            if not await process_bet(interaction, amount):
                return

            embed = discord.Embed(title="🎡  Big Wheel", color=Color.PLAYING)
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
            embed.description = "Spinning the Big Wheel... 🎡"
            await interaction.response.send_message(embed=embed)

            await asyncio.sleep(2.0)

            mult     = random.choices(MULTIPLIERS, weights=WEIGHTS, k=1)[0]
            winnings = int(amount * mult)

            if winnings > 0:
                await update_balance(interaction.user.id, winnings)
                profit = winnings - amount
                if profit > 0:
                    embed.color     = Color.WIN
                    pf_str          = f"💰  **Profit:** +${profit:,}"
                    await log_event(self.bot, f"{interaction.user.name} WON ${profit} in Big Wheel (x{mult})")
                    await record_game(interaction.user.id, amount, profit, True)
                else:
                    embed.color = Color.WARNING
                    pf_str      = f"➖  **Returned:** ${winnings:,}  (no profit)"
                    await log_event(self.bot, f"{interaction.user.name} tied in Big Wheel (x{mult})")
                res_str = f">>> **Wheel stopped on:** `{get_wheel_visual(mult)}`\n\n{pf_str}"
            else:
                embed.color = Color.LOSS
                res_str     = (
                    f">>> **Wheel stopped on:** `{get_wheel_visual(mult)}`\n\n"
                    f"💸  **Loss:** -${amount:,}"
                )
                await log_event(self.bot, f"{interaction.user.name} LOST ${amount} in Big Wheel")
                await record_game(interaction.user.id, amount, -amount, False)

            embed.description = res_str
            view = PlayAgainView(self.wheel.callback, self, interaction, amount)
            try:
                await interaction.edit_original_response(embed=embed, view=view)
            except Exception:
                pass
        finally:
            release_game_lock(interaction.user.id)


async def setup(bot):
    await bot.add_cog(WheelCog(bot))