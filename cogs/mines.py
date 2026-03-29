import discord
from discord import app_commands
from discord.ext import commands
import random
from database import get_balance, update_balance
from logger import log_event

# --- CONFIG ---
GRID_SIZE = 6
NUM_BOMBS = 8 

class MinesweeperGame:
    def __init__(self, user_id):
        self.user_id = user_id
        self.grid = [[0 for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        self.visible = [[False for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        self.flagged = [[False for _ in range(GRID_SIZE)] for _ in range(GRID_SIZE)]
        self.bombs = []
        
        # Economy State
        self.total_invested = 0      
        self.current_value = 0.0     
        self.last_bet = 0            
        self.correct_flags = 0
        
        self._generate_grid()
        self._reveal_starting_tiles()

    def _generate_grid(self):
        count = 0
        while count < NUM_BOMBS:
            r, c = random.randint(0, GRID_SIZE-1), random.randint(0, GRID_SIZE-1)
            if self.grid[r][c] != 9: 
                self.grid[r][c] = 9
                self.bombs.append((r, c))
                count += 1
        
        for r in range(GRID_SIZE):
            for c in range(GRID_SIZE):
                if self.grid[r][c] == 9: continue
                bombs_near = 0
                for i in range(-1, 2):
                    for j in range(-1, 2):
                        nr, nc = r + i, c + j
                        if 0 <= nr < GRID_SIZE and 0 <= nc < GRID_SIZE:
                            if self.grid[nr][nc] == 9:
                                bombs_near += 1
                self.grid[r][c] = bombs_near

    def _reveal_starting_tiles(self):
        revealed = 0
        while revealed < 3:
            r, c = random.randint(0, GRID_SIZE-1), random.randint(0, GRID_SIZE-1)
            if self.grid[r][c] != 9 and not self.visible[r][c]:
                self.visible[r][c] = True
                revealed += 1

    def get_board_view(self, reveal_all=False, debug=False):
        number_row_emojis = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣"] 
        cell_numbers = ["0️⃣", "1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]
        
        rows = []
        rows.append("💣⬛🇦 🇧 🇨 🇩 🇪 🇫⬛")
        rows.append("⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛")

        for r in range(GRID_SIZE):
            line = f"{number_row_emojis[r+1]}⬛"
            for c in range(GRID_SIZE):
                is_bomb = self.grid[r][c] == 9
                cell_icon = "🟦"
                
                if reveal_all:
                    if is_bomb: cell_icon = "💣"
                    else: cell_icon = cell_numbers[self.grid[r][c]]
                elif self.flagged[r][c]:
                    cell_icon = "🚩"
                elif self.visible[r][c]:
                    if is_bomb: cell_icon = "💣"
                    else: cell_icon = cell_numbers[self.grid[r][c]]
                elif debug and is_bomb:
                    cell_icon = "🧨" 
                
                # Removed the space here so tiles touch
                line += f"{cell_icon}" 
            
            # Removed the space before the border
            line += "⬛"
            rows.append(line)
        
        rows.append("⬛⬛⬛⬛⬛⬛⬛⬛⬛⬛")
        return "\n".join(rows)

active_games = {}

class Minesweeper(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.debug_mode = False 

    def coord_parser(self, coord_str):
        try:
            coord_str = coord_str.upper().strip()
            if len(coord_str) < 2: return None
            col_char, row_char = coord_str[0], coord_str[1]
            col_map = {'A':0, 'B':1, 'C':2, 'D':3, 'E':4, 'F':5}
            
            if col_char not in col_map or not row_char.isdigit(): return None
            r, c = int(row_char) - 1, col_map[col_char]
            
            if 0 <= r < GRID_SIZE and 0 <= c < GRID_SIZE: return (r, c)
            return None
        except: return None

    @app_commands.command(name="mines", description="Play high-stakes Minesweeper")
    @app_commands.describe(
        action="Choose an action",
        coord="Coordinate (A1, B2)",
        amount="Money to invest"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="New Game", value="start"),
        app_commands.Choice(name="Reveal", value="reveal"),
        app_commands.Choice(name="Flag", value="flag"),
        app_commands.Choice(name="Cashout", value="cashout"),
        app_commands.Choice(name="View Board", value="view")
    ])
    async def mines(self, interaction: discord.Interaction, action: app_commands.Choice[str], coord: str = None, amount: int = None):
        user_id = interaction.user.id
        from cogs.linker import is_linked
        if not is_linked(user_id):
            await interaction.response.send_message("❌ | You must link your Rugplay account first! Use `/link`.", ephemeral=True)
            return

        act = action.value
        
        # --- START ---
        if act == "start":
            if user_id in active_games:
                await interaction.response.send_message("❌ | Game running! Use **Cashout**.", ephemeral=True)
                return

            from cogs.utils import acquire_game_lock
            if not await acquire_game_lock(user_id, interaction):
                return

            game = MinesweeperGame(user_id)
            active_games[user_id] = game
            
            embed = discord.Embed(title="💣 Gambling Minesweeper (6x6)", color=discord.Color.blue())
            embed.set_author(name=f"{interaction.user.display_name} is playing", icon_url=interaction.user.display_avatar.url)
            embed.description = (
                f"{game.get_board_view(debug=self.debug_mode)}\n\n"
                "**Rules:**\n"
                "1. **Reveal:** Adds money (Must bet higher than last).\n"
                "2. **Flag:** Multiplies current pot by **1.5x**.\n"
                "3. **Cashout:** Take the money and run."
            )
            await interaction.response.send_message(embed=embed)
            return

        # --- CHECK GAME ---
        if user_id not in active_games:
            await interaction.response.send_message("❌ | No active game! Use **New Game**.", ephemeral=True)
            return
        
        game = active_games[user_id]

        # --- CASHOUT ---
        if act == "cashout":
            winnings = int(game.current_value)
            
            payout = winnings
            
            if payout > 0:
                await update_balance(user_id, payout)
            
            del active_games[user_id]
            from cogs.utils import release_game_lock
            release_game_lock(user_id)
            
            embed = discord.Embed(title="💰 Cashed Out!", color=discord.Color.green())
            embed.description = (
                f"**Total Invested:** ${game.total_invested}\n"
                f"**Pot Value:** ${winnings}\n"
                f"**Profit:** ${payout - game.total_invested}\n\n"
                f"Funds added to wallet."
            )
            await interaction.response.send_message(embed=embed)
            await log_event(self.bot, f"{interaction.user.name} cashed out Minesweeper for ${payout} (Profit: ${payout - game.total_invested})")
            return

        # --- VIEW ---
        if act == "view":
            embed = discord.Embed(title="💣 Current Board", color=discord.Color.blue())
            current_val = int(game.current_value)
            embed.description = (
                f"{game.get_board_view(debug=self.debug_mode)}\n\n"
                f"💰 **Invested:** ${game.total_invested}\n"
                f"💵 **Current Value:** ${current_val}\n"
                f"🔼 **Next Bet Min:** ${game.last_bet}"
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # --- COORD CHECK ---
        if not coord:
            await interaction.response.send_message("❌ | Missing Coordinate (e.g. A1).", ephemeral=True)
            return

        xy = self.coord_parser(coord)
        if not xy:
            await interaction.response.send_message("❌ | Invalid Coordinate.", ephemeral=True)
            return
        
        r, c = xy
        if game.visible[r][c] or game.flagged[r][c]:
            await interaction.response.send_message("❌ | Already processed.", ephemeral=True)
            return

        # --- FLAG ---
        if act == "flag":
            if game.grid[r][c] == 9:
                game.flagged[r][c] = True
                game.correct_flags += 1
                game.current_value = game.current_value * 1.35
                
                embed = discord.Embed(title="🚩 Bomb Defused!", color=discord.Color.gold())
                embed.description = (
                    f"{game.get_board_view(debug=self.debug_mode)}\n\n"
                    f"**Success!** Pot x1.35!\n"
                    f"**New Value:** ${int(game.current_value)}"
                )
                await interaction.response.send_message(embed=embed)
            else:
                del active_games[user_id]
                from cogs.utils import release_game_lock
                release_game_lock(user_id)
                
                embed = discord.Embed(title="❌ WRONG!", color=discord.Color.dark_red())
                embed.description = (
                    f"{game.get_board_view(reveal_all=True)}\n\n"
                    f"That was safe.\n**Lost:** ${game.total_invested}"
                )
                await interaction.response.send_message(embed=embed)
                await log_event(self.bot, f"{interaction.user.name} LOST ${game.total_invested} in Minesweeper (False Flag).")
            return

        # --- REVEAL ---
        if act == "reveal":
            if amount is None:
                await interaction.response.send_message("❌ | Invalid Amount.", ephemeral=True)
                return
            
            if amount < game.last_bet:
                await interaction.response.send_message(f"❌ | Progressive Betting: Must bet **${game.last_bet}** or higher.", ephemeral=True)
                return
            
            from database import process_bet
            if not await process_bet(interaction, amount):
                return
            game.total_invested += amount
            game.last_bet = amount
            
            if game.grid[r][c] == 9:
                del active_games[user_id]
                from cogs.utils import release_game_lock
                release_game_lock(user_id)
                
                embed = discord.Embed(title="💥 BOOM!", color=discord.Color.red())
                embed.description = f"{game.get_board_view(reveal_all=True)}\n\nYou died.\n**Lost:** ${game.total_invested}"
                await interaction.response.send_message(embed=embed)
                await log_event(self.bot, f"{interaction.user.name} LOST ${game.total_invested} in Minesweeper (Boom).")
            else:
                game.visible[r][c] = True
                game.current_value += amount
                
                embed = discord.Embed(title="Safe!", color=discord.Color.green())
                embed.description = (
                    f"{game.get_board_view(debug=self.debug_mode)}\n\n"
                    f"💰 **Added:** ${amount}\n"
                    f"💵 **Current Value:** ${int(game.current_value)}\n"
                    f"🔼 **Next Bet Min:** ${game.last_bet}"
                )
                await interaction.response.send_message(embed=embed)

async def setup(bot):
    # await bot.add_cog(Minesweeper(bot))
    pass