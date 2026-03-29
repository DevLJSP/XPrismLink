import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
from database import get_balance, update_balance, record_game
from logger import log_event
from cogs.utils_view import PlayAgainView

# --- LOGIC SETUP ---
def generate_roulette_wheel():
    wheel = []
    # Vegas Rules
    wheel.append({"color": "🟢", "type": "green", "val": 0, "label": "🟢 0"})
    wheel.append({"color": "🟢", "type": "green", "val": 37, "label": "🟢 00"})
    
    # Generate 1-36 with alternating colors
    for i in range(1, 37):
        if i % 2 != 0:
            color_emoji = "🔴"
            color_type = "red"
        else:
            color_emoji = "⚫"
            color_type = "black"
            
        # Format: "🔴 13"
        wheel.append({
            "color": color_emoji, 
            "type": color_type, 
            "val": i, 
            "label": f"{color_emoji} {i}"
        })
    return wheel

# Create a triple wheel so we can spin comfortably in the middle without hitting edges
BASE_WHEEL = generate_roulette_wheel()
MASTER_WHEEL = BASE_WHEEL * 3 

class Roulette(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Default State: Animations are ON
        self.animation_enabled = True

    @app_commands.command(name="roulette", description="Bet on Color, Parity (Even/Odd), or Number")
    @app_commands.describe(amount="Amount to bet", bet_on="Type: 'red', 'black', 'even', 'odd', or a number 0-36")
    async def roulette(self, interaction: discord.Interaction, amount: int, bet_on: str):
        from cogs.utils import acquire_game_lock
        if not await acquire_game_lock(interaction.user.id, interaction): return
        try:
            bet_on = bet_on.lower().strip()
        
            # --- 1. VALIDATION ---
            from database import process_bet
            await interaction.response.defer()
            if not await process_bet(interaction, amount):
                return

            specific_number = None
        
            if bet_on in ['red', 'black', 'even', 'odd', 'green']:
                pass
            elif bet_on.isdigit():
                specific_number = int(bet_on)
                if specific_number < 0 or specific_number > 36:
                    await interaction.followup.send("❌ | Numbers must be between 0 and 36.", ephemeral=True)
                    return
            else:
                await interaction.followup.send("❌ | Invalid bet. Choose: `red`, `black`, `even`, `odd`, or a number `0-36`.", ephemeral=True)
                return

            # --- 2. SETUP WINNER ---
            wheel_size = len(BASE_WHEEL)
            winning_index = random.randint(wheel_size, (wheel_size * 2) - 1)
            winning_slot = MASTER_WHEEL[winning_index]

            # --- 3. ANIMATION OR INSTANT SKIP ---
        
            if self.animation_enabled:
                # === PLAY ANIMATION ===
                await interaction.edit_original_response(content=f"🎰 | Betting **${amount}** on **{bet_on.upper()}**...")

                # Logic Setup
                raw_moves = [16, 8, 4, 3, 1, 1, 1]
                raw_delays = [0.3, 0.5, 0.8, 1.0, 1.3, 1.6, 2.0]

                # 50% Tip Over
                tip_over_active = False
                if random.choice([True, False]):
                    tip_over_active = True
                    raw_moves.append(1)
                    raw_delays.append(2.5) 
            
                # 25% Repeat Logic
                final_moves = []
                final_delays = []
                final_is_tip_over = [] 
            
                for i, (m, d) in enumerate(zip(raw_moves, raw_delays)):
                    is_this_tip_over = False
                    if tip_over_active and i == len(raw_moves) - 1:
                        is_this_tip_over = True

                    final_moves.append(m)
                    final_delays.append(d)
                    final_is_tip_over.append(is_this_tip_over)
                
                    if i < 3:
                        if random.random() < 0.25:
                            final_moves.append(m)
                            final_delays.append(d)
                            final_is_tip_over.append(False)

                # Backwards Calculation
                frame_indices = []
                current_calc_index = winning_index
            
                for move, is_tip_over in zip(reversed(final_moves), reversed(final_is_tip_over)):
                    if is_tip_over:
                        variance = 0
                    else:
                        variance = random.choice([3, 2, 1, 0, -1])
                
                    total_move = move + variance
                    if total_move < 1: total_move = 1
                    
                    frame_indices.insert(0, current_calc_index)
                    current_calc_index -= total_move

                # Loop
                for i in range(len(frame_indices)):
                    center_idx = frame_indices[i]
                    window = MASTER_WHEEL[center_idx - 2 : center_idx + 3]
                
                    lines = []
                    for idx, item in enumerate(window):
                        if idx == 2:
                            lines.append(f"**► {item['label']} ◄**")
                        else:
                            lines.append(f"  {item['label']}  ")

                    view_str = "\n".join(lines)
                
                    spin_embed = discord.Embed(title="🎡 Roulette Spinning...", color=discord.Color.gold())
                    spin_embed.description = f">>> {view_str}"
                
                    await interaction.edit_original_response(
                        content=None, embed=spin_embed
                    )
                
                    jitter = random.uniform(-0.1, 0.1)
                    actual_delay = final_delays[i] + jitter
                    if actual_delay < 0.1: actual_delay = 0.1
                    
                    await asyncio.sleep(actual_delay)
            else:
                # === SKIP ANIMATION (INSTANT) ===
                await interaction.edit_original_response(content=f"🎰 | Betting **${amount}** on **{bet_on.upper()}**... (Instant Result)")


            # --- 4. WIN CHECKING ---
            winnings = 0
            outcome_text = "LOST"
            won = False
            multiplier = 0

            result_val = winning_slot['val']
            result_color = winning_slot['type']
        
            if specific_number is not None:
                if specific_number == result_val:
                    won = True
                    multiplier = 36
            else:
                if bet_on == "red" and result_color == "red":
                    won = True; multiplier = 2
                elif bet_on == "black" and result_color == "black":
                    won = True; multiplier = 2
                elif bet_on == "green" and result_color == "green":
                    won = True; multiplier = 36
                elif bet_on == "even" and result_val != 0 and result_val % 2 == 0:
                    won = True; multiplier = 2
                elif bet_on == "odd" and result_val != 0 and result_val % 2 != 0:
                    won = True; multiplier = 2

            # --- 5. PAYOUT ---
            if won:
                winnings = amount * multiplier
                await update_balance(interaction.user.id, winnings)
                outcome_text = "WON"

            # --- 6. FINAL DISPLAY ---
            final_window = MASTER_WHEEL[winning_index - 2 : winning_index + 3]
            lines = []
            for idx, item in enumerate(final_window):
                if idx == 2:
                    lines.append(f"**► {item['label']} ◄**")
                else:
                    lines.append(f"  {item['label']}  ")
            final_view = "\n".join(lines)

            embed = discord.Embed(title="🎡 Roulette Result", color=discord.Color.green() if won else discord.Color.red())
            profit = winnings - amount if won else -amount
        
            embed.description = (
                f">>> {final_view}\n\n"
                f"**You bet on:** `{bet_on.capitalize()}`\n"
                f"**Result:** {'Correct!' if won else 'Incorrect!'}\n\n"
                f"{f'💰 **Profit:** +${profit}' if won else f'💸 **Loss:** -${abs(profit)}'}"
            )
        
            if won:
                await log_event(self.bot, f"{interaction.user.name} WON ${winnings} in Roulette.")
                await record_game(interaction.user.id, amount, profit, True)
            else:
                embed.add_field(name="Loss", value=f"-${amount}")
                await log_event(self.bot, f"{interaction.user.name} LOST ${amount} in Roulette.")
                await record_game(interaction.user.id, amount, -amount, False)
            
            embed.set_footer(text=f"New Balance: ${await get_balance(interaction.user.id)}")
        
            view = PlayAgainView(self.roulette.callback, self, interaction, amount, bet_on)
        
            if self.animation_enabled:
                await interaction.edit_original_response(content=None, embed=embed, view=view)
            else:
                await interaction.edit_original_response(content=None, embed=embed, view=view)
        finally:
            from cogs.utils import release_game_lock
            release_game_lock(interaction.user.id)

async def setup(bot):
    await bot.add_cog(Roulette(bot))
