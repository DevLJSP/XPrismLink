import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from database import update_balance, record_game, process_bet
from logger import log_event
from cogs.utils_view import PlayAgainView
from cogs.theme import Color

# ─── Leg Registry ────────────────────────────────────────────────────────────
_LEGS = {
    "coin_0":    {"name": "🪙 Coins — 0 Heads",      "mult": 7.2, "chance": 1/8},
    "coin_1":    {"name": "🪙 Coins — 1 Head",       "mult": 2.4, "chance": 3/8},
    "coin_2":    {"name": "🪙 Coins — 2 Heads",      "mult": 2.4, "chance": 3/8},
    "coin_3":    {"name": "🪙 Coins — 3 Heads",      "mult": 7.2, "chance": 1/8},
    "dice_low":  {"name": "🎲 Dice — Low  (1-3)",    "mult": 2.1, "chance": 15/36},
    "dice_high": {"name": "🎲 Dice — High (4-6)",    "mult": 2.1, "chance": 15/36},
    "rou_red":   {"name": "🔴 Roulette — Red",       "mult": 2.0, "chance": 18/38},
    "rou_black": {"name": "⚫ Roulette — Black",     "mult": 2.0, "chance": 18/38},
}

_CHOICES = [
    app_commands.Choice(name="Coins: 0 Heads  (7.2x)", value="coin_0"),
    app_commands.Choice(name="Coins: 1 Head   (2.4x)", value="coin_1"),
    app_commands.Choice(name="Coins: 2 Heads  (2.4x)", value="coin_2"),
    app_commands.Choice(name="Coins: 3 Heads  (7.2x)", value="coin_3"),
    app_commands.Choice(name="Dice: Under 7   (2.1x)", value="dice_low"),
    app_commands.Choice(name="Dice: Over 7    (2.1x)", value="dice_high"),
    app_commands.Choice(name="Roulette: Red   (2.0x)", value="rou_red"),
    app_commands.Choice(name="Roulette: Black (2.0x)", value="rou_black"),
]


class ParlayCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    parlay = app_commands.Group(name="parlay", description="Parlay betting commands")

    # ──────────────────────────────────────────────────────────────────────────
    # /parlay combo
    # ──────────────────────────────────────────────────────────────────────────
    @parlay.command(name="combo", description="Chain 2–3 bets into one parlay with a 10% bonus multiplier")
    @app_commands.describe(
        amount="Amount to wager",
        leg1="First bet",
        leg2="Second bet",
        leg3="Third bet (optional)",
    )
    async def combo(
        self,
        interaction: discord.Interaction,
        amount: int,
        leg1: str,
        leg2: str,
        leg3: str = None,
    ):
        from cogs.utils import acquire_game_lock, release_game_lock

        if not await acquire_game_lock(interaction.user.id, interaction):
            return

        try:
            await interaction.response.defer()

            if not await process_bet(interaction, amount):
                return

            # ── Build leg list ───────────────────────────────────────────────
            leg_keys = [leg1, leg2] + ([leg3] if leg3 else [])
            legs = []
            for key in leg_keys:
                data = _LEGS.get(key)
                if data is None:
                    await interaction.followup.send(
                        "❌  Invalid leg selection — please use the autocomplete options.",
                        ephemeral=True,
                    )
                    await update_balance(interaction.user.id, amount)  # refund
                    return
                legs.append(data)

            # ── Calculate compound multiplier (10 % bonus applied once) ──────
            compound_mult = round(
                1.10 * float.__mul__(*[d["mult"] for d in legs]) if len(legs) == 2
                else 1.10 * legs[0]["mult"] * legs[1]["mult"] * legs[2]["mult"],
                2,
            )
            potential_win = int(amount * compound_mult)

            # ── Initial embed ────────────────────────────────────────────────
            embed = discord.Embed(title="🔗 Combo Parlay", color=Color.PLAYING)
            embed.set_author(
                name=interaction.user.display_name,
                icon_url=interaction.user.display_avatar.url,
            )

            def build_desc(results: list[bool | None]) -> str:
                header = (
                    f"**Wager:** `${amount:,}`\n"
                    f"**Potential payout:** `${potential_win:,}` (`{compound_mult}x` · 10 % bonus)\n\n"
                )
                rows = []
                for i, leg in enumerate(legs):
                    if i >= len(results) or results[i] is None:
                        rows.append(f"**Leg {i+1}:** {leg['name']}  ⏳")
                    elif results[i]:
                        rows.append(f"**Leg {i+1}:** {leg['name']}  ✅")
                    else:
                        rows.append(f"**Leg {i+1}:** {leg['name']}  ❌")
                return header + "\n".join(rows)

            embed.description = build_desc([])
            await interaction.edit_original_response(embed=embed)

            # ── Roll legs one by one ─────────────────────────────────────────
            results: list[bool] = []
            for i, leg in enumerate(legs):
                await asyncio.sleep(1.5)
                won = random.random() < leg["chance"]
                results.append(won)

                embed.description = build_desc(results)

                if not won:
                    embed.color = Color.LOSS
                    embed.description += f"\n\n💥 **Busted on Leg {i+1}!**\n💸 **Loss:** -${amount:,}"
                    view = PlayAgainView(self.combo.callback, self, interaction, amount, leg1, leg2, leg3)
                    await interaction.edit_original_response(embed=embed, view=view)
                    await log_event(self.bot, f"{interaction.user.name} LOST ${amount} in Combo Parlay (bust leg {i+1})")
                    await record_game(interaction.user.id, amount, -amount, False)
                    return

                await interaction.edit_original_response(embed=embed)

            # ── All legs hit ─────────────────────────────────────────────────
            profit = potential_win - amount
            await update_balance(interaction.user.id, potential_win)

            embed.color = Color.WIN
            embed.description += f"\n\n🎉 **Parlay cashed!**\n💰 **Profit:** +${profit:,}"
            view = PlayAgainView(self.combo.callback, self, interaction, amount, leg1, leg2, leg3)
            await interaction.edit_original_response(embed=embed, view=view)
            await log_event(self.bot, f"{interaction.user.name} WON ${profit} in Combo Parlay ({compound_mult}x)")
            await record_game(interaction.user.id, amount, profit, True)

        finally:
            release_game_lock(interaction.user.id)

    @combo.autocomplete("leg1")
    @combo.autocomplete("leg2")
    @combo.autocomplete("leg3")
    async def combo_autocomplete(self, interaction: discord.Interaction, current: str):
        return [c for c in _CHOICES if current.lower() in c.name.lower()][:25]

    # ──────────────────────────────────────────────────────────────────────────
    # /parlay streak
    # ──────────────────────────────────────────────────────────────────────────
    @parlay.command(name="streak", description="Bet that one outcome hits N times in a row")
    @app_commands.describe(
        amount="Amount to wager",
        game="The outcome to streak",
        count="Number of consecutive hits required (2–10)",
    )
    async def streak(
        self,
        interaction: discord.Interaction,
        amount: int,
        game: str,
        count: int,
    ):
        from cogs.utils import acquire_game_lock, release_game_lock

        if not await acquire_game_lock(interaction.user.id, interaction):
            return

        try:
            await interaction.response.defer()

            if not 2 <= count <= 10:
                await interaction.followup.send(
                    "❌  Streak count must be between 2 and 10.", ephemeral=True
                )
                return

            leg = _LEGS.get(game)
            if leg is None:
                await interaction.followup.send(
                    "❌  Invalid game choice — please use the autocomplete options.", ephemeral=True
                )
                return

            if not await process_bet(interaction, amount):
                return

            compound_mult = round((leg["mult"] ** count) * 1.10, 2)
            potential_win = int(amount * compound_mult)

            def build_embed(hits: int, busted: bool = False) -> discord.Embed:
                bar = "✅ " * hits + ("❌" if busted else "⬜ " * (count - hits))
                color = Color.LOSS if busted else (Color.WIN if hits == count else Color.PLAYING)
                embed = discord.Embed(title="🔥 Streak Parlay", color=color)
                embed.set_author(
                    name=interaction.user.display_name,
                    icon_url=interaction.user.display_avatar.url,
                )
                embed.description = (
                    f"**Target:** {leg['name']}  ×{count}\n"
                    f"**Wager:** `${amount:,}`   **Potential:** `${potential_win:,}` (`{compound_mult}x` · 10 % bonus)\n\n"
                    f"**Progress:** {hits}/{count}\n{bar}"
                )
                return embed

            await interaction.edit_original_response(embed=build_embed(0))

            # ── Roll streak ──────────────────────────────────────────────────
            for i in range(count):
                await asyncio.sleep(1.0)
                won = random.random() < leg["chance"]

                if not won:
                    embed = build_embed(i, busted=True)
                    embed.description += f"\n\n💥 **Streak broken on roll {i+1}!**\n💸 **Loss:** -${amount:,}"
                    view = PlayAgainView(self.streak.callback, self, interaction, amount, game, count)
                    await interaction.edit_original_response(embed=embed, view=view)
                    await log_event(self.bot, f"{interaction.user.name} LOST ${amount} in Streak Parlay (broke at {i+1}/{count})")
                    await record_game(interaction.user.id, amount, -amount, False)
                    return

                await interaction.edit_original_response(embed=build_embed(i + 1))

            # ── Streak complete ──────────────────────────────────────────────
            profit = potential_win - amount
            await update_balance(interaction.user.id, potential_win)

            embed = build_embed(count)
            embed.description += f"\n\n🎉 **Streak complete!**\n💰 **Profit:** +${profit:,}"
            view = PlayAgainView(self.streak.callback, self, interaction, amount, game, count)
            await interaction.edit_original_response(embed=embed, view=view)
            await log_event(self.bot, f"{interaction.user.name} WON ${profit} in Streak Parlay ({compound_mult}x, {count}×{leg['name']})")
            await record_game(interaction.user.id, amount, profit, True)

        finally:
            release_game_lock(interaction.user.id)

    @streak.autocomplete("game")
    async def streak_autocomplete(self, interaction: discord.Interaction, current: str):
        return [c for c in _CHOICES if current.lower() in c.name.lower()][:25]


async def setup(bot):
    await bot.add_cog(ParlayCog(bot))