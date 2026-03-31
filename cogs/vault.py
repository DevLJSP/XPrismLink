import discord
from discord import app_commands
from discord.ext import commands
import aiohttp
import os
from cogs.theme import Color

_API_BASE = "https://xprismplay.dpdns.org"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.5",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Referer": f"{_API_BASE}/portfolio",
    "Alt-Used": "xprismplay.dpdns.org",
}


def _get_cookies(bot) -> dict:
    tracker = bot.get_cog("Tracker")
    if tracker:
        return {
            "__Secure-better-auth.session_token": tracker.session_cookie,
            "cf_clearance": tracker.clearance_cookie,
        }
    return {
        "__Secure-better-auth.session_token": os.getenv("COOKIE_SESSION", ""),
        "cf_clearance": os.getenv("COOKIE_CLEARANCE", ""),
    }


class VaultCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    vault = app_commands.Group(name="vault", description="Vault commands")

    @vault.command(name="balance", description="Check the current XPrism vault balance")
    async def balance(self, interaction: discord.Interaction):
        await interaction.response.defer()

        try:
            async with aiohttp.ClientSession(
                cookies=_get_cookies(self.bot),
                timeout=aiohttp.ClientTimeout(total=10),
            ) as session:
                async with session.get(
                    f"{_API_BASE}/api/portfolio/summary", headers=_HEADERS
                ) as resp:
                    if resp.status in (401, 403):
                        await interaction.edit_original_response(
                            content="❌  Authentication failed. Cookies are expired — use `/admin cookies` to update them."
                        )
                        return

                    if resp.status != 200:
                        await interaction.edit_original_response(
                            content=f"❌  Failed to fetch vault balance (HTTP {resp.status})."
                        )
                        return

                    data = await resp.json()

        except aiohttp.ClientTimeout:
            await interaction.edit_original_response(
                content="❌  Request timed out while fetching vault balance."
            )
            return
        except Exception as e:
            await interaction.edit_original_response(
                content=f"❌  Unexpected error: `{type(e).__name__}: {e}`"
            )
            return

        cash       = float(data.get("baseCurrencyBalance", 0))
        coin_value = float(data.get("totalCoinValue", 0))
        total      = float(data.get("totalValue", 0))

        embed = discord.Embed(
            title="🏦  Vault Balance",
            description="Live balance of the **brazil** master account on XPrism.",
            color=Color.GOLD,
        )
        embed.add_field(name="💵  Cash",         value=f"**${cash:,.2f}**",       inline=True)
        embed.add_field(name="🪙  Coin Holdings", value=f"**${coin_value:,.2f}**", inline=True)
        embed.add_field(name="📊  Total Value",   value=f"**${total:,.2f}**",      inline=True)
        embed.set_footer(text="xprismplay.dpdns.org/user/brazil")

        await interaction.edit_original_response(embed=embed)


async def setup(bot):
    await bot.add_cog(VaultCog(bot))