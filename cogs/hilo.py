import discord
from discord import app_commands
from discord.ext import commands
import random
from database import update_balance, record_game
from logger import log_event
from cogs.utils_view import PlayAgainView
from cogs.theme import Color

SUITS = ["♠", "♥", "♦", "♣"]
RANK_VALUES: dict[str, int] = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
    "8": 8, "9": 9, "10": 10, "J": 11, "Q": 12, "K": 13, "A": 14,
}

# Each correct guess now multiplies pot by 1.18 instead of 1.4
STEP_MULT = 1.18


class HiloGame:
    def __init__(self, bot, user_id, user_name, bet, interaction):
        self.bot         = bot
        self.user_id     = user_id
        self.user_name   = user_name
        self.bet         = bet
        self.interaction = interaction
        self.mult        = 1.0
        self.deck        = [(r, s, v) for r, v in RANK_VALUES.items() for s in SUITS] * 2
        random.shuffle(self.deck)
        self.current     = self.deck.pop()

    def card_str(self, card) -> str:
        return f"{card[0]}{card[1]}"


class HiloView(discord.ui.View):
    def __init__(self, game: HiloGame):
        super().__init__(timeout=60)
        self.game        = game
        self._processing = False

    async def on_timeout(self):
        from cogs.utils import release_game_lock
        release_game_lock(self.game.user_id)
        for child in self.children:
            child.disabled = True

    def _playing_embed(self):
        pot   = int(self.game.bet * self.game.mult)
        embed = discord.Embed(title="🃏  Higher or Lower", color=Color.PLAYING)
        embed.set_author(name=self.game.interaction.user.display_name, icon_url=self.game.interaction.user.display_avatar.url)
        embed.description = (
            f"**Current card:** `{self.game.card_str(self.game.current)}`\n\n"
            f"Will the next card be **higher** or **lower**?\n\n"
            f"💰  **Pot:** ${pot:,}  (`{self.game.mult:.2f}x`)"
        )
        return embed

    def _result_embed(self, prev, nxt, correct: bool):
        pot = int(self.game.bet * self.game.mult)
        if correct:
            embed = discord.Embed(title="🃏  Higher or Lower — Correct!", color=Color.WIN)
            body  = (
                f"`{self.game.card_str(prev)}` ➜ `{self.game.card_str(nxt)}`\n\n"
                f"💰  **Pot:** ${pot:,}  (`{self.game.mult:.2f}x`)"
            )
        else:
            embed = discord.Embed(title="🃏  Higher or Lower — Wrong!", color=Color.LOSS)
            body  = (
                f"`{self.game.card_str(prev)}` ➜ `{self.game.card_str(nxt)}`\n\n"
                f"💸  **Loss:** -${self.game.bet:,}"
            )
        embed.set_author(name=self.game.interaction.user.display_name, icon_url=self.game.interaction.user.display_avatar.url)
        embed.description = body
        return embed

    def _cashout_embed(self):
        pot    = int(self.game.bet * self.game.mult)
        profit = pot - self.game.bet
        embed  = discord.Embed(title="🃏  Higher or Lower — Cashed Out!", color=Color.CASHOUT)
        embed.set_author(name=self.game.interaction.user.display_name, icon_url=self.game.interaction.user.display_avatar.url)
        embed.description = (
            f"Secured at `{self.game.card_str(self.game.current)}`  (`{self.game.mult:.2f}x`)\n\n"
            f"💰  **Profit:** +${profit:,}"
        )
        return embed

    async def _process_guess(self, interaction: discord.Interaction, direction: str):
        if self._processing:
            return
        if interaction.user.id != self.game.user_id:
            await interaction.response.send_message("This isn't your game.", ephemeral=True)
            return
        self._processing = True
        await interaction.response.defer()

        prev  = self.game.current
        nxt   = self.game.deck.pop()
        self.game.current = nxt

        correct = (
            (direction == "higher" and nxt[2] > prev[2]) or
            (direction == "lower"  and nxt[2] < prev[2])
        )

        if correct:
            self.game.mult = round(self.game.mult * STEP_MULT, 3)
            try:
                await interaction.edit_original_response(embed=self._result_embed(prev, nxt, True), view=self)
            except discord.NotFound:
                pass
        else:
            cog     = self.game.bot.get_cog("HiloCog")
            pa_view = PlayAgainView(cog.hilo.callback, cog, interaction, self.game.bet) if cog else self
            try:
                await interaction.edit_original_response(embed=self._result_embed(prev, nxt, False), view=pa_view)
            except discord.NotFound:
                pass
            self.stop()
            from cogs.utils import release_game_lock
            release_game_lock(self.game.user_id)
            await log_event(self.game.bot, f"{self.game.user_name} LOST ${self.game.bet} in HiLo")
            await record_game(self.game.user_id, self.game.bet, -self.game.bet, False)

        self._processing = False

    @discord.ui.button(label="Higher", style=discord.ButtonStyle.primary, emoji="⬆️")
    async def higher(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._process_guess(interaction, "higher")

    @discord.ui.button(label="Lower", style=discord.ButtonStyle.danger, emoji="⬇️")
    async def lower(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._process_guess(interaction, "lower")

    @discord.ui.button(label="Cash Out", style=discord.ButtonStyle.success, emoji="💰")
    async def cashout(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._processing:
            return
        if interaction.user.id != self.game.user_id:
            await interaction.response.send_message("This isn't your game.", ephemeral=True)
            return
        self._processing = True
        await interaction.response.defer()

        winnings = int(self.game.bet * self.game.mult)
        profit   = winnings - self.game.bet
        await update_balance(self.game.user_id, winnings)

        cog     = self.game.bot.get_cog("HiloCog")
        pa_view = PlayAgainView(cog.hilo.callback, cog, interaction, self.game.bet) if cog else self
        try:
            await interaction.edit_original_response(embed=self._cashout_embed(), view=pa_view)
        except discord.NotFound:
            pass
        self.stop()
        from cogs.utils import release_game_lock
        release_game_lock(self.game.user_id)
        await log_event(self.game.bot, f"{self.game.user_name} WON ${profit} in HiLo ({self.game.mult:.2f}x)")
        await record_game(self.game.user_id, self.game.bet, profit, True)
        self._processing = False


class HiloCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="hilo", description="Play Higher or Lower — cash out before you guess wrong")
    @app_commands.describe(amount="Amount to bet")
    async def hilo(self, interaction: discord.Interaction, amount: int):
        from cogs.utils import acquire_game_lock, release_game_lock
        if not await acquire_game_lock(interaction.user.id, interaction):
            return
        await interaction.response.defer()
        from database import process_bet
        if not await process_bet(interaction, amount):
            release_game_lock(interaction.user.id)
            return
        game = HiloGame(self.bot, interaction.user.id, interaction.user.name, amount, interaction)
        view = HiloView(game)
        await interaction.edit_original_response(embed=view._playing_embed(), view=view)


async def setup(bot):
    await bot.add_cog(HiloCog(bot))