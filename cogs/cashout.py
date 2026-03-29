import discord
from discord import app_commands
from discord.ext import commands
from database import get_balance, update_balance, deduct_balance_if_sufficient
from cogs.linker import is_linked, get_linked_users
from logger import log_event, get_config
import os
import aiohttp
import re

ADMIN_ID = 1284967683246264443

class CashoutApprovalView(discord.ui.View):
    def __init__(self, bot):
        super().__init__(timeout=None)  # No timeout — persists until clicked
        self.bot = bot

    def _extract_data(self, interaction: discord.Interaction):
        if not interaction.message.embeds: return None, None, None
        desc = interaction.message.embeds[0].description
        if not desc: return None, None, None
        
        uid_match = re.search(r"\(`(\d+)`\)", desc)
        user_id = int(uid_match.group(1)) if uid_match else None
        
        rug_match = re.search(r"\*\*Rugplay:\*\* `([^`]+)`", desc)
        rugplay_username = rug_match.group(1) if rug_match else None
        
        amt_match = re.search(r"\*\*Amount:\*\* \*\*\$(\d+)\*\*", desc)
        amount = int(amt_match.group(1)) if amt_match else None
        
        return user_id, rugplay_username, amount

    @discord.ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="✅", custom_id="cashout_approve")
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ | Only the admin can approve cashouts.", ephemeral=True)
            return
            
        requester_id, rugplay_username, amount = self._extract_data(interaction)
        if not requester_id or not rugplay_username or not amount:
            await interaction.response.send_message("❌ | Could not parse cashout data from embed.", ephemeral=True)
            return

        await interaction.response.defer()
        
        for child in self.children:
            child.disabled = True
            
        embed = interaction.message.embeds[0]

        # Execute the transfer
        success = await self._do_transfer(rugplay_username, amount)
        
        if success:
            embed.color = discord.Color.green()
            embed.set_footer(text=f"✅ APPROVED by {interaction.user.name}")
            await interaction.message.edit(embed=embed, view=self)
            
            await log_event(self.bot, f"Cashout APPROVED: ${amount} to {rugplay_username} (Discord: {requester_id})")
            
            try:
                user = self.bot.get_user(requester_id) or await self.bot.fetch_user(requester_id)
                await user.send(f"✅ Your cashout of **${amount}** has been **approved** and sent to **{rugplay_username}** on Rugplay!")
            except:
                pass
        else:
            # Refund on API failure
            from database import update_balance
            await update_balance(requester_id, amount)
            
            embed.color = discord.Color.red()
            embed.set_footer(text=f"❌ FAILED API Transfer. Balance Refunded.")
            await interaction.message.edit(embed=embed, view=self)
            
            await interaction.followup.send(f"❌ | Transfer API failed! Balance refunded to user. View permanently disabled.", ephemeral=True)
            await log_event(self.bot, f"Cashout FAILED (API error): ${amount} to {rugplay_username} — balance refunded")

    @discord.ui.button(label="Deny", style=discord.ButtonStyle.danger, emoji="❌", custom_id="cashout_deny")
    async def deny(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != ADMIN_ID:
            await interaction.response.send_message("❌ | Only the admin can deny cashouts.", ephemeral=True)
            return
            
        requester_id, rugplay_username, amount = self._extract_data(interaction)
        if not requester_id or not rugplay_username or not amount:
            await interaction.response.send_message("❌ | Could not parse cashout data from embed.", ephemeral=True)
            return

        await interaction.response.defer()
        
        for child in self.children:
            child.disabled = True
            
        from database import update_balance
        await update_balance(requester_id, amount)
        
        embed = interaction.message.embeds[0]
        embed.color = discord.Color.red()
        embed.set_footer(text=f"❌ DENIED by {interaction.user.name}")
        
        try:
            await interaction.message.edit(embed=embed, view=self)
        except Exception:
            pass
        
        await log_event(self.bot, f"Cashout DENIED: ${amount} to {rugplay_username} (Discord: {requester_id}) — balance refunded")
        
        try:
            user = self.bot.get_user(requester_id) or await self.bot.fetch_user(requester_id)
            await user.send(f"❌ Your cashout of **${amount}** has been **denied**. Your balance has been refunded.")
        except:
            pass

    async def _do_transfer(self, recipient_username: str, amount: int) -> bool:
        """Call the Rugplay transfer API to send cash."""
        session_cookie = os.getenv("COOKIE_SESSION", "")
        clearance_cookie = os.getenv("COOKIE_CLEARANCE", "")
        
        tracker = self.bot.get_cog("Tracker")
        if tracker:
            session_cookie = tracker.session_cookie
            clearance_cookie = tracker.clearance_cookie
        
        cookies = {
            "__Secure-better-auth.session_token": session_cookie,
            "cf_clearance": clearance_cookie
        }
        
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.5",
            "Content-Type": "application/json",
            "Alt-Used": "rugplay.com",
            "Sec-Fetch-Dest": "empty",
            "Sec-Fetch-Mode": "cors",
            "Sec-Fetch-Site": "same-origin",
            "Referer": "https://rugplay.com/portfolio",
            "Origin": "https://rugplay.com"
        }
        
        payload = {
            "recipientUsername": recipient_username,
            "type": "CASH",
            "amount": amount
        }
        
        try:
            async with aiohttp.ClientSession(cookies=cookies) as session:
                async with session.post("https://rugplay.com/api/transfer", headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        return True
                    else:
                        print(f"[CASHOUT ERROR] Transfer API returned {resp.status}: {await resp.text()}")
                        return False
        except Exception as e:
            print(f"[CASHOUT ERROR] Transfer failed: {e}")
            return False


class Cashout(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session_cookie = os.getenv("COOKIE_SESSION", "")
        self.clearance_cookie = os.getenv("COOKIE_CLEARANCE", "")

    @app_commands.command(name="cashout", description="Request a cashout to your linked Rugplay account")
    @app_commands.describe(amount="Amount to cash out")
    async def cashout(self, interaction: discord.Interaction, amount: int):
        await interaction.response.defer(ephemeral=True)
        if not is_linked(interaction.user.id):
            await interaction.followup.send("❌ | You must link your Rugplay account first! Use `/link`.", ephemeral=True)
            return
        
        if amount <= 0:
            await interaction.followup.send("❌ | Amount must be greater than $0.", ephemeral=True)
            return
        
        # Deduct balance atomically
        success = await deduct_balance_if_sufficient(interaction.user.id, amount)
        if not success:
            bal = await get_balance(interaction.user.id)
            deposit_msg = (
                f"❌ | You only have **${bal}**!"
                f"\n\n💰 To deposit, send money to **crackhead** on Rugplay:"
                f"\nhttps://rugplay.com/user/crackhead"
            )
            await interaction.followup.send(deposit_msg, ephemeral=True)
            return
        
        # Get linked rugplay username
        linked = get_linked_users()
        user_data = linked.get(str(interaction.user.id))
        if not user_data:
            await update_balance(interaction.user.id, amount) # refund
            await interaction.followup.send("❌ | Could not find your linked account data.", ephemeral=True)
            return
        
        rugplay_username = user_data["rugplay_username"]
        
        # Get cashout channel
        config = get_config()
        cashout_channel_id = config.get("cashout_channel_id")
        
        if not cashout_channel_id:
            # Refund if no channel configured
            await update_balance(interaction.user.id, amount)
            await interaction.followup.send("❌ | Cashout channel not configured. Ask an admin to set it with `/admin cashoutchannel`.", ephemeral=True)
            return
        
        cashout_channel = self.bot.get_channel(cashout_channel_id)
        if not cashout_channel:
            await update_balance(interaction.user.id, amount)
            await interaction.followup.send("❌ | Could not find the cashout channel. Ask an admin to reconfigure.", ephemeral=True)
            return
        
        # Build the approval embed
        embed = discord.Embed(
            title="💸 Cashout Request",
            color=discord.Color.orange(),
            description=(
                f"**User:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                f"**Rugplay:** `{rugplay_username}` — [Profile](https://rugplay.com/user/{rugplay_username})\n"
                f"**Amount:** **${amount}**\n\n"
                f"⏳ Awaiting admin approval..."
            )
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        view = CashoutApprovalView(self.bot)
        
        # Send to cashout channel and ping admin
        await cashout_channel.send(
            content=f"<@{ADMIN_ID}> — New cashout request!",
            embed=embed,
            view=view
        )
        
        await interaction.followup.send(
            f"✅ | Cashout request for **${amount}** submitted!\n"
            f"Your balance has been deducted. An admin will review your request shortly.\n"
            f"You'll be DM'd when it's approved or denied.",
            ephemeral=True
        )
        
        await log_event(self.bot, f"{interaction.user.name} requested cashout: ${amount} to {rugplay_username}")


async def setup(bot):
    bot.add_view(CashoutApprovalView(bot))
    await bot.add_cog(Cashout(bot))
