import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from database import get_balance, update_balance, record_game, process_bet
from cogs.linker import is_linked
from logger import log_event
from cogs.utils_view import PlayAgainView

def get_plane_visual(mult):
    if mult < 1.5:
        return "🛫 ☁️  ☁️  ☁️  ☁️  ☁️"
    elif mult < 2.5:
        return "☁️  🛫  ☁️  ☁️  ☁️  ☁️"
    elif mult < 4.0:
        return "☁️  ☁️  🛫  ☁️  ☁️  ☁️"
    elif mult < 10.0:
        return "☁️  ☁️  ☁️  🛫  ☁️  ☁️"
    else:
        return "☁️  ☁️  ☁️  ☁️  ☁️  🚀"

class CrashView(discord.ui.View):
    def __init__(self, bot, user_id, user_name, bet, **kwargs):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id
        self.user_name = user_name
        self.bet = bet
        self.auto_cashout = kwargs.get('auto_cashout', None)
        self.current_mult = 1.00
        self.crashed = False
        self.cashed_out = False
        self.crash_point = max(1.00, 0.90 / (1.0 - random.random()))
        
    @discord.ui.button(label="Cash Out", style=discord.ButtonStyle.success)
    async def cash_out(self, interaction: discord.Interaction, button: discord.ui.Button):
        if getattr(self, '_processing', False): return
        self._processing = True
        
        if interaction.user.id != self.user_id:
            self._processing = False
            await interaction.response.send_message("Not your game!", ephemeral=True)
            return
            
        if self.crashed or self.cashed_out:
            self._processing = False
            if not interaction.response.is_done():
                try: await interaction.response.defer()
                except: pass
            return
            
        await interaction.response.defer()
        await self.trigger_cashout(interaction)
        self._processing = False

    async def trigger_cashout(self, interaction: discord.Interaction = None, original_interaction: discord.Interaction = None):
        self.cashed_out = True
        winnings = int(self.bet * self.current_mult)
        await update_balance(self.user_id, winnings)
        profit = winnings - self.bet
        await log_event(self.bot, f"{self.user_name} WON ${profit} in Crash (Bailed at {self.current_mult:.2f}x)")
        await record_game(self.user_id, self.bet, profit, True)
        
        embed = discord.Embed(title="✈️ Crash - Cashed Out!", color=discord.Color.green())
        embed.description = (
            f">>> **Escaped at:** `{self.current_mult:.2f}x`!\n\n"
            f"{get_plane_visual(self.current_mult)}\n\n"
            f"💰 **Profit:** +${winnings - self.bet}"
        )
        
        for child in self.children:
            child.disabled = True
            
        cog = self.bot.get_cog("CrashCog")
        final_view = PlayAgainView(cog.crash.callback, cog, interaction or original_interaction, self.bet, self.auto_cashout) if cog else self
            
        if interaction:
            try:
                await interaction.edit_original_response(embed=embed, view=final_view)
            except Exception as e:
                print(f"[CRASHOUT] Edit Error (interaction): {e}")
        elif original_interaction:
            try:
                await original_interaction.edit_original_response(embed=embed, view=final_view)
            except Exception as e:
                print(f"[CRASHOUT] Edit Error (original): {e}")
        self.stop()

class CrashCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="crash", description="Play the Aviator Crash game")
    @app_commands.describe(amount="Amount to bet", auto_cashout="Target multiplier to auto cash you out (optional)")
    async def crash(self, interaction: discord.Interaction, amount: int, auto_cashout: float = None):
        from cogs.utils import acquire_game_lock
        if not await acquire_game_lock(interaction.user.id, interaction): return
        try:
            await interaction.response.defer()
            if auto_cashout is not None and auto_cashout <= 1.0:
                await interaction.followup.send("❌ | Auto cashout must be greater than 1.0x.", ephemeral=True)
                return

            if not await process_bet(interaction, amount):
                return

            view = CrashView(self.bot, interaction.user.id, interaction.user.name, amount, auto_cashout=auto_cashout)
            
            embed = discord.Embed(title="✈️ Crash", color=discord.Color.blue())
            embed.set_author(name=f"{interaction.user.display_name} is playing", icon_url=interaction.user.display_avatar.url)
            embed.description = (
                f">>> **Multiplier:** `1.00x`\n\n"
                f"{get_plane_visual(1.0)}\n\n"
                f"💰 **Bet:** ${amount}"
            )
            if auto_cashout:
                embed.set_footer(text=f"Auto-Cashout: {auto_cashout}x")
            await interaction.edit_original_response(embed=embed, view=view)
            
            # Game loop
            while not view.cashed_out and not view.crashed:
                await asyncio.sleep(1.5)
                if view.cashed_out:
                    break
                    
                # Increase mult
                growth = random.uniform(1.05, 1.2)
                view.current_mult *= growth
                
                # If auto_cashout is reached safely before crash
                if auto_cashout and view.current_mult >= auto_cashout:
                    if view.crash_point > auto_cashout:
                        view.current_mult = auto_cashout
                        await view.trigger_cashout(original_interaction=interaction)
                        break
                
                if view.current_mult >= view.crash_point:
                    view.crashed = True
                    view.current_mult = view.crash_point
                    
                    embed = discord.Embed(title="💥 CRASHED!", color=discord.Color.red())
                    embed.description = (
                        f">>> **Multiplier:** `{view.current_mult:.2f}x`\n\n"
                        f"🔥 ☁️  ☁️  ☁️  ☁️  ☁️\n\n"
                        f"💸 **Lost:** -${amount}"
                    )
                    try:
                        pa_view = PlayAgainView(self.crash.callback, self, interaction, amount, auto_cashout)
                        await interaction.edit_original_response(embed=embed, view=pa_view)
                        await log_event(self.bot, f"{interaction.user.name} LOST ${amount} in Crash (Max was {view.current_mult:.2f}x)")
                        await record_game(interaction.user.id, amount, -amount, False)
                    except:
                        pass
                    view.stop()
                    break
                else:
                    embed = discord.Embed(title="✈️ Crash", color=discord.Color.blue())
                    embed.description = (
                        f">>> **Multiplier:** `{view.current_mult:.2f}x`\n\n"
                        f"{get_plane_visual(view.current_mult)}\n\n"
                        f"💰 **Bet:** ${amount}"
                    )
                    if auto_cashout:
                        embed.set_footer(text=f"Auto-Cashout: {auto_cashout}x")
                    try:
                        if not view.cashed_out and not view.crashed:
                            await interaction.edit_original_response(embed=embed, view=view)
                    except:
                        pass
        finally:
            from cogs.utils import release_game_lock
            release_game_lock(interaction.user.id)

async def setup(bot):
    await bot.add_cog(CrashCog(bot))
