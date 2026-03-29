import discord
from discord import app_commands
from discord.ext import commands
import random
from database import get_active_lottery, buy_lottery_ticket, process_bet, add_lottery_pool
from logger import log_event

class LotteryCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    lottery = app_commands.Group(name="lottery", description="Lottery commands")

    @lottery.command(name="status", description="Check the current active lottery")
    async def status(self, interaction: discord.Interaction):
        active = await get_active_lottery()
        if not active or not active["is_active"]:
            await interaction.response.send_message("ℹ️ | There is currently no active lottery.", ephemeral=True)
            return
            
        embed = discord.Embed(title="🎟️ Active Lottery", color=discord.Color.gold())
        embed.description = (
            f"💰 **Current Pool:** `${active['current_pool']:,}`\n"
            f"🎫 **Ticket Price:** `${active['ticket_price']:,}`\n"
            f"🎯 **Pick 5 Numbers (1-50)**\n\n"
            f"Use `/lottery buy` to get your tickets before the draw!"
        )
        await interaction.response.send_message(embed=embed)

    @lottery.command(name="buy", description="Buy one or multiple lottery tickets (Pick numbers or leave blank for Quick Pick)")
    @app_commands.describe(quantity="How many tickets to buy (Max 100)", n1="Number 1", n2="Number 2", n3="Number 3", n4="Number 4", n5="Number 5")
    async def buy(self, interaction: discord.Interaction, quantity: int = 1, n1: int = None, n2: int = None, n3: int = None, n4: int = None, n5: int = None):
        if quantity < 1 or quantity > 100:
            await interaction.response.send_message("❌ | Quantity must be between 1 and 100.", ephemeral=True)
            return
            
        active = await get_active_lottery()
        if not active or not active["is_active"]:
            await interaction.response.send_message("❌ | There is currently no active lottery.", ephemeral=True)
            return
            
        price = active["ticket_price"]
        total_cost = price * quantity
        user_picks = [n for n in [n1, n2, n3, n4, n5] if n is not None]
        
        is_quick_pick = False
        if len(user_picks) == 0:
            is_quick_pick = True
        elif len(user_picks) == 5:
            # Validate picks
            if any(n < 1 or n > 50 for n in user_picks):
                await interaction.response.send_message("❌ | All numbers must be between 1 and 50.", ephemeral=True)
                return
            if len(set(user_picks)) != 5:
                await interaction.response.send_message("❌ | You must pick 5 UNIQUE numbers.", ephemeral=True)
                return
            picks = sorted(list(user_picks))
        else:
            await interaction.response.send_message("❌ | You must provide either ALL 5 numbers or NONE for a random Quick Pick.", ephemeral=True)
            return

        # Deduct the total cost
        if not await process_bet(interaction, total_cost):
            return
            
        await add_lottery_pool(total_cost)
        
        for _ in range(quantity):
            if is_quick_pick:
                picks = sorted(random.sample(range(1, 51), 5))
            await buy_lottery_ticket(interaction.user.id, picks[0], picks[1], picks[2], picks[3], picks[4])
        
        embed = discord.Embed(title="🎫 Lottery Tickets Purchased!", color=discord.Color.green())
        if is_quick_pick:
            embed.description = (
                f"**Quantity:** `{quantity} Quick Picks`\n\n"
                f"💸 **Total Cost:** `${total_cost:,}` added to the pool!\n"
                f"Good luck on the draw!"
            )
        else:
            embed.description = (
                f"**Your Numbers:** `{' '.join(map(str, picks))}`\n"
                f"**Quantity:** `{quantity}x Identical Shares`\n\n"
                f"💸 **Total Cost:** `${total_cost:,}` added to the pool!\n"
                f"Good luck on the draw!"
            )
        
        await log_event(self.bot, f"{interaction.user.name} bought {quantity} lottery tickets for ${total_cost}. Quick Pick: {is_quick_pick}")
        await interaction.response.send_message(embed=embed)

async def setup(bot):
    await bot.add_cog(LotteryCog(bot))
