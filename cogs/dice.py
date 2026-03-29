import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from database import get_balance, update_balance, record_game
from cogs.linker import is_linked
from logger import log_event
from cogs.utils_view import PlayAgainView

class DiceCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="dice", description="Roll two 6-sided dice")
    @app_commands.describe(amount="Amount to bet", choice="Over, Under, or Exactly 7")
    @app_commands.choices(choice=[
        app_commands.Choice(name="Over 7", value="over"),
        app_commands.Choice(name="Under 7", value="under"),
        app_commands.Choice(name="Exactly 7", value="exactly"),
    ])
    async def dice(self, interaction: discord.Interaction, amount: int, choice: app_commands.Choice[str]):
        from cogs.utils import acquire_game_lock
        if not await acquire_game_lock(interaction.user.id, interaction): return
        try:
            from database import process_bet
            if not await process_bet(interaction, amount):
                return
            
            embed = discord.Embed(title="🎲 Dice Roll", color=discord.Color.blue())
            embed.set_author(name=f"{interaction.user.display_name} is playing", icon_url=interaction.user.display_avatar.url)
            embed.description = f"Rolling the dice... 🎲 🎲"
            await interaction.response.send_message(embed=embed)
            
            await asyncio.sleep(1.0)
            
            d1 = random.randint(1, 6)
            d2 = random.randint(1, 6)
            total = d1 + d2
            
            # Payout Multipliers
            mult = 0.0
            if choice.value == "over" and total > 7:
                mult = 2.1
            elif choice.value == "under" and total < 7:
                mult = 2.1
            elif choice.value == "exactly" and total == 7:
                mult = 5.0
                
            winnings = int(amount * mult)
            
            if winnings > 0:
                await update_balance(interaction.user.id, winnings)
                final_profit = winnings - amount
                embed.color = discord.Color.green()
                res_str = (
                    f">>> **Roll Result:  [ {d1} ] + [ {d2} ]  =  {total}**\n\n"
                    f"**You guessed:** `{choice.name}`\n"
                    f"**Status:** Correct!\n\n"
                    f"💰 **Profit:** +${final_profit}"
                )
                await log_event(self.bot, f"{interaction.user.name} WON ${final_profit} in Dice (Guessed {choice.name})")
                await record_game(interaction.user.id, amount, final_profit, True)
            else:
                embed.color = discord.Color.red()
                res_str = (
                    f">>> **Roll Result:  [ {d1} ] + [ {d2} ]  =  {total}**\n\n"
                    f"**You guessed:** `{choice.name}`\n"
                    f"**Status:** Incorrect.\n\n"
                    f"💸 **Loss:** -${amount}"
                )
                await log_event(self.bot, f"{interaction.user.name} LOST ${amount} in Dice (Guessed {choice.name})")
                await record_game(interaction.user.id, amount, -amount, False)

            embed.description = res_str
            
            view = PlayAgainView(self.dice.callback, self, interaction, amount, choice)
            try:
                await interaction.edit_original_response(embed=embed, view=view)
            except:
                pass
        finally:
            from cogs.utils import release_game_lock
            release_game_lock(interaction.user.id)

async def setup(bot):
    await bot.add_cog(DiceCog(bot))
