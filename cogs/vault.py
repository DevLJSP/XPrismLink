import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import os

class VaultCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    vault = app_commands.Group(name="vault", description="Vault commands")

    @vault.command(name="balance", description="Check the current vault balance on Rugplay")
    async def balance(self, interaction: discord.Interaction):
        await interaction.response.defer()

        tracker = self.bot.get_cog("Tracker")
        session_cookie = tracker.session_cookie if tracker else os.getenv("COOKIE_SESSION", "")
        clearance_cookie = tracker.clearance_cookie if tracker else os.getenv("COOKIE_CLEARANCE", "")

        cookies = {
            "__Secure-better-auth.session_token": session_cookie,
            "cf_clearance": clearance_cookie
        }

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0",
            "Accept": "application/json",
            "Accept-Language": "en-US,en;q=0.5",
            "Alt-Used": "rugplay.com",
            "Referer": "https://rugplay.com/portfolio",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin"
        }

        try:
            async with aiohttp.ClientSession(cookies=cookies) as session:
                async with session.get(
                    "https://rugplay.com/api/portfolio/summary",
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        cash = float(data.get("baseCurrencyBalance", 0))
                        coin_value = float(data.get("totalCoinValue", 0))
                        total = float(data.get("totalValue", 0))

                        embed = discord.Embed(
                            title="🏦 Vault Balance",
                            color=discord.Color.gold(),
                            description="Current balance of the **brazil** master account on Rugplay."
                        )
                        embed.add_field(name="💵 Cash Balance", value=f"**${cash:,.2f}**", inline=True)
                        embed.add_field(name="🪙 Coin Holdings", value=f"**${coin_value:,.2f}**", inline=True)
                        embed.add_field(name="📊 Total Value", value=f"**${total:,.2f}**", inline=True)
                        embed.set_footer(text="rugplay.com/user/brazil")

                        await interaction.edit_original_response(embed=embed)

                    elif resp.status in (401, 403):
                        await interaction.edit_original_response(
                            content="❌ | Authentication failed. Cookies are expired — use `/admin cookies` to update them."
                        )
                    else:
                        await interaction.edit_original_response(
                            content=f"❌ | Failed to fetch vault balance (HTTP {resp.status})."
                        )

        except aiohttp.ClientTimeout:
            await interaction.edit_original_response(content="❌ | Request timed out while fetching vault balance.")
        except Exception as e:
            await interaction.edit_original_response(content=f"❌ | Unexpected error: `{type(e).__name__}`")


async def setup(bot):
    await bot.add_cog(VaultCog(bot))