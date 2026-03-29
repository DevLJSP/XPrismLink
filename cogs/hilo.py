import discord
from discord import app_commands
from discord.ext import commands
import random
from database import get_balance, update_balance, record_game
from cogs.linker import is_linked
from logger import log_event
from cogs.utils_view import PlayAgainView

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = {
    "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
    "8": 8, "9": 9, "10": 10, "J": 11, "Q": 12, "K": 13, "A": 14
}

class HiloGame:
    def __init__(self, bot, user_id, user_name, bet, display_name, display_avatar_url):
        self.bot = bot
        self.user_id = user_id
        self.user_name = user_name
        self.bet = bet
        self.display_name = display_name
        self.display_avatar_url = display_avatar_url
        self.current_mult = 1.0
        self.deck = [(r, s, RANKS[r]) for r in RANKS.keys() for s in SUITS] * 2
        random.shuffle(self.deck)
        self.current_card = self.deck.pop()

    def get_card_str(self, card):
        return f"{card[0]}{card[1]}"

class HiloView(discord.ui.View):
    def __init__(self, game: HiloGame):
        super().__init__(timeout=60)
        self.game = game

    async def on_timeout(self):
        from cogs.utils import release_game_lock
        release_game_lock(self.game.user_id)
        for child in self.children:
            child.disabled = True

    def build_embed(self, status="playing", previous_card=None):
        embed = discord.Embed(title="🃏 Higher or Lower", color=discord.Color.blue())
        embed.set_author(name=f"{self.game.display_name} is playing", icon_url=self.game.display_avatar_url)
        
        card_str = self.game.get_card_str(self.game.current_card)
        winnings = int(self.game.bet * self.game.current_mult)
        
        if status == "playing":
            embed.description = (
                f">>> **Current Card:** `{card_str}`\n\n"
                f"Will the next card be higher or lower?\n\n"
                f"💰 **Current Pot:** ${winnings} (`{self.game.current_mult:.2f}x`)"
            )
        elif status == "won_round":
            embed.color = discord.Color.green()
            prev_str = self.game.get_card_str(previous_card)
            embed.description = (
                f">>> **Card Pulled:** `{card_str}`\n"
                f"*( {prev_str} ➡️ {card_str} )*\n\n"
                f"**Result:** Correct!\n\n"
                f"💰 **Current Pot:** ${winnings} (`{self.game.current_mult:.2f}x`)"
            )
        elif status == "lost":
            embed.color = discord.Color.red()
            prev_str = self.game.get_card_str(previous_card)
            embed.description = (
                f">>> **Card Pulled:** `{card_str}`\n"
                f"*( {prev_str} ➡️ {card_str} )*\n\n"
                f"**Result:** Incorrect / Tie.\n\n"
                f"💸 **Loss:** -${self.game.bet}"
            )
        elif status == "cashed_out":
            embed.color = discord.Color.gold()
            embed.description = (
                f">>> **Secured at:** `{card_str}`\n\n"
                f"You successfully cashed out your winnings!\n\n"
                f"💰 **Profit:** +${winnings - self.game.bet} (`{self.game.current_mult:.2f}x`)"
            )

        return embed

    async def process_guess(self, interaction: discord.Interaction, guess: str):
        if getattr(self, '_processing', False): return
        self._processing = True
        
        if interaction.user.id != self.game.user_id:
            self._processing = False
            await interaction.response.send_message("Not your game!", ephemeral=True)
            return

        await interaction.response.defer()

        previous_card = self.game.current_card
        next_card = self.game.deck.pop()
        self.game.current_card = next_card
        
        prev_val = previous_card[2]
        next_val = next_card[2]
        
        correct = False
        if guess == "higher" and next_val > prev_val:
            correct = True
        elif guess == "lower" and next_val < prev_val:
            correct = True
            
        if correct:
            self.game.current_mult *= 1.4
            embed = self.build_embed(status="won_round", previous_card=previous_card)
            try:
                await interaction.edit_original_response(embed=embed, view=self)
            except discord.NotFound:
                pass
        else:
            embed = self.build_embed(status="lost", previous_card=previous_card)
            for child in self.children:
                child.disabled = True
                
            cog = self.game.bot.get_cog("HiloCog")
            pa_view = PlayAgainView(cog.hilo.callback, cog, interaction, self.game.bet) if cog else self
            
            try:
                await interaction.edit_original_response(embed=embed, view=pa_view)
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
        await self.process_guess(interaction, "higher")

    @discord.ui.button(label="Lower", style=discord.ButtonStyle.danger, emoji="⬇️")
    async def lower(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_guess(interaction, "lower")

    @discord.ui.button(label="Cash Out", style=discord.ButtonStyle.success, emoji="💰")
    async def cashout(self, interaction: discord.Interaction, button: discord.ui.Button):
        if getattr(self, '_processing', False): return
        self._processing = True
        
        if interaction.user.id != self.game.user_id:
            self._processing = False
            await interaction.response.send_message("Not your game!", ephemeral=True)
            return
            
        await interaction.response.defer()
            
        winnings = int(self.game.bet * self.game.current_mult)
        await update_balance(self.game.user_id, winnings)
        profit = winnings - self.game.bet
        
        embed = self.build_embed(status="cashed_out")
        for child in self.children:
            child.disabled = True
            
        cog = self.game.bot.get_cog("HiloCog")
        pa_view = PlayAgainView(cog.hilo.callback, cog, interaction, self.game.bet) if cog else self
            
        try:
            await interaction.edit_original_response(embed=embed, view=pa_view)
        except discord.NotFound:
            pass
        self.stop()
        from cogs.utils import release_game_lock
        release_game_lock(self.game.user_id)
        await log_event(self.game.bot, f"{self.game.user_name} WON ${profit} in HiLo (x{self.game.current_mult:.2f})")
        await record_game(self.game.user_id, self.game.bet, profit, True)
        self._processing = False

class HiloCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="hilo", description="Play Higher or Lower")
    @app_commands.describe(amount="Amount to bet")
    async def hilo(self, interaction: discord.Interaction, amount: int):
        from cogs.utils import acquire_game_lock
        if not await acquire_game_lock(interaction.user.id, interaction):
            return

        from database import process_bet
        await interaction.response.defer()
        if not await process_bet(interaction, amount):
            from cogs.utils import release_game_lock
            release_game_lock(interaction.user.id)
            return
        
        game = HiloGame(self.bot, interaction.user.id, interaction.user.name, amount, interaction.user.display_name, interaction.user.display_avatar.url)
        view = HiloView(game)
        embed = view.build_embed(status="playing")
        
        await interaction.edit_original_response(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(HiloCog(bot))
