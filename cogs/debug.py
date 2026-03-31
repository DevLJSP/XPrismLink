import discord
from discord import app_commands
from discord.ext import commands
from database import update_balance, set_balance, get_balance, get_casino_stats, set_casino_stat, get_active_lottery, start_lottery, end_lottery_active, get_all_tickets, clear_all_tickets
from cogs.linker import get_linked_users
from logger import log_event, get_logs, save_config, get_config
import os
import aiohttp

ADMIN_ID = 1384301389047660574

class Debug(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def is_admin(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == ADMIN_ID

    def _resolve_target(self, target: str):
        """Resolve a target string (mention, Discord ID, or Prism username) to a Discord ID string."""
        target = target.strip()
        discord_id = None
        
        if target.startswith('<@') and target.endswith('>'):
            try:
                discord_id = str(''.join(c for c in target if c.isdigit()))
            except:
                pass
        elif target.isdigit():
            discord_id = str(target)
        
        if discord_id is None:
            linked = get_linked_users()
            target_lower = target.lower()
            for did, info in linked.items():
                if info.get("prism_username", "").lower() == target_lower:
                    discord_id = str(did)
                    break
        
        return discord_id

    @app_commands.command(name="admin", description="Admin toolkit")
    @app_commands.describe(
        action="Action to perform",
        target="User Discord ID, Prism Username, or Cashout ID (for approve/deny)",
        amount="Amount (for balance/cashout/setstats)",
        channel="Channel (for logchannel/cashoutchannel)",
        session="Session cookie (for cookies)",
        clearance="Clearance cookie (for cookies)",
        game="Game (for debug) / Stat field name (for setstats)",
        state="True/False (for debug)"
    )
    @app_commands.choices(action=[
        app_commands.Choice(name="Balance Set", value="bal_set"),
        app_commands.Choice(name="Balance Add", value="bal_add"),
        app_commands.Choice(name="Balance Remove", value="bal_remove"),
        app_commands.Choice(name="Debug Mode", value="debug"),
        app_commands.Choice(name="View Logs", value="logs"),
        app_commands.Choice(name="Set Log Channel", value="logchannel"),
        app_commands.Choice(name="Ban User", value="ban"),
        app_commands.Choice(name="Unban User", value="unban"),
        app_commands.Choice(name="Update Cookies", value="cookies"),
        app_commands.Choice(name="Force Cashout", value="cashout"),
        app_commands.Choice(name="Cashout Approve", value="cashout_approve"),
        app_commands.Choice(name="Cashout Deny", value="cashout_deny"),
        app_commands.Choice(name="Cashout Pending", value="cashout_pending"),
        app_commands.Choice(name="Set Cashout Channel", value="cashoutchannel"),
        app_commands.Choice(name="Casino Stats", value="stats"),
        app_commands.Choice(name="Set Casino Stats", value="setstats"),
        app_commands.Choice(name="Lottery Start", value="l_start"),
        app_commands.Choice(name="Lottery Draw", value="l_draw"),
        app_commands.Choice(name="Lottery Rig Draw", value="l_rig"),
        app_commands.Choice(name="Sync Server", value="sync")
    ])
    async def admin(self, interaction: discord.Interaction, action: app_commands.Choice[str], 
                    target: str = None, 
                    amount: int = None, 
                    channel: discord.TextChannel = None, 
                    session: str = None, 
                    clearance: str = None,
                    game: str = None,
                    state: bool = None):
        
        if not self.is_admin(interaction):
            await interaction.response.send_message("❌ | Admin only.", ephemeral=True)
            return

        cmd = action.value
        
        if cmd == "sync":
            if target is None:
                await interaction.response.send_message("❌ | Missing 'target' Server ID.", ephemeral=True)
                return
            try:
                await interaction.response.defer(ephemeral=True)
                guild_id = int(target.strip())
                guild = discord.Object(id=guild_id)
                self.bot.tree.copy_global_to(guild=guild)
                await self.bot.tree.sync(guild=guild)
                await interaction.followup.send(f"✅ | Commands forcefully synced instantly to Server `{guild_id}`!", ephemeral=True)
            except Exception as e:
                try:
                    await interaction.followup.send(f"❌ | Failed to sync to that server: `{e}`", ephemeral=True)
                except:
                    await interaction.response.send_message(f"❌ | Failed to sync to that server: `{e}`", ephemeral=True)

        elif cmd == "debug":
            if game is None or state is None:
                await interaction.response.send_message("❌ | Missing 'game' or 'state' parameters.", ephemeral=True)
                return
            
            if game.lower() == "roulette":
                cog = self.bot.get_cog("Roulette")
                if cog:
                    cog.animation_enabled = state
                    status = "ENABLED" if state else "DISABLED"
                    await interaction.response.send_message(f"⚙️ | Roulette animations **{status}**.", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ | Roulette Cog not found.", ephemeral=True)
            elif game.lower() == "mines":
                cog = self.bot.get_cog("Minesweeper")
                if cog:
                    cog.debug_mode = state
                    status = "VISIBLE" if state else "HIDDEN"
                    await interaction.response.send_message(f"⚙️ | Minesweeper debug mode: **{status}**.\n(Bombs will appear as 🧨).", ephemeral=True)
                else:
                    await interaction.response.send_message("❌ | Minesweeper Cog not found.", ephemeral=True)
            else:
                await interaction.response.send_message("❌ | Invalid game.", ephemeral=True)

        elif cmd in ("bal_set", "bal_add", "bal_remove"):
            if target is None or amount is None:
                await interaction.response.send_message("❌ | Missing 'target' or 'amount'.", ephemeral=True)
                return
                
            discord_id = self._resolve_target(target)
            if discord_id is None:
                await interaction.response.send_message(f"❌ | Could not find a linked user matching '{target}'.", ephemeral=True)
                return
                
            from database import set_balance, update_balance
            if cmd == "bal_set":
                await set_balance(int(discord_id), amount)
                await interaction.response.send_message(f"✅ | Set balance to **${amount}** for user {discord_id}.", ephemeral=True)
                await log_event(self.bot, f"Admin set balance for {discord_id} to ${amount}")
            elif cmd == "bal_add":
                await update_balance(int(discord_id), amount)
                await interaction.response.send_message(f"✅ | Added **${amount}** to user {discord_id}'s balance.", ephemeral=True)
                await log_event(self.bot, f"Admin added ${amount} to {discord_id}'s balance")
            elif cmd == "bal_remove":
                await update_balance(int(discord_id), -amount)
                await interaction.response.send_message(f"✅ | Removed **${amount}** from user {discord_id}'s balance.", ephemeral=True)
                await log_event(self.bot, f"Admin removed ${amount} from {discord_id}'s balance")

        elif cmd == "logs":
            logs = get_logs()
            if not logs:
                await interaction.response.send_message("📜 | No logs found yet.", ephemeral=True)
                return
            recent = logs[-10:]
            recent.reverse()
            log_str = "\n".join(recent)
            if len(log_str) > 1900: log_str = log_str[:1900] + "..."
            await interaction.response.send_message(f"📜 **Latest Logs:**\n```\n{log_str}\n```", ephemeral=True)
            
        elif cmd == "logchannel":
            if channel is None:
                await interaction.response.send_message("❌ | Missing 'channel'.", ephemeral=True)
                return
            config = get_config()
            config["log_channel_id"] = channel.id
            save_config(config)
            await interaction.response.send_message(f"✅ | Log channel has been set to {channel.mention}!", ephemeral=True)
            await log_event(self.bot, f"Admin configured log channel to {channel.id}")

        elif cmd == "ban":
            if target is None:
                await interaction.response.send_message("❌ | Missing 'target'.", ephemeral=True)
                return
                
            discord_id = self._resolve_target(target)
            if discord_id is None:
                await interaction.response.send_message(f"❌ | Could not find user '{target}'.", ephemeral=True)
                return

            config = get_config()
            banned = config.get("banned_users", [])
            if discord_id not in banned:
                banned.append(discord_id)
                config["banned_users"] = banned
                save_config(config)
            await interaction.response.send_message(f"🔨 | User {discord_id} has been banned from the bot.", ephemeral=True)
            await log_event(self.bot, f"Admin banned user {discord_id}")

        elif cmd == "unban":
            if target is None:
                await interaction.response.send_message("❌ | Missing 'target'.", ephemeral=True)
                return
                
            discord_id = self._resolve_target(target)
            if discord_id is None:
                await interaction.response.send_message(f"❌ | Could not find user '{target}'.", ephemeral=True)
                return

            config = get_config()
            banned = config.get("banned_users", [])
            if discord_id in banned:
                banned.remove(discord_id)
                config["banned_users"] = banned
                save_config(config)
                await interaction.response.send_message(f"✅ | User {discord_id} has been unbanned.", ephemeral=True)
                await log_event(self.bot, f"Admin unbanned user {discord_id}")
            else:
                await interaction.response.send_message(f"⚠️ | User {discord_id} is not currently banned.", ephemeral=True)

        elif cmd == "cookies":
            if session is None or clearance is None:
                await interaction.response.send_message("❌ | Missing 'session' or 'clearance'.", ephemeral=True)
                return
                
            tracker = self.bot.get_cog("Tracker")
            if tracker:
                tracker.session_cookie = session
                tracker.clearance_cookie = clearance
                tracker.cookies = {
                    "__Secure-better-auth.session_token": session,
                    "cf_clearance": clearance
                }
            cashout_cog = self.bot.get_cog("Cashout")
            if cashout_cog:
                cashout_cog.session_cookie = session
                cashout_cog.clearance_cookie = clearance
            try:
                with open(".env", "r") as f: lines = f.readlines()
                for i, line in enumerate(lines):
                    if line.startswith("COOKIE_SESSION="): lines[i] = f"COOKIE_SESSION={session}\n"
                    elif line.startswith("COOKIE_CLEARANCE="): lines[i] = f"COOKIE_CLEARANCE={clearance}\n"
                with open(".env", "w") as f: f.writelines(lines)
                await interaction.response.send_message("✅ | Cookies updated securely!", ephemeral=True)
            except Exception as e:
                await interaction.response.send_message(f"⚠️ | Updated memory, but failed to save to .env: {e}", ephemeral=True)

        elif cmd == "cashout":
            if target is None or amount is None:
                await interaction.response.send_message("❌ | Missing 'target' or 'amount'.", ephemeral=True)
                return
            
            discord_id = self._resolve_target(target)
            if discord_id is None:
                await interaction.response.send_message(f"❌ | Could not find user '{target}'.", ephemeral=True)
                return
            
            linked = get_linked_users()
            user_data = linked.get(discord_id)
            if not user_data:
                await interaction.response.send_message(f"❌ | User {discord_id} is not linked to a Prism account.", ephemeral=True)
                return
            
            prism_username = user_data["prism_username"]
            
            await interaction.response.defer(ephemeral=True)
            
            from database import deduct_balance_if_sufficient
            if not await deduct_balance_if_sufficient(int(discord_id), amount):
                await interaction.followup.send(f"❌ | User does not have enough balance to cash out **${amount}**.", ephemeral=True)
                return
            
            success = await self._do_transfer(prism_username, amount)
            
            if success:
                await interaction.followup.send(f"✅ | Force cashout: Sent **${amount}** to **{prism_username}** on XPrism.", ephemeral=True)
                await log_event(self.bot, f"Admin force-cashout: ${amount} to {prism_username} (Discord: {discord_id})")
            else:
                await update_balance(int(discord_id), amount)
                await interaction.followup.send(f"❌ | Transfer API failed! Balance refunded. Check cookies.", ephemeral=True)

        elif cmd in ("cashout_approve", "cashout_deny"):
            if target is None:
                await interaction.response.send_message("❌ | Missing 'target' (Cashout ID number).", ephemeral=True)
                return
            try:
                cashout_id = int(target.strip())
            except ValueError:
                await interaction.response.send_message("❌ | Target must be a cashout ID number (e.g. `5`).", ephemeral=True)
                return
            
            await interaction.response.defer(ephemeral=True)
            from cogs.cashout import process_cashout_action
            action_type = "approve" if cmd == "cashout_approve" else "deny"
            success, message = await process_cashout_action(self.bot, cashout_id, action_type)
            await interaction.followup.send(message, ephemeral=True)

        elif cmd == "cashout_pending":
            from database import get_pending_cashouts
            pending = await get_pending_cashouts()
            if not pending:
                await interaction.response.send_message("✅ | No pending cashout requests.", ephemeral=True)
                return
            lines = []
            for row in pending:
                cid, uid, prism_user, amt = row
                lines.append(f"**#{cid}** — <@{uid}> → `{prism_user}` — **${amt:,}**")
            desc = "\n".join(lines)
            if len(desc) > 1900:
                desc = desc[:1900] + "\n..."
            embed = discord.Embed(title="⏳ Pending Cashouts", description=desc, color=discord.Color.orange())
            await interaction.response.send_message(embed=embed, ephemeral=True)

        elif cmd == "cashoutchannel":
            if channel is None:
                await interaction.response.send_message("❌ | Missing 'channel'.", ephemeral=True)
                return
            config = get_config()
            config["cashout_channel_id"] = channel.id
            save_config(config)
            await interaction.response.send_message(f"✅ | Cashout channel has been set to {channel.mention}!", ephemeral=True)
            await log_event(self.bot, f"Admin configured cashout channel to {channel.id}")

        elif cmd == "stats":
            stats = await get_casino_stats()
            games = stats["games_played"]
            wins = stats["games_won"]
            losses = stats["games_lost"]
            winrate = (wins / games * 100) if games > 0 else 0
            
            embed = discord.Embed(title="🏛️ Casino Stats", color=discord.Color.gold())
            embed.add_field(name="Total Wagered", value=f"${stats['total_wagered']:,}", inline=True)
            embed.add_field(name="Casino Profit", value=f"${stats['total_won']:,}", inline=True)
            embed.add_field(name="Casino Losses", value=f"${stats['total_lost']:,}", inline=True)
            embed.add_field(name="Games Played", value=f"{games:,}", inline=True)
            embed.add_field(name="House Wins", value=f"{wins:,}", inline=True)
            embed.add_field(name="House Losses", value=f"{losses:,}", inline=True)
            net = stats['total_won'] - stats['total_lost']
            embed.add_field(name="Net Profit", value=f"${net:,}", inline=True)
            embed.add_field(name="House Win Rate", value=f"{winrate:.1f}%", inline=True)
            
            await interaction.response.send_message(embed=embed, ephemeral=True)

        elif cmd == "setstats":
            if game is None or amount is None:
                await interaction.response.send_message(
                    "❌ | Missing parameters.\n"
                    "Use `game` for field name: `total_wagered`, `total_won`, `total_lost`, `games_played`, `games_won`, `games_lost`\n"
                    "Use `amount` for the value.",
                    ephemeral=True
                )
                return
            
            field = game.lower().strip()
            success = await set_casino_stat(field, amount)
            if success:
                await interaction.response.send_message(f"✅ | Casino stat `{field}` set to **{amount}**.", ephemeral=True)
                await log_event(self.bot, f"Admin set casino stat {field} to {amount}")
            else:
                await interaction.response.send_message(
                    f"❌ | Invalid field `{field}`.\n"
                    "Valid: `total_wagered`, `total_won`, `total_lost`, `games_played`, `games_won`, `games_lost`",
                    ephemeral=True
                )

        elif cmd == "l_start":
            if amount is None:
                await interaction.response.send_message("❌ | Missing 'amount' for starting fund.", ephemeral=True)
                return
            
            active = await get_active_lottery()
            if active and active["is_active"]:
                await interaction.response.send_message("❌ | A lottery is already active! Draw it first.", ephemeral=True)
                return
            
            ticket_price = max(1, amount // 5000)
            await start_lottery(amount, ticket_price)
            await interaction.response.send_message(f"✅ | Lottery started with **${amount:,}** pool! Ticket price: **${ticket_price:,}**.", ephemeral=False)
            await log_event(self.bot, f"Admin started lottery with ${amount} (ticket: ${ticket_price})")

        elif cmd in ["l_draw", "l_rig"]:
            import random
            import asyncio
            
            active = await get_active_lottery()
            if not active or not active["is_active"]:
                await interaction.response.send_message("❌ | No active lottery to draw.", ephemeral=True)
                return
            
            if cmd == "l_rig":
                if target is None:
                    await interaction.response.send_message("❌ | Missing 'target'. Pass 5 numbers like '1 2 3 4 5'.", ephemeral=True)
                    return
                try:
                    winning_numbers = sorted([int(x) for x in target.strip().split()][:5])
                    if len(winning_numbers) != 5:
                        raise ValueError
                except:
                    await interaction.response.send_message("❌ | Invalid target form. Pass 5 numbers e.g. '1 2 3 4 5'", ephemeral=True)
                    return
            else:
                winning_numbers = sorted(random.sample(range(1, 51), 5))

            winning_set = set(winning_numbers)

            embed = discord.Embed(title="🎟️ Lottery Draw", color=discord.Color.blue())
            embed.description = "🎰 **Initializing Lottery Machine...**\n*The suspense is building!*"
            await interaction.response.send_message(embed=embed, ephemeral=False)
            
            drawn_str = ""
            for i, num in enumerate(winning_numbers):
                embed.description = f"🎰 **Drawn:** `{drawn_str}`\n\nDrawing number {i+1}..." if drawn_str else f"🎰 **Drawing number {i+1}...**"
                try:
                    await interaction.edit_original_response(embed=embed)
                except discord.errors.NotFound:
                    pass
                    
                await asyncio.sleep(10.0)
                
                if drawn_str:
                    drawn_str += " "
                drawn_str += f"{str(num)}"
                
            embed.description = f"🎰 **Final Numbers:** `{drawn_str}`\n\nCalculating winners..."
            try:
                await interaction.edit_original_response(embed=embed)
            except discord.errors.NotFound:
                pass
            
            pool = active["current_pool"]
            
            bot_cut = 0
            remaining = pool
            if remaining > 10000000:
                bot_cut += int((remaining - 10000000) * 0.05)
                remaining = 10000000
            if remaining > 1000000:
                bot_cut += int((remaining - 1000000) * 0.10)
                remaining = 1000000
            bot_cut += int(remaining * 0.15)
                
            net_pool = pool - bot_cut
            
            tickets = await get_all_tickets()
            winners = []
            
            for t in tickets:
                user_id, n1, n2, n3, n4, n5 = t
                t_set = {n1, n2, n3, n4, n5}
                if t_set == winning_set:
                    winners.append(user_id)
            
            await clear_all_tickets()
            
            win_str = f"**Winning Numbers:** `{' '.join(map(str, winning_numbers))}`\n\n"
            
            if winners:
                per_winner = net_pool // len(winners)
                for w in winners:
                    await update_balance(w, per_winner)
                await end_lottery_active()
                win_str += f"🎉 **{len(winners)} Winner(s)!** They each won **${per_winner:,}**!\nBot took `${bot_cut:,}`."
                await log_event(self.bot, f"Lottery Draw: WON by {len(winners)}. Payout ${per_winner} each. Bot Cut: ${bot_cut}")
            else:
                win_str += f"😢 **No Winners!** The pool of **${pool:,}** rolls over to the next draw!"
                await log_event(self.bot, f"Lottery Draw: No Winners. Rollover pool: ${pool}")
                
            embed.color = discord.Color.gold()
            embed.description = win_str
            try:
                await interaction.edit_original_response(embed=embed)
            except discord.errors.NotFound:
                pass

    async def _do_transfer(self, recipient_username: str, amount: int) -> bool:
        """Call the XPrism transfer API to send cash."""
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
                async with session.post("https://xprismplay.dpdns.org/api/transfer", headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        return True
                    else:
                        print(f"[CASHOUT ERROR] Transfer API returned {resp.status}: {await resp.text()}")
                        return False
        except Exception as e:
            print(f"[CASHOUT ERROR] Transfer failed: {e}")
            return False

async def setup(bot):
    await bot.add_cog(Debug(bot))