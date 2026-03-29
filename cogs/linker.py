import discord
from discord.ext import commands
from discord import app_commands
import websockets
import asyncio
import os
import json
import random
from logger import get_config, log_event

DATA_FILE = "linked_users.json"

def get_linked_users():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_linked_users(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

def is_linked(user_id):
    users = get_linked_users()
    if str(user_id) not in users:
        return False
        
    config = get_config()
    banned_users = config.get("banned_users", [])
    if str(user_id) in banned_users:
        return False
        
    return True

class Linker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active_tasks = {}

    async def link_listener(self, url: str, interaction: discord.Interaction, expected_username: str, target_amount: float):
        browser_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Origin": "https://rugplay.com"
        }
        
        target_str = f"{target_amount:.5f}"
        
        try:
            async with websockets.connect(url, additional_headers=browser_headers) as websocket:
                payloads = [
                    {"type": "subscribe", "channel": "trades:all"},
                    {"type": "subscribe", "channel": "trades:large"},
                    {"type": "set_coin", "coinSymbol": "@global"}
                ]
                for payload in payloads:
                    await websocket.send(json.dumps(payload))

                timeout_seconds = 600 
                start_time = asyncio.get_event_loop().time()

                async for message in websocket:
                    if asyncio.get_event_loop().time() - start_time > timeout_seconds:
                        await interaction.followup.send("⏳ Your verification timed out after 10 minutes. Please run `/link` again.", ephemeral=True)
                        break

                    try:
                        data = json.loads(message)
                        
                        if data.get("type") == "all-trades":
                            trade_data = data.get("data", {})
                            
                            trade_type = trade_data.get("type", "")
                            trade_user = trade_data.get("username", "")
                            trade_value = trade_data.get("totalValue", 0)
                            trade_userid = trade_data.get("userId", "")
                            coin_symbol = trade_data.get("coinSymbol", "")
                            
                            if trade_type == "BUY" and coin_symbol == "RUGLINK" and trade_user.lower() == expected_username.lower() and f"{trade_value:.5f}" == target_str:
                                
                                users = get_linked_users()
                                users[str(interaction.user.id)] = {
                                    "discord_username": str(interaction.user),
                                    "rugplay_username": trade_user,
                                    "rugplay_userid": trade_userid
                                }
                                save_linked_users(users)
                                
                                embed = discord.Embed(
                                    title="✅ Account Linked Successfully!",
                                    description=f"Your Discord account is now linked to **{trade_user}**.",
                                    color=discord.Color.green()
                                )
                                await interaction.followup.send(embed=embed, ephemeral=True)
                                await log_event(self.bot, f"{interaction.user} ({interaction.user.id}) linked to Rugplay: {trade_user} (ID: {trade_userid}) — https://rugplay.com/user/{trade_user}")
                                break 
                                
                    except json.JSONDecodeError:
                        pass
                        
        except asyncio.CancelledError:
            pass 
        except Exception as e:
            await interaction.followup.send(f"❌ Connection Error: `{e}`", ephemeral=True)
        finally:
            if interaction.user.id in self.active_tasks:
                del self.active_tasks[interaction.user.id]

    @app_commands.command(name="link", description="Verify and link your Rugplay account")
    @app_commands.describe(username="Your exact Rugplay username")
    async def link_cmd(self, interaction: discord.Interaction, username: str):
        if interaction.user.id in self.active_tasks:
            await interaction.response.send_message("⚠️ You already have a verification pending. Please finish it or type `/cancel`.", ephemeral=True)
            return
            
        self.active_tasks[interaction.user.id] = True

        random_decimals = random.randint(10000, 99999)
        target_amount = float(f"1.{random_decimals}")

        embed = discord.Embed(
            title="🔗 Link Your Rugplay Account",
            description=f"Linking **{username}** to your Discord.\n\nTo verify you own this account, please go to Rugplay and **BUY** exactly:\n### **${target_amount:.5f} of RUGLINK**\n\n*Waiting for trade to appear on the global market... (Times out in 10 minutes)*",
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        
        task = asyncio.create_task(self.link_listener("wss://ws.rugplay.com/", interaction, username, target_amount))
        self.active_tasks[interaction.user.id] = task

    @app_commands.command(name="cancel", description="Cancel your pending account verification")
    async def cancel_cmd(self, interaction: discord.Interaction):
        task = self.active_tasks.get(interaction.user.id)
        if task:
            task.cancel() 
            del self.active_tasks[interaction.user.id]
            await interaction.response.send_message("🛑 Cancelled your pending verification.", ephemeral=True)
        else:
            await interaction.response.send_message("⚠️ You don't have any pending verifications.", ephemeral=True)

    @app_commands.command(name="id", description="Check linked Rugplay info")
    @app_commands.describe(user="User to check (leave blank for yourself)")
    async def check_id(self, interaction: discord.Interaction, user: discord.User = None):
        target = user or interaction.user
        
        users = get_linked_users()
        target_id_str = str(target.id)
        
        if target_id_str not in users:
            await interaction.response.send_message(f"❌ | **{target.name}** is not linked to any Rugplay account.", ephemeral=True)
            return
            
        data = users[target_id_str]
        rp_user = data.get("rugplay_username", "Unknown")
        rp_id = data.get("rugplay_userid", "Unknown")
        
        embed = discord.Embed(title="🔍 Rugplay Linked ID", color=discord.Color.blue())
        embed.add_field(name="Discord User", value=f"{target.mention} (`{target.id}`)", inline=False)
        embed.add_field(name="Rugplay Username", value=f"`{rp_user}`", inline=True)
        embed.add_field(name="Rugplay UserID", value=f"`{rp_id}`", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Linker(bot))
