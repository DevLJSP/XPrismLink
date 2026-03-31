import aiosqlite
import discord

DB_NAME = "economy.db"

async def init_db():
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                balance INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER PRIMARY KEY,
                total_wagered INTEGER DEFAULT 0,
                total_won INTEGER DEFAULT 0,
                total_lost INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0,
                games_won INTEGER DEFAULT 0,
                games_lost INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS casino_stats (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                total_wagered INTEGER DEFAULT 0,
                total_won INTEGER DEFAULT 0,
                total_lost INTEGER DEFAULT 0,
                games_played INTEGER DEFAULT 0,
                games_won INTEGER DEFAULT 0,
                games_lost INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            INSERT OR IGNORE INTO casino_stats (id) VALUES (1)
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS lotteries (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                is_active BOOLEAN DEFAULT 0,
                starting_fund INTEGER DEFAULT 0,
                current_pool INTEGER DEFAULT 0,
                ticket_price INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS lottery_tickets (
                ticket_id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                n1 INTEGER,
                n2 INTEGER,
                n3 INTEGER,
                n4 INTEGER,
                n5 INTEGER
            )
        """)
        await db.execute("INSERT OR IGNORE INTO lotteries (id, is_active) VALUES (1, 0)")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS cashout_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                prism_username TEXT NOT NULL,
                amount INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                message_id INTEGER DEFAULT NULL,
                channel_id INTEGER DEFAULT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def get_balance(user_id):
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
            result = await cursor.fetchone()
            if result:
                return result[0]
            else:
                await db.execute("INSERT INTO users (user_id, balance) VALUES (?, ?)", (user_id, 0))
                await db.commit()
                return 0

async def update_balance(user_id, amount):
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        await get_balance(user_id)
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def set_balance(user_id, amount):
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        await get_balance(user_id)
        await db.execute("UPDATE users SET balance = ? WHERE user_id = ?", (amount, user_id))
        await db.commit()

async def deduct_balance_if_sufficient(user_id: int, amount: int) -> bool:
    """Atomically check if a user has enough balance and deduct it if so."""
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        await db.execute("BEGIN IMMEDIATE")
        
        await db.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, ?)", (user_id, 0))
        
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            current_bal = row[0]
            
        if current_bal < amount:
            await db.rollback()
            return False
            
        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        await db.commit()
        return True

async def get_top_stats(stat_type="balance", limit=10):
    valid_stats = ["total_wagered", "total_won", "total_lost", "games_played", "games_won", "games_lost"]
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        if stat_type == "balance":
            async with db.execute("SELECT user_id, balance FROM users ORDER BY balance DESC LIMIT ?", (limit,)) as cursor:
                return await cursor.fetchall()
        elif stat_type in valid_stats:
            async with db.execute(f"SELECT user_id, {stat_type} FROM user_stats ORDER BY {stat_type} DESC LIMIT ?", (limit,)) as cursor:
                return await cursor.fetchall()
        return []

async def process_bet(interaction: discord.Interaction, amount: int) -> bool:
    from cogs.linker import is_linked
    user_id = interaction.user.id
    if not is_linked(user_id):
        msg = "❌ | You must link your Prism account first! Use `/link`."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
        return False

    if amount <= 0:
        msg = "❌ | Bet must be greater than $0."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
        return False
        
    if amount > 5000:
        msg = "❌ | The maximum bet is **$5000**."
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
        return False

    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        await db.execute("BEGIN IMMEDIATE")
        
        await db.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, ?)", (user_id, 0))
        
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            current_bal = row[0]
            
        if current_bal < amount:
            await db.rollback()
            deposit_msg = (
                f"❌ | You only have **${current_bal}**!"
                f"\n\n💰 To deposit, send money to **brazil** on XPrism:"
                f"\nhttps://xprismplay.dpdns.org/user/brazil"
            )
            if interaction.response.is_done():
                await interaction.followup.send(deposit_msg, ephemeral=True)
            else:
                await interaction.response.send_message(deposit_msg, ephemeral=True)
            return False
            
        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, user_id))
        await db.commit()
        return True

# ─── Stats Functions ───

async def record_game(user_id, wagered, net_result, won: bool):
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        await db.execute("INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)", (user_id,))
        
        if won:
            await db.execute("""
                UPDATE user_stats SET 
                    total_wagered = total_wagered + ?,
                    total_won = total_won + ?,
                    games_played = games_played + 1,
                    games_won = games_won + 1
                WHERE user_id = ?
            """, (wagered, net_result, user_id))
            await db.execute("""
                UPDATE casino_stats SET
                    total_wagered = total_wagered + ?,
                    total_lost = total_lost + ?,
                    games_played = games_played + 1,
                    games_lost = games_lost + 1
                WHERE id = 1
            """, (wagered, net_result))
        else:
            loss = abs(net_result)
            await db.execute("""
                UPDATE user_stats SET
                    total_wagered = total_wagered + ?,
                    total_lost = total_lost + ?,
                    games_played = games_played + 1,
                    games_lost = games_lost + 1
                WHERE user_id = ?
            """, (wagered, loss, user_id))
            await db.execute("""
                UPDATE casino_stats SET
                    total_wagered = total_wagered + ?,
                    total_won = total_won + ?,
                    games_played = games_played + 1,
                    games_won = games_won + 1
                WHERE id = 1
            """, (wagered, loss))
        
        await db.commit()

async def get_user_stats(user_id):
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        await db.execute("INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)", (user_id,))
        await db.commit()
        async with db.execute("SELECT total_wagered, total_won, total_lost, games_played, games_won, games_lost FROM user_stats WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return {
                "total_wagered": row[0],
                "total_won": row[1],
                "total_lost": row[2],
                "games_played": row[3],
                "games_won": row[4],
                "games_lost": row[5]
            }

async def get_casino_stats():
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        await db.execute("INSERT OR IGNORE INTO casino_stats (id) VALUES (1)")
        await db.commit()
        async with db.execute("SELECT total_wagered, total_won, total_lost, games_played, games_won, games_lost FROM casino_stats WHERE id = 1") as cursor:
            row = await cursor.fetchone()
            return {
                "total_wagered": row[0],
                "total_won": row[1],
                "total_lost": row[2],
                "games_played": row[3],
                "games_won": row[4],
                "games_lost": row[5]
            }

async def set_casino_stat(field, value):
    valid_fields = ["total_wagered", "total_won", "total_lost", "games_played", "games_won", "games_lost"]
    if field not in valid_fields:
        return False
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        await db.execute(f"UPDATE casino_stats SET {field} = ? WHERE id = 1", (value,))
        await db.commit()
        return True

# ─── Lottery Functions ───

async def get_active_lottery():
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        async with db.execute("SELECT is_active, starting_fund, current_pool, ticket_price FROM lotteries WHERE id = 1") as cursor:
            row = await cursor.fetchone()
            if row and row[0]:
                return {"is_active": True, "starting_fund": row[1], "current_pool": row[2], "ticket_price": row[3]}
            return None

async def start_lottery(starting_fund, ticket_price):
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        await db.execute("""
            UPDATE lotteries 
            SET is_active = 1, starting_fund = ?, current_pool = ?, ticket_price = ? 
            WHERE id = 1
        """, (starting_fund, starting_fund, ticket_price))
        await db.commit()

async def end_lottery_active():
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        await db.execute("UPDATE lotteries SET is_active = 0 WHERE id = 1")
        await db.commit()

async def add_lottery_pool(amount):
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        await db.execute("UPDATE lotteries SET current_pool = current_pool + ? WHERE id = 1", (amount,))
        await db.commit()

async def buy_lottery_ticket(user_id, n1, n2, n3, n4, n5):
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        await db.execute("""
            INSERT INTO lottery_tickets (user_id, n1, n2, n3, n4, n5) 
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, n1, n2, n3, n4, n5))
        await db.commit()

async def get_all_tickets():
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        async with db.execute("SELECT user_id, n1, n2, n3, n4, n5 FROM lottery_tickets") as cursor:
            return await cursor.fetchall()

async def clear_all_tickets():
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        await db.execute("DELETE FROM lottery_tickets")
        await db.commit()

# ─── Cashout Functions ───

async def create_cashout_request(user_id: int, prism_username: str, amount: int) -> int:
    """Create a cashout request and return its ID."""
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        cursor = await db.execute(
            "INSERT INTO cashout_requests (user_id, prism_username, amount) VALUES (?, ?, ?)",
            (user_id, prism_username, amount)
        )
        await db.commit()
        return cursor.lastrowid

async def get_cashout_request(cashout_id: int):
    """Get a cashout request by ID. Returns dict or None."""
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        async with db.execute(
            "SELECT id, user_id, prism_username, amount, status, message_id, channel_id FROM cashout_requests WHERE id = ?",
            (cashout_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return {
                "id": row[0], "user_id": row[1], "prism_username": row[2],
                "amount": row[3], "status": row[4], "message_id": row[5], "channel_id": row[6]
            }

async def update_cashout_status(cashout_id: int, status: str):
    """Update cashout status to 'approved' or 'denied'."""
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        await db.execute("UPDATE cashout_requests SET status = ? WHERE id = ?", (status, cashout_id))
        await db.commit()

async def update_cashout_message(cashout_id: int, message_id: int, channel_id: int):
    """Store the message/channel ID for the cashout notification."""
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        await db.execute(
            "UPDATE cashout_requests SET message_id = ?, channel_id = ? WHERE id = ?",
            (message_id, channel_id, cashout_id)
        )
        await db.commit()

async def get_pending_cashouts():
    """Get all pending cashout requests."""
    async with aiosqlite.connect(DB_NAME, timeout=20.0) as db:
        async with db.execute(
            "SELECT id, user_id, prism_username, amount FROM cashout_requests WHERE status = 'pending' ORDER BY id"
        ) as cursor:
            return await cursor.fetchall()