import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from database import get_balance, update_balance, record_game
from cogs.linker import is_linked
from logger import log_event
from cogs.utils_view import PlayAgainView

ROWS = 8
PAYOUTS = [15.0, 3.0, 1.0, 0.6, 0.3, 0.6, 1.0, 3.0, 15.0]
IDEOGRAPHIC_SPACE = "　"

def render_board(step, moves):
    current_pos = sum(moves[:step])
    lines = []
    
    for r in range(ROWS):
        pegs = ["⚪"] * (r + 1)
        if r == step:
            pegs[current_pos] = "🔴"
        
        padding = IDEOGRAPHIC_SPACE * (ROWS - r)
        row_str = padding + "".join(pegs)
        lines.append(row_str)
        
    # Draw bottom buckets
    bucket_str = "[15] [3] [1] [.6] [.3] [.6] [1] [3] [15]"
    
    return "\n".join(lines) + f"\n\n**Buckets:**\n`{bucket_str}`"

class PlinkoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="plinko", description="Drop the ball down the Plinko pyramid!")
    @app_commands.describe(amount="Amount to bet")
    async def plinko(self, interaction: discord.Interaction, amount: int):
        from cogs.utils import acquire_game_lock
        if not await acquire_game_lock(interaction.user.id, interaction): return
        try:
            from database import process_bet
            await interaction.response.defer()
            if not await process_bet(interaction, amount):
                return
            
            moves = [random.choice([0, 1]) for _ in range(ROWS)]
            
            embed = discord.Embed(title="🔴 Plinko", color=discord.Color.blue())
            embed.set_author(name=f"{interaction.user.display_name} is playing", icon_url=interaction.user.display_avatar.url)
            embed.description = render_board(0, moves)
            await interaction.edit_original_response(embed=embed)
            
            for step in range(1, ROWS):
                await asyncio.sleep(1.0)
                embed.description = render_board(step, moves)
                try:
                    await interaction.edit_original_response(embed=embed)
                except:
                    pass
                    
            # Final landing
            await asyncio.sleep(1.0)
            final_pos = sum(moves)
            mult = PAYOUTS[final_pos]
            winnings = int(amount * mult)
            
            if winnings > 0:
                await update_balance(interaction.user.id, winnings)
                
            final_profit = winnings - amount
            
            if final_profit > 0:
                embed.color = discord.Color.green()
                res_str = f"**Result:** Landed in `{mult}x` bucket.\n\n💰 **Profit:** +${final_profit}"
                await log_event(self.bot, f"{interaction.user.name} WON ${final_profit} in Plinko (x{mult})")
                await record_game(interaction.user.id, amount, final_profit, True)
            elif final_profit < 0:
                embed.color = discord.Color.red()
                res_str = f"**Result:** Landed in `{mult}x` bucket.\n\n💸 **Loss:** -${abs(final_profit)}"
                await log_event(self.bot, f"{interaction.user.name} LOST ${abs(final_profit)} in Plinko (x{mult})")
                await record_game(interaction.user.id, amount, final_profit, False)
            else:
                embed.color = discord.Color.orange()
                res_str = f"**Result:** Landed in `{mult}x` bucket.\n\n➖ **Broke Even.**"
                await log_event(self.bot, f"{interaction.user.name} tied in Plinko (x{mult})")
                
            # Draw final board
            lines = []
            for r in range(ROWS):
                pegs = ["⚪"] * (r + 1)
                lines.append(IDEOGRAPHIC_SPACE * (ROWS - r) + "".join(pegs))
            
            pointer = ["⬛"] * 9
            pointer[final_pos] = "🔴"
            pointer_str = "".join(pointer)
            bucket_str = "[15][3 ][1 ][.6][.3][.6][1 ][3 ][15]"
            
            final_board = "\n".join(lines) + f"\n{pointer_str}\n`{bucket_str}`"
            
            embed.description = (
                f">>> {final_board}\n\n"
                f"{res_str}"
            )
            
            view = PlayAgainView(self.plinko.callback, self, interaction, amount)
            try:
                await interaction.edit_original_response(embed=embed, view=view)
            except:
                pass
        finally:
            from cogs.utils import release_game_lock
            release_game_lock(interaction.user.id)

async def setup(bot):
    await bot.add_cog(PlinkoCog(bot))
