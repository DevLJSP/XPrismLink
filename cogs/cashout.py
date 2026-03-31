import discord
from discord import app_commands
from discord.ext import commands
from database import (
    get_balance, update_balance, deduct_balance_if_sufficient,
    create_cashout_request, get_cashout_request, update_cashout_status
)
from cogs.linker import is_linked, get_linked_users
from logger import log_event
import os
import aiohttp

ADMIN_ID = 1384301389047660574
AUTO_CASHOUT_LIMIT = 5000


async def do_transfer(bot, recipient_username: str, amount: int) -> bool:
    """Call the XPrism transfer API to send cash."""
    session_cookie = os.getenv("COOKIE_SESSION", "")
    clearance_cookie = os.getenv("COOKIE_CLEARANCE", "")

    tracker = bot.get_cog("Tracker")
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
        "Alt-Used": "xprismplay.dpdns.org",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Referer": "https://xprismplay.dpdns.org/portfolio",
        "Origin": "https://xprismplay.dpdns.org"
    }

    payload = {
        "recipientUsername": recipient_username,
        "type": "CASH",
        "amount": amount
    }

    try:
        async with aiohttp.ClientSession(cookies=cookies) as session:
            async with session.post(
                "https://xprismplay.dpdns.org/api/transfer",
                headers=headers,
                json=payload
            ) as resp:
                if resp.status == 200:
                    return True
                else:
                    print(f"[CASHOUT ERROR] Transfer API returned {resp.status}: {await resp.text()}")
                    return False
    except Exception as e:
        print(f"[CASHOUT ERROR] Transfer failed: {e}")
        return False


async def dm_user(bot, user_id: int, title: str, description: str, color: discord.Color = discord.Color.green()):
    try:
        user = bot.get_user(user_id) or await bot.fetch_user(user_id)
        if not user:
            return

        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )
        embed.set_footer(text="xprismplay.dpdns.org")
        await user.send(embed=embed)
    except Exception:
        pass


async def process_cashout_action(bot, cashout_id: int, action: str):
    """
    Process approve/deny for a cashout request.
    Returns (success: bool, message: str).
    """
    req = await get_cashout_request(cashout_id)
    if not req:
        return False, f"Cashout **#{cashout_id}** not found."

    if req["status"] != "pending":
        return False, f"Cashout **#{cashout_id}** is already **{req['status']}**."

    user_id = req["user_id"]
    prism_username = req["prism_username"]
    amount = req["amount"]

    if action == "approve":
        success = await do_transfer(bot, prism_username, amount)

        if success:
            await update_cashout_status(cashout_id, "approved")
            await log_event(
                bot,
                f"Cashout #{cashout_id} APPROVED: ${amount} to {prism_username} (Discord: {user_id})"
            )

            await dm_user(
                bot,
                user_id,
                "✅ Cashout Approved",
                (
                    f"Your cashout **#{cashout_id}** of **${amount:,}** has been **approved** "
                    f"and sent to **{prism_username}** on XPrism."
                ),
                discord.Color.green()
            )

            return True, f"✅ Cashout **#{cashout_id}** approved! **${amount:,}** sent to **{prism_username}**."
        else:
            await update_balance(user_id, amount)
            await update_cashout_status(cashout_id, "failed")
            await log_event(
                bot,
                f"Cashout #{cashout_id} FAILED (API error): ${amount} to {prism_username} — balance refunded"
            )
            return False, f"❌ Transfer API failed for **#{cashout_id}**! Balance refunded to user. Check cookies."

    elif action == "deny":
        await update_balance(user_id, amount)
        await update_cashout_status(cashout_id, "denied")
        await log_event(
            bot,
            f"Cashout #{cashout_id} DENIED: ${amount} to {prism_username} (Discord: {user_id}) — balance refunded"
        )

        await dm_user(
            bot,
            user_id,
            "❌ Cashout Denied",
            (
                f"Your cashout **#{cashout_id}** of **${amount:,}** has been **denied**. "
                f"Your balance has been refunded."
            ),
            discord.Color.red()
        )

        return True, f"❌ Cashout **#{cashout_id}** denied. **${amount:,}** refunded to user."

    return False, "Invalid action."


class Cashout(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="cashout", description="Request a cashout to your linked Prism account")
    @app_commands.describe(amount="Amount to cash out")
    async def cashout(self, interaction: discord.Interaction, amount: int):
        await interaction.response.defer(ephemeral=True)

        if not is_linked(interaction.user.id):
            await interaction.followup.send("❌ | You must link your Prism account first! Use `/link`.", ephemeral=True)
            return

        if amount <= 0:
            await interaction.followup.send("❌ | Amount must be greater than $0.", ephemeral=True)
            return

        success = await deduct_balance_if_sufficient(interaction.user.id, amount)
        if not success:
            bal = await get_balance(interaction.user.id)
            deposit_msg = (
                f"❌ | You only have **${bal:,}**!\n\n"
                f"💰 To deposit, send money to **xprismbank** on XPrism:\n"
                f"https://xprismplay.dpdns.org/user/xprismbank"
            )
            await interaction.followup.send(deposit_msg, ephemeral=True)
            return

        linked = get_linked_users()
        user_data = linked.get(str(interaction.user.id))
        if not user_data:
            await update_balance(interaction.user.id, amount)
            await interaction.followup.send("❌ | Could not find your linked account data.", ephemeral=True)
            return

        prism_username = user_data["prism_username"]

        cashout_id = await create_cashout_request(interaction.user.id, prism_username, amount)

        if amount <= AUTO_CASHOUT_LIMIT:
            await interaction.followup.send(
                f"⏳ | Cashout **#{cashout_id}** is being processed automatically...\n"
                f"Amount: **${amount:,}**\n"
                f"No admin approval is needed for cashouts up to **${AUTO_CASHOUT_LIMIT:,}**.",
                ephemeral=True
            )

            success = await do_transfer(self.bot, prism_username, amount)

            if success:
                await update_cashout_status(cashout_id, "approved")
                await log_event(
                    self.bot,
                    f"Auto cashout #{cashout_id} APPROVED: ${amount} to {prism_username} (Discord: {interaction.user.id})"
                )

                try:
                    user = self.bot.get_user(interaction.user.id) or await self.bot.fetch_user(interaction.user.id)
                    if user:
                        embed = discord.Embed(
                            title="✅ Cashout Completed",
                            description=(
                                f"Your cashout of **${amount:,}** has been **approved** and sent to "
                                f"**{prism_username}** on XPrism."
                            ),
                            color=discord.Color.green()
                        )
                        embed.add_field(name="Cashout ID", value=f"`#{cashout_id}`", inline=True)
                        embed.add_field(name="Status", value="**Completed**", inline=True)
                        embed.set_footer(text="xprismplay.dpdns.org")
                        await user.send(embed=embed)
                except Exception:
                    pass

                return

            await update_balance(interaction.user.id, amount)
            await update_cashout_status(cashout_id, "failed")
            await interaction.followup.send(
                f"❌ | Auto cashout **#{cashout_id}** failed.\n"
                f"Your balance has been refunded.\n"
                f"Check the bot cookies / session.",
                ephemeral=True
            )
            await log_event(
                self.bot,
                f"Auto cashout #{cashout_id} FAILED: ${amount} to {prism_username} — balance refunded"
            )
            return

        embed = discord.Embed(
            title=f"💸 Cashout Request #{cashout_id}",
            color=discord.Color.orange(),
            description=(
                f"**User:** {interaction.user.mention} (`{interaction.user.id}`)\n"
                f"**Prism:** `{prism_username}` — [Profile](https://xprismplay.dpdns.org/user/{prism_username})\n"
                f"**Amount:** **${amount:,}**\n\n"
                f"⏳ Awaiting admin approval...\n"
                f"✅ `/admin action:Cashout Approve target:{cashout_id}`\n"
                f"❌ `/admin action:Cashout Deny target:{cashout_id}`"
            )
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)

        webhook_url = os.getenv("CASHOUT_WEBHOOK_URL")
        if not webhook_url:
            await update_balance(interaction.user.id, amount)
            await update_cashout_status(cashout_id, "failed")
            await interaction.followup.send("❌ | Cashout webhook not configured in .env.", ephemeral=True)
            return

        try:
            webhook = discord.Webhook.from_url(webhook_url, client=self.bot)
            await webhook.send(
                content=f"<@{ADMIN_ID}> — New cashout request!",
                embed=embed
            )
        except Exception as e:
            await update_balance(interaction.user.id, amount)
            await update_cashout_status(cashout_id, "failed")
            await interaction.followup.send(f"❌ | Failed to send request to webhook: {e}", ephemeral=True)
            return

        await interaction.followup.send(
            f"✅ | Cashout request **#{cashout_id}** for **${amount:,}** submitted!\n"
            f"Your balance has been deducted. An admin will review your request shortly.\n"
            f"You'll be DM'd when it's approved or denied.",
            ephemeral=True
        )

        await log_event(
            self.bot,
            f"{interaction.user.name} requested cashout #{cashout_id}: ${amount} to {prism_username}"
        )


async def setup(bot):
    await bot.add_cog(Cashout(bot))