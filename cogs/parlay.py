import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from database import update_balance, record_game, process_bet
from logger import log_event
from cogs.utils_view import PlayAgainView

class ParlayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    parlay = app_commands.Group(name="parlay", description="Parlay betting commands")

    def get_leg_data(self, leg_val):
        if leg_val == "coin_0":
            return {"name": "🪙 Coins: 0 Heads", "mult": 7.2, "chance": 1/8}
        if leg_val == "coin_1":
            return {"name": "🪙 Coins: 1 Head", "mult": 2.4, "chance": 3/8}
        if leg_val == "coin_2":
            return {"name": "🪙 Coins: 2 Heads", "mult": 2.4, "chance": 3/8}
        if leg_val == "coin_3":
            return {"name": "🪙 Coins: 3 Heads", "mult": 7.2, "chance": 1/8}
        if leg_val == "dice_low":
            return {"name": "🎲 Dice: Low (1-3)", "mult": 2.1, "chance": 15/36}
        if leg_val == "dice_high":
            return {"name": "🎲 Dice: High (4-6)", "mult": 2.1, "chance": 15/36}
        if leg_val == "rou_red":
            return {"name": "🔴 Roulette: Red", "mult": 2.0, "chance": 18/38}
        if leg_val == "rou_black":
            return {"name": "⚫ Roulette: Black", "mult": 2.0, "chance": 18/38}
        return None

    def get_parlay_choices(self):
        return [
            app_commands.Choice(name="Coins: 0 Heads (7.2x)", value="coin_0"),
            app_commands.Choice(name="Coins: 1 Head (2.4x)", value="coin_1"),
            app_commands.Choice(name="Coins: 2 Heads (2.4x)", value="coin_2"),
            app_commands.Choice(name="Coins: 3 Heads (7.2x)", value="coin_3"),
            app_commands.Choice(name="Dice: Under 7 (2.1x)", value="dice_low"),
            app_commands.Choice(name="Dice: Over 7 (2.1x)", value="dice_high"),
            app_commands.Choice(name="Roulette: Red (2.0x)", value="rou_red"),
            app_commands.Choice(name="Roulette: Black (2.0x)", value="rou_black")
        ]

    # ------ COMBO PARLAY ------
    @parlay.command(name="combo", description="Link 2 to 3 bets together. Extra payout for hitting all!")
    @app_commands.describe(amount="Amount to bet", leg1="First bet", leg2="Second bet", leg3="Third bet (optional)")
    async def combo(self, interaction: discord.Interaction, amount: int, leg1: str, leg2: str, leg3: str = None):
        from cogs.utils import acquire_game_lock
        if not await acquire_game_lock(interaction.user.id, interaction): return
        try:
            await interaction.response.defer()
            if not await process_bet(interaction, amount):
                return

            legs_data = [self.get_leg_data(leg1), self.get_leg_data(leg2)]
            if leg3:
                legs_data.append(self.get_leg_data(leg3))
                
            compound_mult = 1.0
            for data in legs_data:
                if not data:
                    await interaction.followup.send("❌ | Invalid leg selected. Please use autocomplete choices.", ephemeral=True)
                    # Re-fund the bet
                    await update_balance(interaction.user.id, amount)
                    return
                compound_mult *= data["mult"]
            
            # Combo parlay bonus (e.g., 10% extra multiplier)
                compound_mult *= 1.10
                compound_mult = round(compound_mult, 2)
                potential_win = int(amount * compound_mult)
            
                embed = discord.Embed(title="🔗 Casino Combo Parlay", color=discord.Color.blue())
                embed.set_author(name=f"{interaction.user.display_name} is playing", icon_url=interaction.user.display_avatar.url)
                embed.description = f"**Wager:** `${amount:,}`\n**Potential Payout:** `${potential_win:,}` (`{compound_mult}x` with 10% Bonus!)\n\n"
        
            for i, data in enumerate(legs_data):
                embed.description += f"**Leg {i+1}:** {data['name']} (Pending...)\n"
            
            await interaction.edit_original_response(embed=embed)
        
            results = []
            for i, data in enumerate(legs_data):
                await asyncio.sleep(1.5)
                won = random.random() < data['chance']
                results.append(won)
            
                embed.description = f"**Wager:** `${amount:,}`\n**Potential Payout:** `${potential_win:,}` (`{compound_mult}x` with 10% Bonus!)\n\n"
                for j, l_data in enumerate(legs_data):
                    if j < i + 1:
                        status = "✅ WON" if results[j] else "❌ LOST"
                        embed.description += f"**Leg {j+1}:** {l_data['name']} -> {status}\n"
                    else:
                        embed.description += f"**Leg {j+1}:** {l_data['name']} (Pending...)\n"
                    
                if not won:
                    embed.color = discord.Color.red()
                    embed.description += f"\n💥 **Parlay busted on Leg {i+1}!**\n💸 **Loss:** -${amount:,}"
                
                    view = PlayAgainView(self.combo.callback, self, interaction, amount, leg1, leg2, leg3)
                    try: await interaction.edit_original_response(embed=embed, view=view)
                    except: pass
                
                    await log_event(self.bot, f"{interaction.user.name} LOST ${amount} in Combo Parlay.")
                    await record_game(interaction.user.id, amount, -amount, False)
                    return
                
                try: await interaction.edit_original_response(embed=embed)
                except: pass
            
                profit = potential_win - amount
                await update_balance(interaction.user.id, potential_win)
            
                embed.color = discord.Color.green()
                embed.description += f"\n🎉 **Parlay CASHED!**\n💰 **Profit:** +${profit:,}"
            
                view = PlayAgainView(self.combo.callback, self, interaction, amount, leg1, leg2, leg3)
                try: await interaction.edit_original_response(embed=embed, view=view)
                except: pass
            
                await log_event(self.bot, f"{interaction.user.name} WON ${profit} from Combo Parlay! ({compound_mult}x)")
                await record_game(interaction.user.id, amount, profit, True)
        finally:
            from cogs.utils import release_game_lock
            release_game_lock(interaction.user.id)

    @combo.autocomplete('leg1')
    @combo.autocomplete('leg2')
    @combo.autocomplete('leg3')
    async def parlay_autocomplete(self, interaction: discord.Interaction, current: str):
        choices = self.get_parlay_choices()
        return [c for c in choices if current.lower() in c.name.lower()][:25]

    # ------ STREAK PARLAY ------
    @parlay.command(name="streak", description="Bet that a single game outcome will hit multiple times in a row!")
    @app_commands.describe(amount="Amount to bet", game="The outcome to streak", count="Number of times (2-10)")
    async def streak(self, interaction: discord.Interaction, amount: int, game: str, count: int):
        from cogs.utils import acquire_game_lock
        if not await acquire_game_lock(interaction.user.id, interaction): return
        try:
            await interaction.response.defer()
            if count < 2 or count > 10:
                await interaction.followup.send("❌ | Streak count must be between 2 and 10.", ephemeral=True)
                return
                
            data = self.get_leg_data(game)
            if not data:
                await interaction.followup.send("❌ | Invalid game choice. Please use autocomplete choices.", ephemeral=True)
                return

            if not await process_bet(interaction, amount):
                return

            compound_mult = (data["mult"] ** count) * 1.10  # 10% bonus
            compound_mult = round(compound_mult, 2)
            potential_win = int(amount * compound_mult)
            
            embed = discord.Embed(title="🔥 Casino Streak Parlay", color=discord.Color.orange())
            embed.set_author(name=f"{interaction.user.display_name} is playing", icon_url=interaction.user.display_avatar.url)
            embed.description = (
                f"**Wager:** `${amount:,}`\n"
                f"**Target:** {data['name']} hitting `{count}` times!\n"
                f"**Potential Payout:** `${potential_win:,}` (`{compound_mult}x` with 10% Bonus!)\n\n"
                f"**Progress:** 0 / {count} ✅\n"
            )
            await interaction.edit_original_response(embed=embed)
        
            for i in range(count):
                await asyncio.sleep(1.0)
                won = random.random() < data['chance']
            
                p_str = "✅ " * (i+1 if won else i)
                embed.description = (
                    f"**Wager:** `${amount:,}`\n"
                    f"**Target:** {data['name']} hitting `{count}` times!\n"
                    f"**Potential Payout:** `${potential_win:,}` (`{compound_mult}x`)\n\n"
                    f"**Progress:** {i+1 if won else i} / {count} \n{p_str}"
                )
            
                if not won:
                    embed.description += f"\n💥 **Streak broken on run {i+1}!**\n💸 **Loss:** -${amount:,}"
                    embed.color = discord.Color.red()
                
                    view = PlayAgainView(self.streak.callback, self, interaction, amount, game, count)
                    try: await interaction.edit_original_response(embed=embed, view=view)
                    except: pass
                
                    await log_event(self.bot, f"{interaction.user.name} LOST ${amount} in Streak Parlay (Count: {count}).")
                    await record_game(interaction.user.id, amount, -amount, False)
                    return
                
                try: await interaction.edit_original_response(embed=embed)
                except: pass

                profit = potential_win - amount
                await update_balance(interaction.user.id, potential_win)
            
                embed.color = discord.Color.green()
                embed.description += f"\n🎉 **STREAK COMPLETED!**\n💰 **Profit:** +${profit:,}"
            
                view = PlayAgainView(self.streak.callback, self, interaction, amount, game, count)
                try: await interaction.edit_original_response(embed=embed, view=view)
                except: pass
            
                await log_event(self.bot, f"{interaction.user.name} WON ${profit} from Streak Parlay! ({compound_mult}x)")
                await record_game(interaction.user.id, amount, profit, True)
        finally:
            from cogs.utils import release_game_lock
            release_game_lock(interaction.user.id)

    @streak.autocomplete('game')
    async def streak_autocomplete(self, interaction: discord.Interaction, current: str):
        choices = self.get_parlay_choices()
        return [c for c in choices if current.lower() in c.name.lower()][:25]

async def setup(bot):
    await bot.add_cog(ParlayCog(bot))
