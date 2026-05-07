"""
DeuceVerify - Main Telegram Bot
Aiogram 3.x based bot for virtual number SMS verification
"""

import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand

from config import settings
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

async def set_bot_commands():
    """Set bot commands for menu"""
    commands = [
        BotCommand(command="start", description="🚀 Start the bot"),
        BotCommand(command="help", description="❓ Help and information"),
        BotCommand(command="balance", description="💰 Check your balance"),
        BotCommand(command="orders", description="📋 View your orders"),
        BotCommand(command="profile", description="👤 View your profile"),
    ]
    await bot.set_my_commands(commands)

async def register_handlers():
    """Register all handlers dynamically"""
    try:
        from bot.handlers.start import router as start_router
        from bot.handlers.wallet import router as wallet_router
        from bot.handlers.activation import router as activation_router
        from bot.handlers.rental import router as rental_router
        from bot.handlers.orders import router as orders_router
        from bot.handlers.admin import router as admin_router
        
        dp.include_router(start_router)
        dp.include_router(wallet_router)
        dp.include_router(activation_router)
        dp.include_router(rental_router)
        dp.include_router(orders_router)
        dp.include_router(admin_router)
        
        logger.info("✅ All handlers registered successfully")
    except Exception as e:
        logger.error(f"Failed to register handlers: {e}")
        raise

async def main():
    """Main bot entry point"""
    logger.info("🚀 Starting DeuceVerify Bot...")
    
    try:
        # Initialize database
        init_db()
        logger.info("✅ Database initialized")
        
        # Set bot commands
        await set_bot_commands()
        logger.info("✅ Bot commands set")
        
        # Register handlers
        await register_handlers()
        
        # Start polling
        logger.info("🤖 Bot is running and polling for updates...")
        await dp.start_polling(bot)
        
    except Exception as e:
        logger.error(f"❌ Bot failed to start: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
