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
        # 1. Initialize Database
        await init_db()
        print("Database initialized.")

        # 2. Load Cogs (Extensions)
        # Iterates through files in the 'cogs' folder
        for filename in os.listdir('./cogs'):
            if filename.endswith('.py'):
                try:
                    await self.load_extension(f'cogs.{filename[:-3]}')
                    print(f"Loaded extension: {filename}")
                except Exception as e:
                    print(f"Failed to load {filename}: {e}")

        # 3. Sync Slash Commands
        await self.tree.sync()
        print("Slash commands synced!")

    async def on_ready(self):
        print(f'Logged in as {self.user} (ID: {self.user.id})')

bot = EconomyBot()

if __name__ == "__main__":
    if TOKEN:
        bot.run(TOKEN)
    else:
        print("Error: DISCORD_TOKEN not found in .env file.")