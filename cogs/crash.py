import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from database import update_balance, record_game, process_bet
from logger import log_event
from cogs.utils_view import PlayAgainView
from cogs.theme import Color

_PLANE_FRAMES = [
    "🛫 ☁️  ☁️  ☁️  ☁️  ☁️",
    "☁️  🛫  ☁️  ☁️  ☁️  ☁️",
    "☁️  ☁️  🛫  ☁️  ☁️  ☁️",
    "☁️  ☁️  ☁️  🛫  ☁️  ☁️",
    "☁️  ☁️  ☁️  ☁️  ☁️  🚀",
]

def _plane(mult: float) -> str:
    if mult < 1.5:  return _PLANE_FRAMES[0]
    if mult < 2.5:  return _PLANE_FRAMES[1]
    if mult < 4.0:  return _PLANE_FRAMES[2]
    if mult < 10.0: return _PLANE_FRAMES[3]
    return _PLANE_FRAMES[4]


import random
import discord

class CrashView(discord.ui.View):
    def __init__(self, bot, user_id: int, user_name: str, bet: int, auto_cashout: float | None = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.user_id = user_id
        self.user_name = user_name
        self.bet = bet
        self.auto_cashout = auto_cashout
        self.current_mult = 1.00
        self.crashed = False
        self.cashed_out = False
        self._processing = False

        # Modo simulador: extremamente punitivo
        roll = random.random()

        if roll < 0.72:
            # 72% das vezes: explode quase na largada
            self.crash_point = round(random.uniform(1.01, 1.15), 2)

        elif roll < 0.93:
            # 21% das vezes: ainda baixo
            self.crash_point = round(random.uniform(1.15, 1.80), 2)

        elif roll < 0.985:
            # 5.5%: sobe um pouco, mas continua ruim
            self.crash_point = round(random.uniform(1.80, 3.50), 2)

        else:
            # 1.5%: raro “milagre” só pra manter o simulador interessante
            self.crash_point = round(random.uniform(3.50, 8.00), 2)

        self.crash_point = max(1.01, self.crash_point)
        self._processing = False

    @discord.ui.button(label="Cash Out", style=discord.ButtonStyle.success, emoji="💰")
    async def cash_out(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._processing or self.crashed or self.cashed_out:
            if not interaction.response.is_done():
                try:
                    await interaction.response.defer()
                except Exception:
                    pass
            return
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("This isn't your game.", ephemeral=True)
            return
        self._processing = True
        await interaction.response.defer()
        await self._do_cashout(interaction)
        self._processing = False

    async def _do_cashout(self, interaction=None, original=None):
        self.cashed_out = True
        winnings = int(self.bet * self.current_mult)
        profit   = winnings - self.bet
        await update_balance(self.user_id, winnings)
        await log_event(self.bot, f"{self.user_name} WON ${profit} in Crash (bailed at {self.current_mult:.2f}x)")
        await record_game(self.user_id, self.bet, profit, True)

        embed = discord.Embed(title="✈️  Crash — Cashed Out!", color=Color.CASHOUT)
        embed.description = (
            f">>> **Escaped at:** `{self.current_mult:.2f}x`\n\n"
            f"{_plane(self.current_mult)}\n\n"
            f"💰  **Profit:** +${profit:,}"
        )
        for child in self.children:
            child.disabled = True

        cog = self.bot.get_cog("CrashCog")
        final_view = (
            PlayAgainView(cog.crash.callback, cog, interaction or original, self.bet, self.auto_cashout)
            if cog else self
        )
        target = interaction or original
        if target:
            try:
                await target.edit_original_response(embed=embed, view=final_view)
            except Exception:
                pass
        self.stop()


class CrashCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="crash", description="Play the Aviator Crash game")
    @app_commands.describe(
        amount="Amount to bet",
        auto_cashout="Auto cash-out at this multiplier (optional, must be > 1.0)",
    )
    async def crash(self, interaction: discord.Interaction, amount: int, auto_cashout: float = None):
        from cogs.utils import acquire_game_lock, release_game_lock
        if not await acquire_game_lock(interaction.user.id, interaction):
            return
        try:
            await interaction.response.defer()
            if auto_cashout is not None and auto_cashout <= 1.0:
                await interaction.followup.send("❌  Auto cash-out must be greater than 1.0×.", ephemeral=True)
                return
            if not await process_bet(interaction, amount):
                return

            view = CrashView(self.bot, interaction.user.id, interaction.user.name, amount, auto_cashout=auto_cashout)

            def _active_embed():
                embed = discord.Embed(title="✈️  Crash", color=Color.PLAYING)
                embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
                embed.description = (
                    f">>> **Multiplier:** `{view.current_mult:.2f}x`\n\n"
                    f"{_plane(view.current_mult)}\n\n"
                    f"💰  **Bet:** ${amount:,}"
                )
                if auto_cashout:
                    embed.set_footer(text=f"Auto cash-out: {auto_cashout}×")
                return embed

            await interaction.edit_original_response(embed=_active_embed(), view=view)

            while not view.cashed_out and not view.crashed:
                await asyncio.sleep(1.5)
                if view.cashed_out:
                    break

                view.current_mult *= random.uniform(1.05, 1.20)

                if auto_cashout and view.current_mult >= auto_cashout:
                    if view.crash_point > auto_cashout:
                        view.current_mult = auto_cashout
                        await view._do_cashout(original=interaction)
                        break

                if view.current_mult >= view.crash_point:
                    view.crashed    = True
                    view.current_mult = view.crash_point
                    embed = discord.Embed(title="💥  Crashed!", color=Color.LOSS)
                    embed.description = (
                        f">>> **Crashed at:** `{view.current_mult:.2f}x`\n\n"
                        f"🔥 ☁️  ☁️  ☁️  ☁️  ☁️\n\n"
                        f"💸  **Loss:** -${amount:,}"
                    )
                    pa = PlayAgainView(self.crash.callback, self, interaction, amount, auto_cashout)
                    try:
                        await interaction.edit_original_response(embed=embed, view=pa)
                    except Exception:
                        pass
                    await log_event(self.bot, f"{interaction.user.name} LOST ${amount} in Crash (crashed at {view.current_mult:.2f}x)")
                    await record_game(interaction.user.id, amount, -amount, False)
                    view.stop()
                    break
                else:
                    try:
                        if not view.cashed_out and not view.crashed:
                            await interaction.edit_original_response(embed=_active_embed(), view=view)
                    except Exception:
                        pass
        finally:
            release_game_lock(interaction.user.id)


async def setup(bot):
    await bot.add_cog(CrashCog(bot))