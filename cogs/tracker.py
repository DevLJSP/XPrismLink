import discord
from discord.ext import commands, tasks
import aiohttp
import json
import os
import asyncio
import datetime

from database import update_balance
from cogs.linker import get_linked_users
from logger import log_event

API_URL = "https://xprismplay.dpdns.org/api/transactions?type=TRANSFER_IN"
TRACKED_FILE = "tracked_tx.json"
CUTOFF_DATE = datetime.datetime.fromisoformat("2026-03-27T22:49:40.440Z".replace("Z", "+00:00"))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Priority": "u=0, i",
}


class Tracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session_cookie = os.getenv("COOKIE_SESSION", "")
        self.clearance_cookie = os.getenv("COOKIE_CLEARANCE", "")
        self.cookies = {
            "__Secure-better-auth.session_token": self.session_cookie,
            "cf_clearance": self.clearance_cookie,
        }
        self.seen_tx_ids = set()
        self._lock = asyncio.Lock()
        self._load_tracked()
        self.monitor_deposits.start()

    def _load_tracked(self):
        if os.path.exists(TRACKED_FILE):
            try:
                with open(TRACKED_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.seen_tx_ids = set(data if isinstance(data, list) else [])
            except Exception:
                self.seen_tx_ids = set()

    def _save_tracked(self):
        try:
            with open(TRACKED_FILE, "w", encoding="utf-8") as f:
                json.dump(list(self.seen_tx_ids), f)
        except Exception as e:
            print(f"[TRACKER ERROR] Failed to save tracked transactions: {e}")

    def cog_unload(self):
        self.monitor_deposits.cancel()

    def build_transaction_embed(
        self,
        *,
        kind: str,
        amount: int,
        tx_id: str | None = None,
        wallet_name: str = "Casino Wallet",
    ) -> discord.Embed:
        kind = kind.lower().strip()

        if kind == "deposit":
            title = "Deposit Received"
            description = (
                f"Your deposit of **${amount:,}** has been successfully received "
                f"and credited to your wallet."
            )
            color = discord.Color.green()
            icon = "✅"
            status_text = "Completed"
        elif kind == "cashout":
            title = "Cashout Completed"
            description = (
                f"Your cashout of **${amount:,}** has been processed successfully "
                f"and sent to your linked account."
            )
            color = discord.Color.gold()
            icon = "💸"
            status_text = "Completed"
        else:
            title = "Transaction Update"
            description = f"A transaction of **${amount:,}** has been processed."
            color = discord.Color.blurple()
            icon = "🔔"
            status_text = "Updated"

        embed = discord.Embed(
            title=f"{icon} {title}",
            description=description,
            color=color,
            timestamp=discord.utils.utcnow(),
        )

        embed.add_field(name="Amount", value=f"**${amount:,}**", inline=True)
        embed.add_field(name="Status", value=f"**{status_text}**", inline=True)
        embed.add_field(name="Wallet", value=f"**{wallet_name}**", inline=True)

        if tx_id:
            embed.add_field(name="Transaction ID", value=f"`{tx_id}`", inline=False)

        embed.set_footer(text="xprismplay.dpdns.org")
        return embed

    async def notify_user(self, discord_id: int, *, kind: str, amount: int, tx_id: str | None = None):
        try:
            user = self.bot.get_user(discord_id) or await self.bot.fetch_user(discord_id)
            if not user:
                return

            embed = self.build_transaction_embed(
                kind=kind,
                amount=amount,
                tx_id=tx_id,
            )
            await user.send(embed=embed)
        except Exception as e:
            print(f"[TRACKER ERROR] Failed to DM user {discord_id}: {e}")

    @tasks.loop(seconds=10.0)
    async def monitor_deposits(self):
        if self._lock.locked():
            return

        async with self._lock:
            try:
                async with aiohttp.ClientSession(cookies=self.cookies) as session:
                    async with session.get(
                        API_URL,
                        headers=HEADERS,
                        timeout=aiohttp.ClientTimeout(total=10),
                    ) as response:
                        if response.status in (401, 403):
                            print(f"[TRACKER ERROR] Authentication failed. Cookies may be expired. ({response.status})")
                            return

                        response.raise_for_status()
                        data = await response.json()

                transactions = data.get("transactions", data.get("data", []))
                linked = get_linked_users()
                username_to_discord = {
                    v["prism_username"].lower(): int(k)
                    for k, v in linked.items()
                    if isinstance(v, dict) and v.get("prism_username")
                }

                for tx in transactions:
                    tx_id = tx.get("id")
                    if not tx_id or tx_id in self.seen_tx_ids:
                        continue

                    created_at_str = tx.get("createdAt", "")
                    try:
                        tx_date = datetime.datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                        if tx_date < CUTOFF_DATE:
                            self.seen_tx_ids.add(tx_id)
                            continue
                    except ValueError:
                        pass

                    if tx.get("isCoinTransfer", False):
                        self.seen_tx_ids.add(tx_id)
                        continue

                    sender_data = tx.get("senderUser") or {}
                    sender = sender_data.get("username") or tx.get("sender") or tx.get("from") or "Unknown"

                    raw_amount = tx.get("totalBaseCurrencyAmount") or 0
                    try:
                        amount = int(float(raw_amount))
                    except (ValueError, TypeError):
                        self.seen_tx_ids.add(tx_id)
                        self._save_tracked()
                        continue

                    if amount <= 0:
                        self.seen_tx_ids.add(tx_id)
                        self._save_tracked()
                        continue

                    self.seen_tx_ids.add(tx_id)
                    self._save_tracked()

                    sender_lower = str(sender).lower()

                    if sender_lower in username_to_discord:
                        discord_id = username_to_discord[sender_lower]

                        await update_balance(discord_id, amount)
                        print(f"[TRACKER] Credited ${amount} to {sender} (Discord: {discord_id}) for TX {tx_id}")

                        await log_event(self.bot, f"Deposit credited: ${amount} to {sender} (Discord ID: {discord_id})")

                        await self.notify_user(
                            discord_id,
                            kind="deposit",
                            amount=amount,
                            tx_id=tx_id,
                        )
                    else:
                        print(f"[TRACKER] Unlinked deposit: ${amount} from {sender} (TX: {tx_id})")

            except aiohttp.ClientResponseError as e:
                print(f"[TRACKER ERROR] HTTP error: {e.status} {e.message}")
            except Exception as e:
                print(f"[TRACKER ERROR] Failed to fetch transactions: {e}")

    @monitor_deposits.before_loop
    async def before_monitor(self):
        print("[TRACKER] Waiting for bot to be ready...")
        await self.bot.wait_until_ready()
        print("[TRACKER] Monitor started.")


async def setup(bot):
    await bot.add_cog(Tracker(bot))