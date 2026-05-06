"""
Helper functions for bot notifications
"""

import asyncio
import os
from loguru import logger

async def send_balance_update(telegram_id: int, amount: float, new_balance: float):
    """Send balance update notification to user"""
    try:
        from aiogram import Bot
        bot = Bot(token=os.getenv('BOT_TOKEN'))
        
        message = (
            f"✅ <b>Payment Received!</b>\n\n"
            f"Amount added: <b>${amount:.2f}</b>\n"
            f"New balance: <b>${new_balance:.2f}</b>\n\n"
            f"Thank you for funding your wallet!"
        )
        
        await bot.send_message(telegram_id, message)
        await bot.session.close()
        
    except Exception as e:
        logger.error(f"Failed to send balance update to {telegram_id}: {e}")

def send_balance_update_sync(telegram_id: int, amount: float, new_balance: float):
    """Sync wrapper for async function"""
    asyncio.create_task(send_balance_update(telegram_id, amount, new_balance))

async def send_payment_failed_notification(telegram_id: int, method: str):
    """Send payment failed notification"""
    try:
        from aiogram import Bot
        bot = Bot(token=os.getenv('BOT_TOKEN'))
        
        message = (
            f"❌ <b>Payment Failed</b>\n\n"
            f"Payment method: {method}\n\n"
            f"Please try again or contact support."
        )
        
        await bot.send_message(telegram_id, message)
        await bot.session.close()
        
    except Exception as e:
        logger.error(f"Failed to send payment failed notification: {e}")

async def notify_admin(message: str):
    """Send notification to all admins"""
    admin_ids = os.getenv('ADMIN_IDS', '').split(',')
    
    try:
        from aiogram import Bot
        bot = Bot(token=os.getenv('BOT_TOKEN'))
        
        for admin_id in admin_ids:
            if admin_id.strip():
                await bot.send_message(int(admin_id), f"🔔 <b>Admin Alert</b>\n\n{message}")
        
        await bot.session.close()
        
    except Exception as e:
        logger.error(f"Failed to send admin notification: {e}")
