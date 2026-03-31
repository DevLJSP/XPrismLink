import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from database import get_balance, update_balance, record_game
from logger import log_event
from cogs.utils_view import PlayAgainView
from cogs.theme import Color

# ── Wheel ─────────────────────────────────────────────────────────────────────
def _build_wheel():
    wheel = [
        {"type": "green", "val": 0,  "label": "🟢 0"},
        {"type": "green", "val": 37, "label": "🟢 00"},
    ]
    for i in range(1, 37):
        emoji = "🔴" if i % 2 != 0 else "⚫"
        kind  = "red"   if i % 2 != 0 else "black"
        wheel.append({"type": kind, "val": i, "label": f"{emoji} {i}"})
    return wheel

BASE_WHEEL   = _build_wheel()
MASTER_WHEEL = BASE_WHEEL * 3


def _window(center: int) -> str:
    lines = []
    for offset in range(-2, 3):
        slot = MASTER_WHEEL[center + offset]
        lines.append(f"**► {slot['label']} ◄**" if offset == 0 else f"    {slot['label']}")
    return "\n".join(lines)


class Roulette(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.animation_enabled = True

    @app_commands.command(name="roulette", description="Bet on red/black, even/odd, or a specific number (0–36)")
    @app_commands.describe(
        amount="Amount to bet",
        bet_on="red · black · even · odd · green · or a number 0–36",
    )
    async def roulette(self, interaction: discord.Interaction, amount: int, bet_on: str):
        from cogs.utils import acquire_game_lock, release_game_lock
        if not await acquire_game_lock(interaction.user.id, interaction):
            return
        try:
            bet_on = bet_on.lower().strip()
            await interaction.response.defer()

            from database import process_bet
            if not await process_bet(interaction, amount):
                return

            # ── Validate ─────────────────────────────────────────────────────
            specific = None
            if bet_on in ("red", "black", "even", "odd", "green"):
                pass
            elif bet_on.isdigit() and 0 <= int(bet_on) <= 36:
                specific = int(bet_on)
            else:
                await interaction.followup.send(
                    "❌  Invalid bet. Choose `red`, `black`, `even`, `odd`, `green`, or a number `0–36`.",
                    ephemeral=True,
                )
                return

            # ── Spin ─────────────────────────────────────────────────────────
            w       = len(BASE_WHEEL)
            win_idx = random.randint(w, w * 2 - 1)
            win_slot = MASTER_WHEEL[win_idx]

            if self.animation_enabled:
                await interaction.edit_original_response(
                    content=f"🎰  Betting **${amount:,}** on **{bet_on.upper()}**…"
                )
                raw_moves  = [16, 8, 4, 3, 1, 1, 1]
                raw_delays = [0.30, 0.50, 0.80, 1.00, 1.30, 1.60, 2.00]
                if random.choice([True, False]):
                    raw_moves.append(1); raw_delays.append(2.50)

                moves, delays = [], []
                for i, (m, d) in enumerate(zip(raw_moves, raw_delays)):
                    moves.append(m); delays.append(d)
                    if i < 3 and random.random() < 0.25:
                        moves.append(m); delays.append(d)

                frame_centres = []
                cur = win_idx
                for m in reversed(moves):
                    frame_centres.insert(0, cur)
                    cur -= m + random.choice([3, 2, 1, 0, -1])

                for idx, delay in zip(frame_centres, delays):
                    idx = max(2, min(idx, len(MASTER_WHEEL) - 3))
                    spin_embed = discord.Embed(title="🎡  Roulette", color=Color.GOLD)
                    spin_embed.description = f">>> {_window(idx)}"
                    await interaction.edit_original_response(content=None, embed=spin_embed)
                    await asyncio.sleep(max(0.1, delay + random.uniform(-0.1, 0.1)))
            else:
                await interaction.edit_original_response(
                    content=f"🎰  Betting **${amount:,}** on **{bet_on.upper()}**…"
                )

            # ── Outcome ───────────────────────────────────────────────────────
            # Payouts reduced — house edge ~25–50 % depending on bet type
            # Color/parity: 1.5x (was 2x) → house edge ~42 %
            # Specific number: 18x (was 36x) → house edge ~50 %
            # Green: 18x (was 36x)
            rv, rc = win_slot["val"], win_slot["type"]
            won, mult = False, 0

            if specific is not None:
                if specific == rv:          won, mult = True, 18
            elif bet_on == "red"   and rc == "red":    won, mult = True, 1.5
            elif bet_on == "black" and rc == "black":  won, mult = True, 1.5
            elif bet_on == "green" and rc == "green":  won, mult = True, 18
            elif bet_on == "even"  and rv != 0 and rv % 2 == 0: won, mult = True, 1.5
            elif bet_on == "odd"   and rv != 0 and rv % 2 != 0: won, mult = True, 1.5

            profit = int(amount * mult - amount) if won else -amount
            if won:
                await update_balance(interaction.user.id, int(amount * mult))

            embed = discord.Embed(
                title="🎡  Roulette",
                color=Color.WIN if won else Color.LOSS,
            )
            embed.description = (
                f">>> {_window(win_idx)}\n\n"
                f"**Bet:** `{bet_on.capitalize()}`   "
                f"**Result:** {'✅ Correct!' if won else '❌ Incorrect'}\n\n"
                + (f"💰  **Profit:** +${profit:,}" if won else f"💸  **Loss:** -${abs(profit):,}")
            )
            embed.set_footer(text=f"Balance: ${await get_balance(interaction.user.id):,}")

            pa = PlayAgainView(self.roulette.callback, self, interaction, amount, bet_on)
            await interaction.edit_original_response(content=None, embed=embed, view=pa)

            if won:
                await log_event(self.bot, f"{interaction.user.name} WON ${profit} in Roulette ({bet_on})")
                await record_game(interaction.user.id, amount, profit, True)
            else:
                await log_event(self.bot, f"{interaction.user.name} LOST ${amount} in Roulette ({bet_on})")
                await record_game(interaction.user.id, amount, -amount, False)
        finally:
            release_game_lock(interaction.user.id)


async def setup(bot):
    await bot.add_cog(Roulette(bot))