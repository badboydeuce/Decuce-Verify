import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from config import settings
from bot.handlers import start, wallet, activation, rental, orders, admin
from database.db import init_db

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize bot and dispatcher
bot = Bot(token=settings.bot_token, parse_mode=ParseMode.HTML)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

async def main():
    """Main bot entry point"""
    # Initialize database
    init_db()
    logger.info("Database initialized")
    
    # Register routers
    dp.include_router(start.router)
    dp.include_router(wallet.router)
    dp.include_router(activation.router)
    dp.include_router(rental.router)
    dp.include_router(orders.router)
    dp.include_router(admin.router)
    
    # Start polling
    logger.info("Starting bot...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
