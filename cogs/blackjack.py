import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from database import update_balance, record_game, deduct_balance_if_sufficient
from logger import log_event
from cogs.utils_view import PlayAgainView
from cogs.theme import Color

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]


def card_value(card: str) -> int:
    rank = card[:-1]
    if rank in ("J", "Q", "K", "10"):
        return 10
    if rank == "A":
        return 11
    return int(rank)


def hand_total(hand: list[str]) -> int:
    total = sum(card_value(c) for c in hand)
    aces  = sum(1 for c in hand if c[:-1] == "A")
    while total > 21 and aces:
        total -= 10
        aces  -= 1
    return total


def fmt_hand(hand: list[str]) -> str:
    return "  ".join(f"`{c}`" for c in hand)


def is_soft_17(hand: list[str]) -> bool:
    """True if dealer has a soft 17 (Ace counted as 11 in a total of 17)."""
    total = sum(card_value(c) for c in hand)
    aces  = sum(1 for c in hand if c[:-1] == "A")
    # Hard total is 17 with at least one ace being counted as 11
    return total == 17 and aces > 0 and (total - 10 * (aces - 1)) != 17


class BlackjackView(discord.ui.View):
    def __init__(self, game: "BlackjackGame"):
        super().__init__(timeout=60)
        self.game        = game
        self._processing = False

    async def on_timeout(self):
        from cogs.utils import release_game_lock
        release_game_lock(self.game.user_id)
        for child in self.children:
            child.disabled = True
        try:
            await self.game.interaction.edit_original_response(view=self)
        except Exception:
            pass

    def _check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.game.user_id

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, emoji="🃏")
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._processing: return
        if not self._check(interaction):
            await interaction.response.send_message("This isn't your game.", ephemeral=True); return
        self._processing = True
        await interaction.response.defer()
        self.game.player_hand.append(self.game.deck.pop())
        if hand_total(self.game.player_hand) > 21:
            await self.game.end_game(interaction, "bust")
        else:
            try:
                await interaction.edit_original_response(embed=self.game.build_embed(), view=self)
            except discord.NotFound:
                pass
        self._processing = False

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary, emoji="✋")
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._processing: return
        if not self._check(interaction):
            await interaction.response.send_message("This isn't your game.", ephemeral=True); return
        self._processing = True
        await interaction.response.defer()
        await self.game.dealer_play(interaction)
        self._processing = False

    @discord.ui.button(label="Double", style=discord.ButtonStyle.danger, emoji="💰")
    async def double(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self._processing: return
        if not self._check(interaction):
            await interaction.response.send_message("This isn't your game.", ephemeral=True); return
        if len(self.game.player_hand) > 2:
            await interaction.response.send_message("Double down only on your first two cards.", ephemeral=True); return
        self._processing = True
        await interaction.response.defer()
        if not await deduct_balance_if_sufficient(self.game.user_id, self.game.bet):
            await interaction.followup.send("Not enough balance to double.", ephemeral=True)
            self._processing = False; return
        self.game.bet *= 2
        self.game.player_hand.append(self.game.deck.pop())
        if hand_total(self.game.player_hand) > 21:
            await self.game.end_game(interaction, "bust")
        else:
            await self.game.dealer_play(interaction)
        self._processing = False


class BlackjackGame:
    def __init__(self, interaction, bet, bot):
        self.interaction  = interaction
        self.user_id      = interaction.user.id
        self.user_name    = interaction.user.name
        self.bet          = bet
        self.bot          = bot
        self.deck         = [f"{r}{s}" for r in RANKS for s in SUITS] * 4
        random.shuffle(self.deck)
        self.player_hand  = [self.deck.pop(), self.deck.pop()]
        self.dealer_hand  = [self.deck.pop(), self.deck.pop()]

    def build_embed(self, hide_dealer=True):
        embed = discord.Embed(title="🃏  Blackjack", color=Color.PLAYING)
        embed.set_author(name=self.interaction.user.display_name, icon_url=self.interaction.user.display_avatar.url)
        p_total = hand_total(self.player_hand)
        if hide_dealer:
            d_display = f"{self.dealer_hand[0][:-1]}?  `🎴`"
            d_total   = card_value(self.dealer_hand[0])
        else:
            d_display = fmt_hand(self.dealer_hand)
            d_total   = hand_total(self.dealer_hand)
        embed.description = (
            f"**Dealer** — {d_total}\n{d_display}\n\n"
            f"**You** — {p_total}\n{fmt_hand(self.player_hand)}\n\n"
            f"💰  **Bet:** ${self.bet:,}"
        )
        return embed

    async def dealer_play(self, interaction):
        try:
            await interaction.edit_original_response(embed=self.build_embed(hide_dealer=False), view=None)
        except discord.NotFound:
            pass
        # Dealer hits soft 17 (more aggressive for house)
        while hand_total(self.dealer_hand) < 17 or is_soft_17(self.dealer_hand):
            await asyncio.sleep(1.2)
            self.dealer_hand.append(self.deck.pop())
            try:
                await interaction.edit_original_response(embed=self.build_embed(hide_dealer=False))
            except Exception:
                pass
        p = hand_total(self.player_hand)
        d = hand_total(self.dealer_hand)
        if   d > 21: await self.end_game(interaction, "dealer_bust")
        elif d > p:  await self.end_game(interaction, "lost")
        elif d < p:  await self.end_game(interaction, "won")
        else:        await self.end_game(interaction, "push")

    async def end_game(self, interaction, result):
        embed    = self.build_embed(hide_dealer=False)
        winnings = 0

        if result == "bust":
            embed.color = Color.LOSS;    embed.title = "🃏  Blackjack — Bust"
            embed.add_field(name="Result", value=f"You busted.  💸 -${self.bet:,}")
            await log_event(self.bot, f"{self.user_name} LOST ${self.bet} in Blackjack (bust)")
            await record_game(self.user_id, self.bet, -self.bet, False)
        elif result == "dealer_bust":
            winnings = self.bet * 2
            embed.color = Color.WIN;     embed.title = "🃏  Blackjack — Won!"
            embed.add_field(name="Result", value=f"Dealer busted.  💰 +${winnings - self.bet:,}")
            await log_event(self.bot, f"{self.user_name} WON ${winnings - self.bet} in Blackjack (dealer bust)")
            await record_game(self.user_id, self.bet, winnings - self.bet, True)
        elif result == "won":
            winnings = self.bet * 2
            embed.color = Color.WIN;     embed.title = "🃏  Blackjack — Won!"
            embed.add_field(name="Result", value=f"You win!  💰 +${winnings - self.bet:,}")
            await log_event(self.bot, f"{self.user_name} WON ${winnings - self.bet} in Blackjack")
            await record_game(self.user_id, self.bet, winnings - self.bet, True)
        elif result == "lost":
            embed.color = Color.LOSS;    embed.title = "🃏  Blackjack — Lost"
            embed.add_field(name="Result", value=f"Dealer wins.  💸 -${self.bet:,}")
            await log_event(self.bot, f"{self.user_name} LOST ${self.bet} in Blackjack")
            await record_game(self.user_id, self.bet, -self.bet, False)
        elif result == "push":
            winnings = self.bet
            embed.color = Color.NEUTRAL; embed.title = "🃏  Blackjack — Push"
            embed.add_field(name="Result", value="Tie — bet returned.")

        if winnings:
            await update_balance(self.user_id, winnings)

        cog     = self.bot.get_cog("BlackjackCog")
        pa_view = PlayAgainView(cog.blackjack.callback, cog, self.interaction, self.bet) if cog else None
        from cogs.utils import release_game_lock
        release_game_lock(self.user_id)
        try:
            await interaction.edit_original_response(embed=embed, view=pa_view)
        except discord.NotFound:
            pass


class BlackjackCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="blackjack", description="Play a hand of Vegas-rules Blackjack")
    @app_commands.describe(amount="Amount to bet")
    async def blackjack(self, interaction: discord.Interaction, amount: int):
        from cogs.utils import acquire_game_lock, release_game_lock
        if not await acquire_game_lock(interaction.user.id, interaction):
            return
        await interaction.response.defer()
        from database import process_bet
        if not await process_bet(interaction, amount):
            release_game_lock(interaction.user.id); return

        game = BlackjackGame(interaction, amount, self.bot)
        p    = hand_total(game.player_hand)
        d    = hand_total(game.dealer_hand)
        cog  = self.bot.get_cog("BlackjackCog")

        # Natural: pays 1:1 instead of 3:2 (worse for player)
        if p == 21 and d != 21:
            winnings = amount * 2   # 1:1 payout
            await update_balance(interaction.user.id, winnings)
            embed = game.build_embed(hide_dealer=False)
            embed.color = Color.GOLD; embed.title = "🃏  Blackjack — Natural 21!"
            embed.add_field(name="Result", value=f"Blackjack! (pays 1:1)  💰 +${winnings - amount:,}")
            pa = PlayAgainView(cog.blackjack.callback, cog, interaction, amount) if cog else None
            release_game_lock(interaction.user.id)
            await interaction.edit_original_response(embed=embed, view=pa)
            await log_event(self.bot, f"{interaction.user.name} WON ${winnings - amount} in Blackjack (Natural 1:1)")
            await record_game(interaction.user.id, amount, winnings - amount, True)
            return

        if p == 21 and d == 21:
            await update_balance(interaction.user.id, amount)
            embed = game.build_embed(hide_dealer=False)
            embed.color = Color.NEUTRAL; embed.title = "🃏  Blackjack — Push"
            embed.add_field(name="Result", value="Double Blackjack — bet returned.")
            pa = PlayAgainView(cog.blackjack.callback, cog, interaction, amount) if cog else None
            release_game_lock(interaction.user.id)
            await interaction.edit_original_response(embed=embed, view=pa)
            return

        view = BlackjackView(game)
        await interaction.edit_original_response(embed=game.build_embed(), view=view)


async def setup(bot):
    await bot.add_cog(BlackjackCog(bot))