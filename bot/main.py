# Bot entry point
import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv
import os

load_dotenv()

from bot.handlers import start, wallet, number, orders, services, admin
from bot.utils.smsman_client import SMSManClient
from models.database import DatabaseManager

# Initialize
bot = Bot(token=os.getenv('BOT_TOKEN'))
dp = Dispatcher(storage=MemoryStorage())
db_manager = DatabaseManager(os.getenv('DATABASE_URL'))
sms_client = SMSManClient(token=os.getenv('SMS_MAN_TOKEN'))

# Create tables
db_manager.create_tables()

# Register handlers
dp.include_router(start.router)
dp.include_router(wallet.router)
dp.include_router(number.router)
dp.include_router(orders.router)

async def main():
    await bot.set_my_commands([
        ("start", "Start bot"),
        ("balance", "Check balance"),
        ("orders", "My orders")
    ])
    
    print("🚀 Bot started!")
    await dp.start_polling(bot, sms_client=sms_client, db_manager=db_manager)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
