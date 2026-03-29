import discord

ACTIVE_GAMES = set()

async def acquire_game_lock(user_id: int, interaction: discord.Interaction) -> bool:
    """Returns True if lock acquired, False if already playing."""
    if user_id in ACTIVE_GAMES:
        msg = "❌ | You're already playing a game! Finish it before starting a new one."
        if not interaction.response.is_done():
            await interaction.response.send_message(msg, ephemeral=True)
        else:
            await interaction.followup.send(msg, ephemeral=True)
        return False
    ACTIVE_GAMES.add(user_id)
    return True

def release_game_lock(user_id: int):
    ACTIVE_GAMES.discard(user_id)
