import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from database import update_balance, record_game
from logger import log_event
from cogs.utils_view import PlayAgainView

# Big Wheel configuration for a 10% House Edge
MULTIPLIERS = [1.5, 2.0, 5.0, 10.0, 0.0]
WEIGHTS = [400, 100, 10, 5, 485] 

def get_wheel_visual(mult):
    if mult == 1.5: return "🔵 1.5x"
    if mult == 2.0: return "🟩 2.0x"
    if mult == 5.0: return "🟪 5.0x"
    if mult == 10.0: return "🌟 10.0x"
    return "💀 0.0x"

class WheelCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="wheel", description="Spin the Big Wheel!")
    @app_commands.describe(amount="Amount to bet")
    async def wheel(self, interaction: discord.Interaction, amount: int):
        from cogs.utils import acquire_game_lock
        if not await acquire_game_lock(interaction.user.id, interaction): return
        try:
            from database import process_bet
            if not await process_bet(interaction, amount):
                return
    
            embed = discord.Embed(title="🎡 Big Wheel", color=discord.Color.blue())
            embed.set_author(name=f"{interaction.user.display_name} is playing", icon_url=interaction.user.display_avatar.url)
            embed.description = "Spinning the Big Wheel... 🎡"
            await interaction.response.send_message(embed=embed)
            
            await asyncio.sleep(2.0)
            
            mult = random.choices(MULTIPLIERS, weights=WEIGHTS, k=1)[0]
            
            winnings = int(amount * mult)
            
            # Payout the winnings (as amount was already deducted)
            if winnings > 0:
                await update_balance(interaction.user.id, winnings)
                final_profit = winnings - amount
                
                if final_profit > 0:
                    embed.color = discord.Color.green()
                    pf_str = f"💰 **Profit:** +${final_profit}"
                    await log_event(self.bot, f"{interaction.user.name} WON ${final_profit} in Big Wheel (x{mult})")
                    await record_game(interaction.user.id, amount, final_profit, True)
                else:
                    embed.color = discord.Color.orange()
                    pf_str = f"➖ **Returned:** ${winnings} (No Profit)"
                    await log_event(self.bot, f"{interaction.user.name} tied in Big Wheel (x{mult})")
                    
                res_str = (
                    f">>> **The wheel stopped on:** `{get_wheel_visual(mult)}`\n\n"
                    f"{pf_str}"
                )
            else:
                embed.color = discord.Color.red()
                res_str = (
                    f">>> **The wheel stopped on:** `{get_wheel_visual(mult)}`\n\n"
                    f"💸 **Loss:** -${amount}"
                )
                await log_event(self.bot, f"{interaction.user.name} LOST ${amount} in Big Wheel")
                await record_game(interaction.user.id, amount, -amount, False)
    
            embed.description = res_str
            
            view = PlayAgainView(self.wheel.callback, self, interaction, amount)
            try:
                await interaction.edit_original_response(embed=embed, view=view)
            except:
                pass
        finally:
            from cogs.utils import release_game_lock
            release_game_lock(interaction.user.id)

async def setup(bot):
    await bot.add_cog(WheelCog(bot))
