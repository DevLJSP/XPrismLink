import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from database import get_balance, update_balance, record_game, deduct_balance_if_sufficient
from cogs.linker import is_linked
from logger import log_event
from cogs.utils_view import PlayAgainView

SUITS = ["♠", "♥", "♦", "♣"]
RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]

def get_card_value(card):
    rank = card[0]
    if rank in ["J", "Q", "K"]: return 10
    if rank == "A": return 11
    if rank == "1": return 10 # 10 is '10', so index 0 is '1'
    return int(rank)

def calc_hand(hand):
    val = sum(get_card_value(c) for c in hand)
    aces = sum(1 for c in hand if c[0] == "A")
    while val > 21 and aces > 0:
        val -= 10
        aces -= 1
    return val

class BlackjackView(discord.ui.View):
    def __init__(self, game):
        super().__init__(timeout=60)
        self.game = game

    async def on_timeout(self):
        from cogs.utils import release_game_lock
        release_game_lock(self.game.user_id)
        for child in self.children:
            child.disabled = True
        try:
            await self.game.interaction.edit_original_response(view=self)
        except Exception:
            pass

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if getattr(self, '_processing', False): return
        self._processing = True
        
        if interaction.user.id != self.game.user_id:
            self._processing = False
            await interaction.response.send_message("Not your game!", ephemeral=True)
            return
            
        await interaction.response.defer()
        self.game.player_hand.append(self.game.deck.pop())
        pval = calc_hand(self.game.player_hand)
        
        if pval > 21:
            await self.game.end_game(interaction, "bust")
        else:
            embed = self.game.build_embed()
            try:
                await interaction.edit_original_response(embed=embed, view=self)
            except discord.NotFound:
                pass
        self._processing = False

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if getattr(self, '_processing', False): return
        self._processing = True
        
        if interaction.user.id != self.game.user_id:
            self._processing = False
            await interaction.response.send_message("Not your game!", ephemeral=True)
            return
            
        await interaction.response.defer()
        await self.game.dealer_play(interaction)
        self._processing = False

    @discord.ui.button(label="Double", style=discord.ButtonStyle.danger)
    async def double(self, interaction: discord.Interaction, button: discord.ui.Button):
        if getattr(self, '_processing', False): return
        self._processing = True
        
        if interaction.user.id != self.game.user_id:
            self._processing = False
            await interaction.response.send_message("Not your game!", ephemeral=True)
            return
            
        if len(self.game.player_hand) > 2:
            self._processing = False
            await interaction.response.send_message("Can only double down on first two cards!", ephemeral=True)
            return
            
        await interaction.response.defer()
        if not await deduct_balance_if_sufficient(self.game.user_id, self.game.bet):
            self._processing = False
            await interaction.followup.send("Not enough money to double!", ephemeral=True)
            return
            
        self.game.bet *= 2
        
        self.game.player_hand.append(self.game.deck.pop())
        pval = calc_hand(self.game.player_hand)
        
        if pval > 21:
            await self.game.end_game(interaction, "bust")
        else:
            await self.game.dealer_play(interaction)
        self._processing = False

class BlackjackGame:
    def __init__(self, interaction, bet, bot):
        self.interaction = interaction
        self.user_id = interaction.user.id
        self.user_name = interaction.user.name
        self.bet = bet
        self.bot = bot
        self.deck = [f"{r}{s}" for r in RANKS for s in SUITS] * 4 # 4 decks
        random.shuffle(self.deck)
        
        self.player_hand = [self.deck.pop(), self.deck.pop()]
        self.dealer_hand = [self.deck.pop(), self.deck.pop()]
        
        self.status = "playing" # playing, won, lost, push, bust

    def build_embed(self, hide_dealer=True):
        embed = discord.Embed(title="🃏 Blackjack", color=discord.Color.blurple())
        embed.set_author(name=f"{self.interaction.user.display_name} is playing", icon_url=self.interaction.user.display_avatar.url)
        
        pval = calc_hand(self.player_hand)
        p_str = " ".join([f"`{c}`" for c in self.player_hand])
        
        if hide_dealer:
            dval = get_card_value(self.dealer_hand[0])
            d_str = f"`{self.dealer_hand[0]}` `🎴`"
        else:
            dval = calc_hand(self.dealer_hand)
            d_str = " ".join([f"`{c}`" for c in self.dealer_hand])
            
        embed.description = (
            f">>> **Dealer Hand:** {dval}\n"
            f"{d_str}\n\n"
            f"**Your Hand:** {pval}\n"
            f"{p_str}\n\n"
            f"💰 **Bet:** ${self.bet}"
        )
        return embed

    async def dealer_play(self, interaction):
        self.status = "dealer_turn"
        # Edit view to none while dealer plays
        try:
            await interaction.edit_original_response(embed=self.build_embed(hide_dealer=False), view=None)
        except discord.NotFound:
            pass
        
        dval = calc_hand(self.dealer_hand)
        while dval < 17:
            await asyncio.sleep(1.2)
            self.dealer_hand.append(self.deck.pop())
            dval = calc_hand(self.dealer_hand)
            try:
                await interaction.edit_original_response(embed=self.build_embed(hide_dealer=False))
            except:
                pass
                
        pval = calc_hand(self.player_hand)
        
        if dval > 21:
            await self.end_game(interaction, "dealer_bust")
        elif dval > pval:
            await self.end_game(interaction, "lost")
        elif dval < pval:
            await self.end_game(interaction, "won")
        else:
            await self.end_game(interaction, "push")

    async def end_game(self, interaction, result):
        embed = self.build_embed(hide_dealer=False)
        winnings = 0
        
        if result == "bust":
            embed.color = discord.Color.red()
            embed.title = "🃏 Blackjack - BUST!"
            embed.add_field(name="Result", value=f"You Busted! Lost ${self.bet}")
            await log_event(self.bot, f"{self.user_name} LOST ${self.bet} in Blackjack (Bust)")
            await record_game(self.user_id, self.bet, -self.bet, False)
        elif result == "dealer_bust":
            embed.color = discord.Color.green()
            embed.title = "🃏 Blackjack - WON!"
            winnings = self.bet * 2
            embed.add_field(name="Result", value=f"Dealer Busted! Won ${winnings - self.bet}")
            await log_event(self.bot, f"{self.user_name} WON ${winnings - self.bet} in Blackjack (Dealer Bust)")
            await record_game(self.user_id, self.bet, winnings - self.bet, True)
        elif result == "won":
            embed.color = discord.Color.green()
            embed.title = "🃏 Blackjack - WON!"
            winnings = self.bet * 2
            embed.add_field(name="Result", value=f"You Won ${winnings - self.bet}")
            await log_event(self.bot, f"{self.user_name} WON ${winnings - self.bet} in Blackjack")
            await record_game(self.user_id, self.bet, winnings - self.bet, True)
        elif result == "lost":
            embed.color = discord.Color.dark_red()
            embed.title = "🃏 Blackjack - LOST"
            embed.add_field(name="Result", value=f"Dealer Wins. Lost ${self.bet}")
            await log_event(self.bot, f"{self.user_name} LOST ${self.bet} in Blackjack")
            await record_game(self.user_id, self.bet, -self.bet, False)
        elif result == "push":
            embed.color = discord.Color.light_grey()
            embed.title = "🃏 Blackjack - PUSH"
            winnings = self.bet
            embed.add_field(name="Result", value=f"It's a Tie! Bet returned.")

        if winnings > 0:
            await update_balance(self.user_id, winnings)
            
        cog = self.bot.get_cog("BlackjackCog")
        view = PlayAgainView(cog.blackjack.callback, cog, self.interaction, self.bet) if cog else None
            
        from cogs.utils import release_game_lock
        release_game_lock(self.user_id)
        
        try:
            await interaction.edit_original_response(embed=embed, view=view)
        except discord.NotFound:
            pass
            
class BlackjackCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="blackjack", description="Play a hand of Vegas Rules Blackjack")
    @app_commands.describe(amount="Amount to bet")
    async def blackjack(self, interaction: discord.Interaction, amount: int):
        from cogs.utils import acquire_game_lock
        if not await acquire_game_lock(interaction.user.id, interaction):
            return

        from database import process_bet
        await interaction.response.defer()
        if not await process_bet(interaction, amount):
            from cogs.utils import release_game_lock
            release_game_lock(interaction.user.id)
            return

        game = BlackjackGame(interaction, amount, self.bot)
        
        pval = calc_hand(game.player_hand)
        dval = calc_hand(game.dealer_hand)
        
        # Check Natural Blackjacks
        if pval == 21 and dval != 21:
            winnings = int(amount * 2.5) # 3:2 payout (original bet + 1.5x)
            await update_balance(interaction.user.id, winnings)
            embed = game.build_embed(hide_dealer=False)
            embed.color = discord.Color.gold()
            embed.title = "🃏 Blackjack - NATURAL 21!"
            embed.add_field(name="Result", value=f"Blackjack pays 3:2! Won ${winnings - amount}")
            
            cog = self.bot.get_cog("BlackjackCog")
            view = PlayAgainView(cog.blackjack.callback, cog, interaction, amount) if cog else None
            
            from cogs.utils import release_game_lock
            release_game_lock(interaction.user.id)
            
            await interaction.edit_original_response(embed=embed, view=view)
            await log_event(self.bot, f"{interaction.user.name} WON ${winnings - amount} in Blackjack (Natural)")
            await record_game(interaction.user.id, amount, winnings - amount, True)
            return
        elif pval == 21 and dval == 21:
            await update_balance(interaction.user.id, amount)
            embed = game.build_embed(hide_dealer=False)
            embed.title = "🃏 Blackjack - PUSH"
            embed.add_field(name="Result", value="Double Blackjack! Ties tie.")
            
            cog = self.bot.get_cog("BlackjackCog")
            view = PlayAgainView(cog.blackjack.callback, cog, interaction, amount) if cog else None
            
            from cogs.utils import release_game_lock
            release_game_lock(interaction.user.id)
            
            await interaction.edit_original_response(embed=embed, view=view)
            return
            
        view = BlackjackView(game)
        embed = game.build_embed()
        await interaction.edit_original_response(embed=embed, view=view)

async def setup(bot):
    await bot.add_cog(BlackjackCog(bot))
