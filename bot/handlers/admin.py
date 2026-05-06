# Admin handler
"""
Admin commands for DeuceVerify
Admin-only functions: refunds, user management, system stats
"""

from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta
import os
from loguru import logger

router = Router()

# Admin check decorator
def admin_only(func):
    async def wrapper(message: Message, *args, **kwargs):
        admin_ids = os.getenv('ADMIN_IDS', '').split(',')
        if str(message.from_user.id) not in admin_ids:
            await message.answer("⛔ Access denied. Admin only.")
            return
        return await func(message, *args, **kwargs)
    return wrapper

class AdminStates(StatesGroup):
    waiting_refund_user_id = State()
    waiting_refund_order_id = State()
    waiting_manual_balance = State()
    waiting_broadcast = State()

# ==================== ADMIN MAIN MENU ====================

@router.message(Command("admin"))
@admin_only
async def admin_panel(message: Message):
    """Show admin panel"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Dashboard", callback_data="admin_dashboard"),
         InlineKeyboardButton(text="👥 Users", callback_data="admin_users")],
        [InlineKeyboardButton(text="📱 Orders", callback_data="admin_orders"),
         InlineKeyboardButton(text="💰 Refunds", callback_data="admin_refunds")],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast"),
         InlineKeyboardButton(text="📈 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton(text="⚙️ Settings", callback_data="admin_settings")]
    ])
    
    await message.answer(
        "🔐 <b>Admin Control Panel</b>\n\n"
        "Welcome to DeuceVerify Admin Panel.\n"
        "Select an option below:",
        reply_markup=keyboard
    )

# ==================== DASHBOARD ====================

@router.callback_query(F.data == "admin_dashboard")
async def admin_dashboard(callback: CallbackQuery, db_manager):
    """Show admin dashboard with stats"""
    session = db_manager.get_session()
    
    try:
        from models.database import User, Order, Transaction
        
        # Get stats
        total_users = session.query(User).count()
        active_users = session.query(User).filter(User.last_active >= datetime.utcnow() - timedelta(days=7)).count()
        total_orders = session.query(Order).count()
        active_orders = session.query(Order).filter(Order.status.in_(['active', 'pending'])).count()
        total_revenue = session.query(Transaction).filter(Transaction.type == 'debit', Transaction.status == 'completed').all()
        total_revenue_sum = sum(t.amount for t in total_revenue)
        
        # Recent activity
        recent_orders = session.query(Order).order_by(Order.created_at.desc()).limit(5).all()
        recent_users = session.query(User).order_by(User.created_at.desc()).limit(5).all()
        
        text = (
            "📊 <b>Admin Dashboard</b>\n\n"
            f"👥 <b>Users:</b>\n"
            f"  • Total: {total_users}\n"
            f"  • Active (7d): {active_users}\n\n"
            f"📱 <b>Orders:</b>\n"
            f"  • Total: {total_orders}\n"
            f"  • Active: {active_orders}\n\n"
            f"💰 <b>Revenue:</b>\n"
            f"  • Total: ${total_revenue_sum:.2f}\n\n"
            f"🔄 <b>Recent Orders:</b>\n"
        )
        
        for order in recent_orders:
            text += f"  • #{order.id} - {order.service_name} - ${order.cost:.2f}\n"
        
        text += f"\n👤 <b>Recent Users:</b>\n"
        for user in recent_users[:3]:
            text += f"  • {user.first_name or 'User'} - ${user.balance:.2f}\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data="admin_dashboard")],
            [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Admin dashboard error: {e}")
        await callback.message.edit_text("❌ Error loading dashboard")
    finally:
        session.close()

# Add this to admin.py for profit tracking

@router.callback_query(F.data == "admin_profit_analytics")
async def admin_profit_analytics(callback: CallbackQuery, db_manager):
    """Show profit analytics"""
    session = db_manager.get_session()
    
    try:
        from models.database import Order, Transaction
        from sqlalchemy import func
        
        # Calculate total profit
        orders = session.query(Order).filter(Order.status.in_(['received', 'active'])).all()
        total_revenue = sum(o.cost for o in orders)
        total_cost = sum(getattr(o, 'original_cost', o.cost / 2) for o in orders)
        total_profit = total_revenue - total_cost
        avg_profit_percent = (total_profit / total_cost * 100) if total_cost > 0 else 0
        
        # Profit by service
        profit_by_service = session.query(
            Order.service_name,
            func.sum(Order.cost).label('revenue'),
            func.sum(getattr(Order, 'original_cost', Order.cost / 2)).label('cost')
        ).group_by(Order.service_name).limit(10).all()
        
        text = (
            "💰 <b>Profit Analytics</b>\n\n"
            f"📊 <b>Overview</b>\n"
            f"├─ Total Orders: {len(orders)}\n"
            f"├─ Total Revenue: ${total_revenue:.2f}\n"
            f"├─ Total Cost: ${total_cost:.2f}\n"
            f"└─ <b>Total Profit: ${total_profit:.2f}</b>\n\n"
            f"📈 <b>Margin</b>\n"
            f"├─ Average Profit %: {avg_profit_percent:.1f}%\n"
            f"└─ Markup Multiplier: {sms_client.profit_margin}x\n\n"
            f"🏆 <b>Top Services by Profit</b>\n"
        )
        
        for service in profit_by_service[:5]:
            revenue = service[1] or 0
            cost = service[2] or 0
            profit = revenue - cost
            text += f"├─ {service[0]}: +${profit:.2f}\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Export Profit Report", callback_data="admin_export_profit")],
            [InlineKeyboardButton(text="⚙️ Adjust Markup", callback_data="admin_adjust_markup")],
            [InlineKeyboardButton(text="🔙 Back", callback_data="admin_back")]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Profit analytics error: {e}")
        await callback.message.edit_text("❌ Error loading profit data")
    finally:
        session.close()

# ==================== USER MANAGEMENT ====================

@router.callback_query(F.data == "admin_users")
async def admin_users(callback: CallbackQuery, db_manager):
    """Show user management panel"""
    session = db_manager.get_session()
    
    try:
        from models.database import User
        
        users = session.query(User).order_by(User.created_at.desc()).limit(20).all()
        
        text = "👥 <b>User Management</b>\n\n"
        
        for user in users[:10]:
            text += (
                f"┌ <b>ID:</b> {user.telegram_id}\n"
                f"├ @{user.username or 'no username'}\n"
                f"├ Balance: ${user.balance:.2f}\n"
                f"├ Orders: {user.total_orders}\n"
                f"└ Joined: {user.created_at.strftime('%Y-%m-%d')}\n\n"
            )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔍 Search User", callback_data="admin_search_user")],
            [InlineKeyboardButton(text="💰 Modify Balance", callback_data="admin_modify_balance")],
            [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Admin users error: {e}")
        await callback.message.edit_text("❌ Error loading users")
    finally:
        session.close()

@router.callback_query(F.data == "admin_modify_balance")
async def admin_modify_balance(callback: CallbackQuery, state: FSMContext):
    """Start balance modification flow"""
    await callback.message.answer(
        "💰 <b>Modify User Balance</b>\n\n"
        "Please enter the user's Telegram ID:\n\n"
        "Example: <code>123456789</code>\n\n"
        "Type /cancel to cancel.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="admin_back")]
        ])
    )
    await state.set_state(AdminStates.waiting_refund_user_id)

@router.message(AdminStates.waiting_refund_user_id)
async def get_user_for_balance(message: Message, state: FSMContext, db_manager):
    """Get user for balance modification"""
    try:
        telegram_id = int(message.text.strip())
        await state.update_data(target_user_id=telegram_id)
        
        session = db_manager.get_session()
        from models.database import User
        
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        session.close()
        
        if user:
            await message.answer(
                f"👤 User found: @{user.username or user.first_name}\n"
                f"Current balance: ${user.balance:.2f}\n\n"
                f"Enter the amount to ADD or SUBTRACT:\n"
                f"Example: <code>+50</code> to add $50\n"
                f"Example: <code>-20</code> to subtract $20\n\n"
                f"Or type /cancel to cancel."
            )
            await state.set_state(AdminStates.waiting_manual_balance)
        else:
            await message.answer("❌ User not found. Please try again.")
            await state.clear()
            
    except ValueError:
        await message.answer("❌ Invalid Telegram ID. Please enter a number.")

@router.message(AdminStates.waiting_manual_balance)
async def modify_balance(message: Message, state: FSMContext, db_manager):
    """Modify user balance"""
    try:
        amount_str = message.text.strip()
        
        if amount_str.startswith('+'):
            amount = float(amount_str[1:])
        elif amount_str.startswith('-'):
            amount = -float(amount_str[1:])
        else:
            amount = float(amount_str)
        
        user_data = await state.get_data()
        telegram_id = user_data.get('target_user_id')
        
        session = db_manager.get_session()
        from models.database import User, Transaction, TransactionType, TransactionStatus
        
        user = session.query(User).filter_by(telegram_id=telegram_id).first()
        
        if user:
            old_balance = user.balance
            user.balance += amount
            user.total_spent += amount if amount < 0 else 0
            
            # Create transaction record
            tx = Transaction(
                user_id=telegram_id,
                amount=abs(amount),
                type=TransactionType.CREDIT if amount > 0 else TransactionType.DEBIT,
                status=TransactionStatus.COMPLETED,
                payment_method="admin_manual",
                description=f"Manual adjustment by admin: {amount:+.2f}"
            )
            session.add(tx)
            session.commit()
            
            await message.answer(
                f"✅ Balance updated!\n\n"
                f"User: @{user.username or user.first_name}\n"
                f"Change: ${amount:+.2f}\n"
                f"Old balance: ${old_balance:.2f}\n"
                f"New balance: ${user.balance:.2f}"
            )
            
            # Notify user
            try:
                from aiogram import Bot
                bot = Bot(token=os.getenv('BOT_TOKEN'))
                await bot.send_message(
                    telegram_id,
                    f"🔔 <b>Balance Update</b>\n\n"
                    f"Your balance has been adjusted by an admin.\n"
                    f"Amount: ${amount:+.2f}\n"
                    f"New balance: ${user.balance:.2f}"
                )
                await bot.session.close()
            except Exception as e:
                logger.error(f"Failed to notify user: {e}")
        else:
            await message.answer("❌ User not found.")
        
        await state.clear()
        session.close()
        
    except ValueError:
        await message.answer("❌ Invalid amount. Please enter a number.")

# ==================== ORDER MANAGEMENT ====================

@router.callback_query(F.data == "admin_orders")
async def admin_orders(callback: CallbackQuery, db_manager):
    """Show order management panel"""
    session = db_manager.get_session()
    
    try:
        from models.database import Order
        
        # Get pending refund requests (expired orders)
        refund_requests = session.query(Order).filter(
            Order.status == 'expired',
            Order.expires_at < datetime.utcnow()
        ).limit(10).all()
        
        recent_orders = session.query(Order).order_by(Order.created_at.desc()).limit(10).all()
        
        text = "📱 <b>Order Management</b>\n\n"
        
        if refund_requests:
            text += "💰 <b>Pending Refund Requests:</b>\n"
            for order in refund_requests:
                text += f"  • #{order.id} - {order.service_name} - ${order.cost:.2f} - User: {order.user_id}\n"
            text += "\n"
        
        text += "📋 <b>Recent Orders:</b>\n"
        for order in recent_orders:
            text += f"  • #{order.id} - {order.service_name} - ${order.cost:.2f} - {order.status}\n"
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💰 Process Refund", callback_data="admin_refund_order")],
            [InlineKeyboardButton(text="🔍 Search Order", callback_data="admin_search_order")],
            [InlineKeyboardButton(text="📊 Export Orders", callback_data="admin_export_orders")],
            [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Admin orders error: {e}")
    finally:
        session.close()

@router.callback_query(F.data == "admin_refund_order")
async def admin_refund_order(callback: CallbackQuery, state: FSMContext):
    """Start refund process"""
    await callback.message.answer(
        "💰 <b>Process Refund</b>\n\n"
        "Enter the Order ID to refund:\n\n"
        "Example: <code>12345</code>\n\n"
        "Type /cancel to cancel.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="admin_back")]
        ])
    )
    await state.set_state(AdminStates.waiting_refund_order_id)

@router.message(AdminStates.waiting_refund_order_id)
async def process_refund(message: Message, state: FSMContext, db_manager):
    """Process refund for order"""
    try:
        order_id = int(message.text.strip())
        
        session = db_manager.get_session()
        from models.database import Order, OrderStatus, User, Transaction, TransactionType, TransactionStatus
        
        order = session.query(Order).filter_by(id=order_id).first()
        
        if not order:
            await message.answer(f"❌ Order #{order_id} not found.")
            await state.clear()
            return
        
        if order.status.value != 'expired' and not order.otp_code:
            await message.answer(
                f"⚠️ Order #{order_id} status: {order.status.value}\n"
                f"Refund only available for expired orders without OTP.\n\n"
                f"Continue anyway?"
            )
        
        # Process refund
        user = session.query(User).filter_by(telegram_id=order.user_id).first()
        
        if user:
            old_balance = user.balance
            user.balance += order.cost
            
            # Create refund transaction
            refund_tx = Transaction(
                user_id=order.user_id,
                amount=order.cost,
                type=TransactionType.CREDIT,
                status=TransactionStatus.COMPLETED,
                payment_method="admin_refund",
                description=f"Refund for order #{order_id}",
                order_id=order_id
            )
            session.add(refund_tx)
            
            # Update order
            order.status = OrderStatus.REFUNDED
            session.commit()
            
            await message.answer(
                f"✅ Refund processed!\n\n"
                f"Order #{order_id}\n"
                f"Amount: ${order.cost:.2f}\n"
                f"User: @{user.username or user.first_name}\n"
                f"New balance: ${user.balance:.2f}"
            )
            
            # Notify user
            try:
                from aiogram import Bot
                bot = Bot(token=os.getenv('BOT_TOKEN'))
                await bot.send_message(
                    order.user_id,
                    f"💰 <b>Refund Processed</b>\n\n"
                    f"Order #{order_id} has been refunded.\n"
                    f"Amount: <b>${order.cost:.2f}</b>\n"
                    f"New balance: <b>${user.balance:.2f}</b>\n\n"
                    f"Thank you for your patience!"
                )
                await bot.session.close()
            except Exception as e:
                logger.error(f"Failed to notify user: {e}")
        else:
            await message.answer(f"❌ User not found for order #{order_id}")
        
        await state.clear()
        session.close()
        
    except ValueError:
        await message.answer("❌ Invalid Order ID. Please enter a number.")

# ==================== BROADCAST ====================

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    """Start broadcast message"""
    await callback.message.answer(
        "📢 <b>Broadcast Message</b>\n\n"
        "Send the message you want to broadcast to all users.\n\n"
        "Supported: Text, emojis, HTML formatting.\n\n"
        "Type /cancel to cancel.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="admin_back")]
        ])
    )
    await state.set_state(AdminStates.waiting_broadcast)

@router.message(AdminStates.waiting_broadcast)
async def send_broadcast(message: Message, state: FSMContext, db_manager):
    """Send broadcast to all users"""
    broadcast_text = message.html_text
    
    await message.answer("⏳ Sending broadcast to all users... This may take a while.")
    
    session = db_manager.get_session()
    
    try:
        from models.database import User
        
        users = session.query(User).all()
        
        success_count = 0
        fail_count = 0
        
        from aiogram import Bot
        bot = Bot(token=os.getenv('BOT_TOKEN'))
        
        for user in users:
            try:
                await bot.send_message(
                    user.telegram_id,
                    f"📢 <b>Announcement from DeuceVerify</b>\n\n{broadcast_text}",
                    parse_mode="HTML"
                )
                success_count += 1
                await asyncio.sleep(0.05)  # Rate limiting
            except Exception as e:
                fail_count += 1
                logger.error(f"Failed to send to {user.telegram_id}: {e}")
        
        await bot.session.close()
        
        await message.answer(
            f"✅ Broadcast complete!\n\n"
            f"Sent: {success_count}\n"
            f"Failed: {fail_count}\n"
            f"Total users: {len(users)}"
        )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Broadcast error: {e}")
        await message.answer(f"❌ Broadcast error: {e}")
    finally:
        session.close()

# ==================== STATISTICS ====================

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery, db_manager):
    """Show detailed statistics"""
    session = db_manager.get_session()
    
    try:
        from models.database import User, Order, Transaction
        from sqlalchemy import func
        
        # Time periods
        today = datetime.utcnow().date()
        week_ago = datetime.utcnow() - timedelta(days=7)
        month_ago = datetime.utcnow() - timedelta(days=30)
        
        # User stats
        total_users = session.query(User).count()
        new_users_today = session.query(User).filter(func.date(User.created_at) == today).count()
        new_users_week = session.query(User).filter(User.created_at >= week_ago).count()
        
        # Order stats
        total_orders = session.query(Order).count()
        orders_today = session.query(Order).filter(func.date(Order.created_at) == today).count()
        completed_orders = session.query(Order).filter(Order.status == 'received').count()
        
        # Revenue stats
        total_revenue = session.query(Transaction).filter(Transaction.type == 'debit', Transaction.status == 'completed').all()
        total_revenue_sum = sum(t.amount for t in total_revenue)
        
        revenue_today = session.query(Transaction).filter(
            Transaction.type == 'debit',
            Transaction.status == 'completed',
            func.date(Transaction.created_at) == today
        ).all()
        revenue_today_sum = sum(t.amount for t in revenue_today)
        
        revenue_week = session.query(Transaction).filter(
            Transaction.type == 'debit',
            Transaction.status == 'completed',
            Transaction.created_at >= week_ago
        ).all()
        revenue_week_sum = sum(t.amount for t in revenue_week)
        
        text = (
            "📈 <b>DeuceVerify Statistics</b>\n\n"
            "👥 <b>Users</b>\n"
            f"  • Total: {total_users}\n"
            f"  • Today: +{new_users_today}\n"
            f"  • Week: +{new_users_week}\n\n"
            "📱 <b>Orders</b>\n"
            f"  • Total: {total_orders}\n"
            f"  • Today: {orders_today}\n"
            f"  • Completed: {completed_orders}\n\n"
            "💰 <b>Revenue</b>\n"
            f"  • Total: ${total_revenue_sum:.2f}\n"
            f"  • Today: ${revenue_today_sum:.2f}\n"
            f"  • Week: ${revenue_week_sum:.2f}\n\n"
            f"📊 <b>Success Rate:</b> {(completed_orders/total_orders*100 if total_orders > 0 else 0):.1f}%"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Refresh", callback_data="admin_stats")],
            [InlineKeyboardButton(text="📊 Export CSV", callback_data="admin_export_stats")],
            [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
        ])
        
        await callback.message.edit_text(text, reply_markup=keyboard)
        
    except Exception as e:
        logger.error(f"Stats error: {e}")
        await callback.message.edit_text("❌ Error loading statistics")
    finally:
        session.close()

# ==================== SETTINGS ====================

@router.callback_query(F.data == "admin_settings")
async def admin_settings(callback: CallbackQuery):
    """Show admin settings"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💵 Set USD/NGN Rate", callback_data="admin_set_rate")],
        [InlineKeyboardButton(text="⏱️ Set OTP Timeout", callback_data="admin_set_timeout")],
        [InlineKeyboardButton(text="📊 Clear Cache", callback_data="admin_clear_cache")],
        [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_back")]
    ])
    
    current_rate = os.getenv('USD_NGN_RATE', '1500')
    current_timeout = os.getenv('OTP_TIMEOUT', '300')
    
    await callback.message.edit_text(
        "⚙️ <b>Admin Settings</b>\n\n"
        f"💵 USD to NGN Rate: ₦{current_rate}\n"
        f"⏱️ OTP Timeout: {current_timeout} seconds\n\n"
        f"Select an option to modify:",
        reply_markup=keyboard
    )

# ==================== BACK BUTTON ====================

@router.callback_query(F.data == "admin_back")
async def admin_back(callback: CallbackQuery):
    """Return to admin panel"""
    await admin_panel(callback.message)
    await callback.answer()

# ==================== IMPORT ASYNC FOR BROADCAST ====================

import asyncio
