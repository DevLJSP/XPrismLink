import discord

# ─── Brand Colors ───────────────────────────────────────────────────────────
class Color:
    WIN      = discord.Color.from_str("#2ecc71")   # green
    LOSS     = discord.Color.from_str("#e74c3c")   # red
    NEUTRAL  = discord.Color.from_str("#95a5a6")   # grey (tie/push)
    PLAYING  = discord.Color.from_str("#3498db")   # blue
    GOLD     = discord.Color.from_str("#f1c40f")   # jackpot / natural
    WARNING  = discord.Color.from_str("#e67e22")   # partial win / orange
    CASHOUT  = discord.Color.from_str("#27ae60")   # cashed out
    PENDING  = discord.Color.from_str("#e67e22")   # pending actions

# ─── Shared Embed Builders ───────────────────────────────────────────────────
def game_embed(title: str, interaction: discord.Interaction, color=None) -> discord.Embed:
    """Base embed for an active game."""
    embed = discord.Embed(title=title, color=color or Color.PLAYING)
    embed.set_author(
        name=f"{interaction.user.display_name}",
        icon_url=interaction.user.display_avatar.url
    )
    return embed

def result_embed(title: str, interaction: discord.Interaction, won: bool, profit: int) -> discord.Embed:
    """Result embed with colour and profit/loss field pre-filled."""
    color = Color.WIN if won else Color.LOSS
    embed = discord.Embed(title=title, color=color)
    embed.set_author(
        name=f"{interaction.user.display_name}",
        icon_url=interaction.user.display_avatar.url
    )
    if profit > 0:
        embed.add_field(name="Profit", value=f"💰 +${profit:,}", inline=True)
    elif profit < 0:
        embed.add_field(name="Loss", value=f"💸 -${abs(profit):,}", inline=True)
    else:
        embed.add_field(name="Result", value="➖ Break even", inline=True)
    return embed

# ─── Standard Error Replies ──────────────────────────────────────────────────
async def send_error(interaction: discord.Interaction, message: str, ephemeral: bool = True):
    """Send a consistent error message regardless of interaction state."""
    if interaction.response.is_done():
        await interaction.followup.send(f"❌  {message}", ephemeral=ephemeral)
    else:
        await interaction.response.send_message(f"❌  {message}", ephemeral=ephemeral)