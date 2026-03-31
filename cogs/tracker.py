import discord
from discord.ext import commands, tasks
import aiohttp
import json
import os
import time
import datetime
from database import update_balance
from cogs.linker import get_linked_users
from logger import log_event

API_URL = "https://xprismplay.dpdns.org/api/transactions?type=TRANSFER_IN"
TRACKED_FILE = "tracked_tx.json"
CUTOFF_DATE = datetime.datetime.fromisoformat("2026-03-27T22:49:40.440Z".replace('Z', '+00:00'))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Priority": "u=0, i"
}

class Tracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.session_cookie = os.getenv("COOKIE_SESSION", "")
        self.clearance_cookie = os.getenv("COOKIE_CLEARANCE", "")
        
        self.cookies = {
            "__Secure-better-auth.session_token": self.session_cookie,
            "cf_clearance": self.clearance_cookie
        }
        
        self.seen_tx_ids = set()
        self._load_tracked()
        self.monitor_deposits.start()

    def _load_tracked(self):
        if os.path.exists(TRACKED_FILE):
            with open(TRACKED_FILE, "r") as f:
                try:
                    data = json.load(f)
                    self.seen_tx_ids = set(data)
                except Exception:
                    self.seen_tx_ids = set()

    def _save_tracked(self):
        with open(TRACKED_FILE, "w") as f:
            json.dump(list(self.seen_tx_ids), f)

    def cog_unload(self):
        self.monitor_deposits.cancel()

    @tasks.loop(seconds=10.0)
    async def monitor_deposits(self):
        try:
            async with aiohttp.ClientSession(cookies=self.cookies) as session:
                async with session.get(API_URL, headers=HEADERS, timeout=10) as response:
                    if response.status in (401, 403):
                        print(f"[TRACKER ERROR] Authentication Failed. Your cookies might be expired. ({response.status})")
                        return
                    response.raise_for_status()
                    data = await response.json()

            transactions = data.get("transactions", data.get("data", []))

            linked = get_linked_users()
            username_to_discord = {v["prism_username"].lower(): k for k, v in linked.items()}

            new_txs = False
            for tx in transactions:
                tx_id = tx.get("id")

                if tx_id and tx_id not in self.seen_tx_ids:
                    self.seen_tx_ids.add(tx_id)
                    new_txs = True
                    
                    created_at_str = tx.get("createdAt", "")
                    try:
                        tx_date = datetime.datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                        if tx_date < CUTOFF_DATE:
                            continue
                    except ValueError:
                        pass
                        
                    is_coin = tx.get("isCoinTransfer", False)
                    if is_coin:
                        continue
                    
                    sender_data = tx.get("senderUser") or {}
                    sender = sender_data.get("username") or tx.get("sender") or tx.get("from") or "Unknown"

                    raw_amount = tx.get("totalBaseCurrencyAmount") or 0
                    try:
                        amount = int(float(raw_amount))
                    except (ValueError, TypeError):
                        continue
                    
                    if amount > 0:
                        sender_lower = sender.lower()
                        if sender_lower in username_to_discord:
                            discord_id = int(username_to_discord[sender_lower])
                            await update_balance(discord_id, int(amount))
                            print(f"[TRACKER] Credited ${amount} to {sender} (Discord: {discord_id}) for TX {tx_id}")
                            await log_event(self.bot, f"Tracker deposited ${amount} to {sender}")
                        else:
                            print(f"[TRACKER] Unlinked deposit: {amount} from {sender} (TX: {tx_id})")

            if new_txs:
                self._save_tracked()

        except aiohttp.ClientResponseError as e:
            print(f"[TRACKER ERROR] Tracking HTTP Error: {e.status} {e.message}")
        except Exception as e:
            print(f"[TRACKER ERROR] Failed to fetch transactions: {e}")

    @monitor_deposits.before_loop
    async def before_monitor(self):
        print("[TRACKER] Waiting for bot to be ready...")
        await self.bot.wait_until_ready()
        print("[TRACKER] Monitor started.")

async def setup(bot):
    await bot.add_cog(Tracker(bot))