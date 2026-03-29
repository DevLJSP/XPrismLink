import asyncio
from database import update_balance, get_balance, init_db
import aiosqlite

async def main():
    await init_db()
    bal = await get_balance(9999)
    print("Initial bal:", bal)
    await update_balance(9999, 100)
    bal = await get_balance(9999)
    print("After +100:", bal)

asyncio.run(main())
