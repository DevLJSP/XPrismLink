import discord
from discord.ext import commands
import os
import asyncio
from dotenv import load_dotenv
from database import init_db

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')

class EconomyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix='!', intents=discord.Intents.default())

    async def setup_hook(self):
        await init_db()
        print("Database initialized.")

        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"Loaded: {filename}")
                except Exception as e:
                    print(f"Failed to load {filename}: {e}")

        await self.tree.sync()
        print("Slash commands synced.")

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')

    async def on_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        original = getattr(error, 'original', error)
        # Stale/expired interaction token — happens after restarts or re-syncs. Not a real error.
        if isinstance(original, discord.NotFound) and original.code == 10062:
            return
        # Everything else should still be visible in the console.
        raise error


bot = EconomyBot()

if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Error: DISCORD_TOKEN not found in .env file.")