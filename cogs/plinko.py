import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from database import update_balance, record_game
from logger import log_event
from cogs.utils_view import PlayAgainView
from cogs.theme import Color

ROWS = 8
# Original: [15, 3, 1, 0.6, 0.3, 0.6, 1, 3, 15]
# Harder:    edges much lower, center near-wipeout
PAYOUTS = [6.0, 1.2, 0.4, 0.2, 0.05, 0.2, 0.4, 1.2, 6.0]

IDEOGRAPHIC_SPACE = "　"


def render_board(step, moves):
    current_pos = sum(moves[:step])
    lines = []
    for r in range(ROWS):
        pegs = ["⚪"] * (r + 1)
        if r == step:
            pegs[current_pos] = "🔴"
        padding = IDEOGRAPHIC_SPACE * (ROWS - r)
        lines.append(padding + "".join(pegs))
    bucket_str = "[6] [1.2] [.4] [.2] [.05] [.2] [.4] [1.2] [6]"
    return "\n".join(lines) + f"\n\n**Buckets:**\n`{bucket_str}`"


class PlinkoCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="plinko", description="Drop the ball down the Plinko pyramid!")
    @app_commands.describe(amount="Amount to bet")
    async def plinko(self, interaction: discord.Interaction, amount: int):
        from cogs.utils import acquire_game_lock, release_game_lock
        if not await acquire_game_lock(interaction.user.id, interaction):
            return
        try:
            from database import process_bet
            await interaction.response.defer()
            if not await process_bet(interaction, amount):
                return

            moves = [random.choice([0, 1]) for _ in range(ROWS)]

            embed = discord.Embed(title="🔴  Plinko", color=Color.PLAYING)
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
            embed.description = render_board(0, moves)
            await interaction.edit_original_response(embed=embed)

            for step in range(1, ROWS):
                await asyncio.sleep(1.0)
                embed.description = render_board(step, moves)
                try:
                    await interaction.edit_original_response(embed=embed)
                except Exception:
                    pass

            await asyncio.sleep(1.0)
            final_pos = sum(moves)
            mult      = PAYOUTS[final_pos]
            winnings  = int(amount * mult)

            if winnings > 0:
                await update_balance(interaction.user.id, winnings)

            profit = winnings - amount

            if profit > 0:
                embed.color = Color.WIN
                res_str = f"**Result:** Landed in `{mult}x` bucket.\n\n💰  **Profit:** +${profit:,}"
                await log_event(self.bot, f"{interaction.user.name} WON ${profit} in Plinko (x{mult})")
                await record_game(interaction.user.id, amount, profit, True)
            elif profit < 0:
                embed.color = Color.LOSS
                res_str = f"**Result:** Landed in `{mult}x` bucket.\n\n💸  **Loss:** -${abs(profit):,}"
                await log_event(self.bot, f"{interaction.user.name} LOST ${abs(profit)} in Plinko (x{mult})")
                await record_game(interaction.user.id, amount, profit, False)
            else:
                embed.color = Color.WARNING
                res_str = f"**Result:** Landed in `{mult}x` bucket.\n\n➖  **Break even.**"

            # Final static board
            lines = []
            for r in range(ROWS):
                lines.append(IDEOGRAPHIC_SPACE * (ROWS - r) + "".join(["⚪"] * (r + 1)))

            pointer = ["⬛"] * 9
            pointer[final_pos] = "🔴"
            bucket_str = "[6 ][1.2][.4][.2][.05][.2][.4][1.2][6 ]"

            embed.description = (
                f">>> {''.join(lines) if False else chr(10).join(lines)}\n"
                f"{''.join(pointer)}\n`{bucket_str}`\n\n"
                f"{res_str}"
            )

            view = PlayAgainView(self.plinko.callback, self, interaction, amount)
            try:
                await interaction.edit_original_response(embed=embed, view=view)
            except Exception:
                pass
        finally:
            release_game_lock(interaction.user.id)


async def setup(bot):
    await bot.add_cog(PlinkoCog(bot))