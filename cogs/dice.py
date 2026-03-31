import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from database import update_balance, record_game
from logger import log_event
from cogs.utils_view import PlayAgainView
from cogs.theme import Color

# Payouts cut — house edge ~44 %
# Over/Under 7: prob ~41.7 % → 1.5x  (was 2.1x)
# Exactly 7:   prob ~16.7 % → 3.0x  (was 5.0x)


class DiceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="dice", description="Roll two 6-sided dice")
    @app_commands.describe(amount="Amount to bet", choice="Over 7, Under 7, or Exactly 7")
    @app_commands.choices(choice=[
        app_commands.Choice(name="Over 7",    value="over"),
        app_commands.Choice(name="Under 7",   value="under"),
        app_commands.Choice(name="Exactly 7", value="exactly"),
    ])
    async def dice(self, interaction: discord.Interaction, amount: int, choice: app_commands.Choice[str]):
        from cogs.utils import acquire_game_lock, release_game_lock
        if not await acquire_game_lock(interaction.user.id, interaction):
            return
        try:
            from database import process_bet
            if not await process_bet(interaction, amount):
                return

            embed = discord.Embed(title="🎲  Dice Roll", color=Color.PLAYING)
            embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
            embed.description = "Rolling the dice...  🎲 🎲"
            await interaction.response.send_message(embed=embed)

            await asyncio.sleep(1.0)

            d1    = random.randint(1, 6)
            d2    = random.randint(1, 6)
            total = d1 + d2

            mult = 0.0
            if   choice.value == "over"    and total > 7: mult = 1.5
            elif choice.value == "under"   and total < 7: mult = 1.5
            elif choice.value == "exactly" and total == 7: mult = 3.0

            winnings = int(amount * mult)

            if winnings > 0:
                await update_balance(interaction.user.id, winnings)
                profit = winnings - amount
                embed.color = Color.WIN
                res_str = (
                    f">>> **Roll:**  `[ {d1} ]` + `[ {d2} ]`  =  **{total}**\n\n"
                    f"**Guess:** `{choice.name}`  ✅\n\n"
                    f"💰  **Profit:** +${profit:,}"
                )
                await log_event(self.bot, f"{interaction.user.name} WON ${profit} in Dice ({choice.name})")
                await record_game(interaction.user.id, amount, profit, True)
            else:
                embed.color = Color.LOSS
                res_str = (
                    f">>> **Roll:**  `[ {d1} ]` + `[ {d2} ]`  =  **{total}**\n\n"
                    f"**Guess:** `{choice.name}`  ❌\n\n"
                    f"💸  **Loss:** -${amount:,}"
                )
                await log_event(self.bot, f"{interaction.user.name} LOST ${amount} in Dice ({choice.name})")
                await record_game(interaction.user.id, amount, -amount, False)

            embed.description = res_str
            view = PlayAgainView(self.dice.callback, self, interaction, amount, choice)
            try:
                await interaction.edit_original_response(embed=embed, view=view)
            except Exception:
                pass
        finally:
            release_game_lock(interaction.user.id)


async def setup(bot):
    await bot.add_cog(DiceCog(bot))