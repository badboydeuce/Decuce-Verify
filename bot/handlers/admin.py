"""
Admin handlers for DeuceVerify bot
Handles admin commands for user management, refunds, and system monitoring
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta
import logging

from database.db import SessionLocal
from database.crud import (
    get_user_by_telegram_id,
    get_user_by_id,
    get_all_users,
    get_user_count,
    get_user_orders,
    get_user_transactions,
    get_order,
    update_order_status,
    update_user_balance,
    create_transaction,
    get_admin_stats
)
from database.models import OrderStatus, TransactionType
from config import settings

logger = logging.getLogger(__name__)
router = Router()

# ============ FSM STATES ============

class AdminStates(StatesGroup):
    """Admin FSM states"""
    waiting_for_refund_order_id = State()
    waiting_for_add_balance_user = State()
    waiting_for_add_balance_amount = State()
    waiting_for_broadcast_message = State()
    waiting_for_user_telegram_id = State()

# ============ HELPER FUNCTIONS ============

def is_admin(user_id: int) -> bool:
    """Check if user is an admin"""
    return user_id in settings.admin_ids

def format_price(amount: float) -> str:
    """Format price with currency"""
    return f"₦{amount:,.2f}"

def format_date(date: datetime) -> str:
    """Format datetime for display"""
    return date.strftime("%Y-%m-%d %H:%M:%S")

def get_status_emoji(status: str) -> str:
    """Get emoji for order status"""
    status_emoji = {
        'pending': '⏳',
        'received': '✅',
        'expired': '❌',
        'cancelled': '🚫',
        'completed': '🎉'
    }
    return status_emoji.get(status, '📋')

def get_admin_keyboard() -> InlineKeyboardMarkup:
    """Get admin main menu keyboard"""
    keyboard = [
        [InlineKeyboardButton(text="👥 Users", callback_data="admin_users"),
         InlineKeyboardButton(text="📊 Stats", callback_data="admin_stats")],
        [InlineKeyboardButton(text="💰 Refund", callback_data="admin_refund"),
         InlineKeyboardButton(text="➕ Add Balance", callback_data="admin_add_balance")],
        [InlineKeyboardButton(text="📢 Broadcast", callback_data="admin_broadcast"),
         InlineKeyboardButton(text="📋 All Orders", callback_data="admin_orders")],
        [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_users_keyboard(users: list, page: int = 1, total_pages: int = 1) -> InlineKeyboardMarkup:
    """Get users list keyboard with pagination"""
    keyboard = []
    
    for user in users:
        keyboard.append([
            InlineKeyboardButton(
                text=f"👤 {user.username or user.telegram_id} - ₦{user.balance:,.0f}",
                callback_data=f"admin_user_{user.id}"
            )
        ])
    
    # Pagination buttons
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Previous", callback_data=f"admin_users_page_{page-1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"admin_users_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_orders_keyboard(orders: list, page: int = 1, total_pages: int = 1) -> InlineKeyboardMarkup:
    """Get admin orders list keyboard"""
    keyboard = []
    
    for order in orders[:10]:
        status_emoji = get_status_emoji(order.status.value)
        keyboard.append([
            InlineKeyboardButton(
                text=f"{status_emoji} #{order.id} - {order.service_name} - {order.number}",
                callback_data=f"admin_order_{order.id}"
            )
        ])
    
    # Pagination
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Previous", callback_data=f"admin_orders_page_{page-1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"admin_orders_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_panel")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ============ ADMIN ACCESS CHECK ============

async def check_admin(message: Message) -> bool:
    """Check if user is admin and return appropriate response"""
    if not is_admin(message.from_user.id):
        await message.answer(
            "⛔ <b>Access Denied</b>\n\n"
            "You don't have permission to use admin commands.\n"
            "This incident has been logged.",
            parse_mode="HTML"
        )
        logger.warning(f"Unauthorized admin access attempt by {message.from_user.id}")
        return False
    return True

# ============ ADMIN COMMANDS ============

@router.message(Command("admin"))
async def admin_panel(message: Message):
    """Show admin panel"""
    if not await check_admin(message):
        return
    
    db = SessionLocal()
    try:
        stats = get_admin_stats(db)
        
        admin_text = (
            f"🔐 <b>Admin Control Panel</b>\n\n"
            f"<b>System Statistics:</b>\n"
            f"• 👥 Total Users: {stats['total_users']}\n"
            f"• 📦 Total Orders: {stats['total_orders']}\n"
            f"• ⏳ Active Orders: {stats['active_orders']}\n"
            f"• 💰 Total Volume: {format_price(stats['total_volume'])}\n\n"
            f"<b>Quick Actions:</b>\n"
            f"• Issue refunds for failed orders\n"
            f"• Add balance to user accounts\n"
            f"• Send broadcast messages\n"
            f"• View user and order details\n\n"
            f"<i>Select an option below:</i>"
        )
        
        await message.answer(
            admin_text,
            parse_mode="HTML",
            reply_markup=get_admin_keyboard()
        )
    finally:
        db.close()

@router.message(Command("refund"))
async def refund_command(message: Message, state: FSMContext):
    """Handle /refund command"""
    if not await check_admin(message):
        return
    
    # Check if order ID was provided
    parts = message.text.split()
    if len(parts) > 1:
        try:
            order_id = int(parts[1])
            await process_refund(message, order_id)
            return
        except ValueError:
            await message.answer(
                "❌ <b>Invalid Order ID</b>\n\n"
                "Please provide a valid order ID.\n"
                "Example: <code>/refund 12345</code>",
                parse_mode="HTML"
            )
            return
    
    # If no ID provided, ask for it
    await state.set_state(AdminStates.waiting_for_refund_order_id)
    await message.answer(
        "💰 <b>Process Refund</b>\n\n"
        "Please enter the order ID to refund:\n\n"
        "<i>Example: 12345</i>\n"
        "Send /cancel to abort.",
        parse_mode="HTML"
    )

@router.message(AdminStates.waiting_for_refund_order_id)
async def process_refund_order_id(message: Message, state: FSMContext):
    """Process refund order ID input"""
    if message.text.lower() == "/cancel":
        await state.clear()
        await message.answer("❌ Refund cancelled.", reply_markup=get_admin_keyboard())
        return
    
    try:
        order_id = int(message.text.strip())
        await process_refund(message, order_id)
        await state.clear()
    except ValueError:
        await message.answer(
            "❌ <b>Invalid Order ID</b>\n\n"
            "Please enter a valid number.\n"
            "Send /cancel to abort.",
            parse_mode="HTML"
        )

async def process_refund(message: Message, order_id: int):
    """Process refund for an order"""
    db = SessionLocal()
    try:
        order = get_order(db, order_id)
        if not order:
            await message.answer(
                f"❌ <b>Order Not Found</b>\n\n"
                f"Order #{order_id} does not exist.",
                parse_mode="HTML"
            )
            return
        
        if order.status.value in ["expired", "cancelled"]:
            # Check if already refunded
            # This would need a refund flag in the database
            await message.answer(
                f"💰 <b>Refund Order #{order_id}</b>\n\n"
                f"<b>Order Details:</b>\n"
                f"• User: {order.user_id}\n"
                f"• Service: {order.service_name}\n"
                f"• Amount: {format_price(order.cost)}\n"
                f"• Status: {order.status.value}\n\n"
                f"⚠️ This order is already {order.status.value}.\n\n"
                f"Refund amount: {format_price(order.cost)}\n\n"
                f"Confirm refund?",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Yes, Refund", callback_data=f"admin_refund_confirm_{order_id}")],
                    [InlineKeyboardButton(text="❌ Cancel", callback_data="admin_panel")]
                ])
            )
        else:
            await message.answer(
                f"⚠️ <b>Order #{order_id}</b>\n\n"
                f"This order is still {order.status.value}.\n"
                f"Refunds are typically issued for expired/cancelled orders.\n\n"
                f"Refund amount: {format_price(order.cost)}\n\n"
                f"Confirm refund anyway?",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Yes, Force Refund", callback_data=f"admin_refund_confirm_{order_id}")],
                    [InlineKeyboardButton(text="❌ Cancel", callback_data="admin_panel")]
                ])
            )
    finally:
        db.close()

@router.callback_query(F.data.startswith("admin_refund_confirm_"))
async def confirm_refund(callback: CallbackQuery):
    """Confirm and process refund"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[3])
    
    db = SessionLocal()
    try:
        order = get_order(db, order_id)
        if not order:
            await callback.message.edit_text("❌ Order not found.")
            await callback.answer()
            return
        
        # Get user
        user = get_user_by_id(db, order.user_id)
        if not user:
            await callback.message.edit_text("❌ User not found.")
            await callback.answer()
            return
        
        # Update user balance
        update_user_balance(db, user.id, order.cost, "credit")
        
        # Create transaction record
        create_transaction(
            db=db,
            user_id=user.id,
            amount=order.cost,
            transaction_type="credit",
            description=f"Admin refund for order #{order_id} - {order.service_name}",
            status="completed"
        )
        
        # Update order status if still pending
        if order.status.value == "pending":
            update_order_status(db, order_id, "cancelled")
        
        await callback.message.edit_text(
            f"✅ <b>Refund Processed Successfully</b>\n\n"
            f"<b>Order #{order_id}</b>\n"
            f"• Amount: {format_price(order.cost)}\n"
            f"• User: {user.telegram_id} (@{user.username or 'No username'})\n"
            f"• New Balance: {format_price(user.balance + order.cost)}\n\n"
            f"Refund has been credited to user's wallet.",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard()
        )
        
        # Notify user about refund
        from bot.main import bot
        try:
            await bot.send_message(
                user.telegram_id,
                f"💰 <b>Refund Issued</b>\n\n"
                f"Your order #{order_id} has been refunded.\n"
                f"Amount: {format_price(order.cost)}\n\n"
                f"Reason: Admin refund\n\n"
                f"Your new balance: {format_price(user.balance + order.cost)}",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify user about refund: {e}")
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error processing refund: {e}")
        await callback.message.edit_text(
            f"❌ <b>Refund Failed</b>\n\n"
            f"Error: {str(e)}",
            parse_mode="HTML"
        )
        await callback.answer()
    finally:
        db.close()

@router.message(Command("addbalance"))
async def add_balance_command(message: Message, state: FSMContext):
    """Handle /addbalance command"""
    if not await check_admin(message):
        return
    
    parts = message.text.split()
    if len(parts) == 3:
        try:
            user_identifier = parts[1]
            amount = float(parts[2])
            
            # Determine if it's telegram_id or username
            db = SessionLocal()
            try:
                if user_identifier.startswith('@'):
                    username = user_identifier[1:]
                    user = db.query(User).filter(User.username == username).first()
                else:
                    telegram_id = int(user_identifier)
                    user = get_user_by_telegram_id(db, telegram_id)
                
                if user:
                    await process_add_balance(message, user, amount)
                else:
                    await message.answer(
                        f"❌ <b>User Not Found</b>\n\n"
                        f"Could not find user: {user_identifier}",
                        parse_mode="HTML"
                    )
            finally:
                db.close()
            return
        except ValueError:
            await message.answer(
                "❌ <b>Invalid Amount</b>\n\n"
                "Please provide a valid amount.\n"
                "Example: <code>/addbalance @username 1000</code>",
                parse_mode="HTML"
            )
            return
    
    # If not enough arguments, ask for user
    await state.set_state(AdminStates.waiting_for_add_balance_user)
    await message.answer(
        "➕ <b>Add Balance</b>\n\n"
        "Please enter the user (Telegram ID or @username):\n\n"
        "<i>Example: 123456789 or @username</i>\n"
        "Send /cancel to abort.",
        parse_mode="HTML"
    )

@router.message(AdminStates.waiting_for_add_balance_user)
async def add_balance_user(message: Message, state: FSMContext):
    """Get user for adding balance"""
    if message.text.lower() == "/cancel":
        await state.clear()
        await message.answer("❌ Operation cancelled.", reply_markup=get_admin_keyboard())
        return
    
    user_identifier = message.text.strip()
    await state.update_data(user_identifier=user_identifier)
    await state.set_state(AdminStates.waiting_for_add_balance_amount)
    
    await message.answer(
        f"💰 <b>Enter Amount</b>\n\n"
        f"User: {user_identifier}\n\n"
        f"Enter the amount to add (NGN):\n"
        f"<i>Example: 5000</i>\n"
        f"Send /cancel to abort.",
        parse_mode="HTML"
    )

@router.message(AdminStates.waiting_for_add_balance_amount)
async def add_balance_amount(message: Message, state: FSMContext):
    """Process add balance amount"""
    if message.text.lower() == "/cancel":
        await state.clear()
        await message.answer("❌ Operation cancelled.", reply_markup=get_admin_keyboard())
        return
    
    try:
        amount = float(message.text.strip())
        if amount <= 0:
            await message.answer(
                "❌ <b>Invalid Amount</b>\n\n"
                "Amount must be greater than 0.",
                parse_mode="HTML"
            )
            return
        
        data = await state.get_data()
        user_identifier = data.get('user_identifier')
        
        db = SessionLocal()
        try:
            if user_identifier.startswith('@'):
                username = user_identifier[1:]
                user = db.query(User).filter(User.username == username).first()
            else:
                telegram_id = int(user_identifier)
                user = get_user_by_telegram_id(db, telegram_id)
            
            if user:
                await process_add_balance(message, user, amount)
                await state.clear()
            else:
                await message.answer(
                    f"❌ <b>User Not Found</b>\n\n"
                    f"Could not find user: {user_identifier}",
                    parse_mode="HTML"
                )
        finally:
            db.close()
            
    except ValueError:
        await message.answer(
            "❌ <b>Invalid Amount</b>\n\n"
            "Please enter a valid number.",
            parse_mode="HTML"
        )

async def process_add_balance(message: Message, user, amount: float):
    """Process adding balance to user"""
    db = SessionLocal()
    try:
        old_balance = user.balance
        update_user_balance(db, user.id, amount, "credit")
        create_transaction(
            db=db,
            user_id=user.id,
            amount=amount,
            transaction_type="credit",
            description=f"Admin credit - Added by admin",
            status="completed"
        )
        
        await message.answer(
            f"✅ <b>Balance Added Successfully</b>\n\n"
            f"<b>User:</b> {user.telegram_id} (@{user.username or 'No username'})\n"
            f"<b>Old Balance:</b> {format_price(old_balance)}\n"
            f"<b>Amount Added:</b> {format_price(amount)}\n"
            f"<b>New Balance:</b> {format_price(user.balance + amount)}\n\n"
            f"Transaction recorded successfully.",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard()
        )
        
        # Notify user
        from bot.main import bot
        try:
            await bot.send_message(
                user.telegram_id,
                f"➕ <b>Balance Updated</b>\n\n"
                f"An admin has added {format_price(amount)} to your wallet.\n\n"
                f"<b>New Balance:</b> {format_price(user.balance + amount)}",
                parse_mode="HTML"
            )
        except Exception as e:
            logger.error(f"Failed to notify user: {e}")
            
    except Exception as e:
        logger.error(f"Error adding balance: {e}")
        await message.answer(
            f"❌ <b>Failed to Add Balance</b>\n\n"
            f"Error: {str(e)}",
            parse_mode="HTML"
        )
    finally:
        db.close()

# ============ BROADCAST ============

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    """Start broadcast message process"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return
    
    await state.set_state(AdminStates.waiting_for_broadcast_message)
    await callback.message.edit_text(
        "📢 <b>Send Broadcast Message</b>\n\n"
        "Please send the message you want to broadcast to all users.\n\n"
        "<i>Supported: Text, emojis, and formatting\n"
        "Send /cancel to abort</i>",
        parse_mode="HTML"
    )
    await callback.answer()

@router.message(AdminStates.waiting_for_broadcast_message)
async def process_broadcast(message: Message, state: FSMContext):
    """Process and send broadcast message"""
    if message.text.lower() == "/cancel":
        await state.clear()
        await message.answer("❌ Broadcast cancelled.", reply_markup=get_admin_keyboard())
        return
    
    broadcast_text = message.text or message.caption
    if not broadcast_text:
        await message.answer(
            "❌ <b>Invalid Message</b>\n\n"
            "Please send a text message to broadcast.",
            parse_mode="HTML"
        )
        return
    
    # Confirm broadcast
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yes, Send", callback_data="admin_broadcast_confirm")],
        [InlineKeyboardButton(text="❌ Cancel", callback_data="admin_panel")]
    ])
    
    await state.update_data(broadcast_message=broadcast_text)
    await message.answer(
        f"📢 <b>Confirm Broadcast</b>\n\n"
        f"Message to send:\n"
        f"{'─' * 30}\n"
        f"{broadcast_text}\n"
        f"{'─' * 30}\n\n"
        f"<i>This will be sent to ALL users.\n"
        f"Confirm to proceed.</i>",
        parse_mode="HTML",
        reply_markup=keyboard
    )

@router.callback_query(F.data == "admin_broadcast_confirm")
async def confirm_broadcast(callback: CallbackQuery, state: FSMContext):
    """Send broadcast to all users"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return
    
    data = await state.get_data()
    broadcast_text = data.get('broadcast_message')
    
    if not broadcast_text:
        await callback.message.edit_text("❌ No message to broadcast.")
        await callback.answer()
        return
    
    await callback.message.edit_text(
        "⏳ <b>Sending Broadcast...</b>\n\n"
        "Please wait while messages are sent to all users.",
        parse_mode="HTML"
    )
    
    db = SessionLocal()
    try:
        users = get_all_users(db, limit=1000)
        success_count = 0
        fail_count = 0
        
        from bot.main import bot
        
        for user in users:
            try:
                await bot.send_message(
                    user.telegram_id,
                    f"📢 <b>Announcement from Admin</b>\n\n{broadcast_text}",
                    parse_mode="HTML"
                )
                success_count += 1
                await asyncio.sleep(0.05)  # Small delay to avoid rate limiting
            except Exception as e:
                logger.error(f"Failed to send broadcast to {user.telegram_id}: {e}")
                fail_count += 1
        
        await callback.message.edit_text(
            f"✅ <b>Broadcast Complete</b>\n\n"
            f"<b>Statistics:</b>\n"
            f"• ✅ Sent: {success_count}\n"
            f"• ❌ Failed: {fail_count}\n"
            f"• 📊 Total Users: {len(users)}\n\n"
            f"Broadcast message sent successfully!",
            parse_mode="HTML",
            reply_markup=get_admin_keyboard()
        )
        
        await state.clear()
        
    except Exception as e:
        logger.error(f"Error in broadcast: {e}")
        await callback.message.edit_text(
            f"❌ <b>Broadcast Failed</b>\n\n"
            f"Error: {str(e)}",
            parse_mode="HTML"
        )
    finally:
        db.close()
    
    await callback.answer()

# ============ ADMIN CALLBACKS ============

@router.callback_query(F.data == "admin_panel")
async def admin_panel_callback(callback: CallbackQuery):
    """Return to admin panel"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return
    
    db = SessionLocal()
    try:
        stats = get_admin_stats(db)
        
        admin_text = (
            f"🔐 <b>Admin Control Panel</b>\n\n"
            f"<b>System Statistics:</b>\n"
            f"• 👥 Total Users: {stats['total_users']}\n"
            f"• 📦 Total Orders: {stats['total_orders']}\n"
            f"• ⏳ Active Orders: {stats['active_orders']}\n"
            f"• 💰 Total Volume: {format_price(stats['total_volume'])}\n\n"
            f"<i>Select an option below:</i>"
        )
        
        await callback.message.edit_text(
            admin_text,
            parse_mode="HTML",
            reply_markup=get_admin_keyboard()
        )
        await callback.answer()
    finally:
        db.close()

@router.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    """Show detailed statistics"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return
    
    db = SessionLocal()
    try:
        stats = get_admin_stats(db)
        
        # Get additional stats
        from database.models import Order
        today = datetime.utcnow().date()
        today_start = datetime(today.year, today.month, today.day)
        
        today_orders = db.query(Order).filter(Order.created_at >= today_start).count()
        today_volume = db.query(Order).filter(Order.created_at >= today_start).with_entities(db.func.sum(Order.cost)).scalar() or 0
        
        stats_text = (
            f"📊 <b>Detailed Statistics</b>\n\n"
            f"<b>Overall:</b>\n"
            f"• 👥 Total Users: {stats['total_users']}\n"
            f"• 📦 Total Orders: {stats['total_orders']}\n"
            f"• ⏳ Active Orders: {stats['active_orders']}\n"
            f"• 💰 Total Volume: {format_price(stats['total_volume'])}\n\n"
            f"<b>Today:</b>\n"
            f"• 📦 Today's Orders: {today_orders}\n"
            f"• 💰 Today's Volume: {format_price(today_volume)}\n\n"
            f"<b>System Health:</b>\n"
            f"• ✅ Database: Connected\n"
            f"• 🤖 Bot: Running\n"
            f"• 💳 Paystack: {'✅' if settings.paystack_secret_key else '❌'}\n"
            f"• 📱 SMS-Man: {'✅' if settings.sms_man_token else '❌'}\n\n"
            f"<i>Last updated: {format_date(datetime.utcnow())}</i>"
        )
        
        await callback.message.edit_text(
            stats_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Back to Admin", callback_data="admin_panel")]
            ])
        )
        await callback.answer()
    finally:
        db.close()

@router.callback_query(F.data == "admin_users")
async def admin_users_list(callback: CallbackQuery):
    """Show list of users"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return
    
    db = SessionLocal()
    try:
        users = get_all_users(db, limit=20)
        total_users = get_user_count(db)
        total_pages = (total_users + 19) // 20
        
        if not users:
            await callback.message.edit_text("No users found.")
            await callback.answer()
            return
        
        users_text = f"👥 <b>Users - Page 1/{total_pages}</b>\n\n"
        for user in users:
            users_text += f"• 👤 {user.telegram_id} - @{user.username or 'No username'} - {format_price(user.balance)}\n"
        
        await callback.message.edit_text(
            users_text,
            parse_mode="HTML",
            reply_markup=get_users_keyboard(users, 1, total_pages)
        )
        await callback.answer()
    finally:
        db.close()

@router.callback_query(F.data.startswith("admin_users_page_"))
async def admin_users_page(callback: CallbackQuery):
    """Handle users pagination"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return
    
    page = int(callback.data.split("_")[3])
    limit = 20
    offset = (page - 1) * limit
    
    db = SessionLocal()
    try:
        users = get_all_users(db, limit=limit, offset=offset)
        total_users = get_user_count(db)
        total_pages = (total_users + limit - 1) // limit
        
        users_text = f"👥 <b>Users - Page {page}/{total_pages}</b>\n\n"
        for user in users:
            users_text += f"• 👤 {user.telegram_id} - @{user.username or 'No username'} - {format_price(user.balance)}\n"
        
        await callback.message.edit_text(
            users_text,
            parse_mode="HTML",
            reply_markup=get_users_keyboard(users, page, total_pages)
        )
        await callback.answer()
    finally:
        db.close()

@router.callback_query(F.data == "admin_orders")
async def admin_orders_list(callback: CallbackQuery):
    """Show list of all orders"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return
    
    db = SessionLocal()
    try:
        from database.crud import get_all_orders
        orders = get_all_orders(db, limit=20)
        total_orders = db.query(Order).count()
        total_pages = (total_orders + 19) // 20
        
        orders_text = f"📋 <b>All Orders - Page 1/{total_pages}</b>\n\n"
        for order in orders[:10]:
            status_emoji = get_status_emoji(order.status.value)
            orders_text += f"{status_emoji} #{order.id} - {order.service_name} - {order.number}\n"
        
        await callback.message.edit_text(
            orders_text,
            parse_mode="HTML",
            reply_markup=get_orders_keyboard(orders, 1, total_pages)
        )
        await callback.answer()
    finally:
        db.close()

@router.callback_query(F.data.startswith("admin_order_"))
async def admin_view_order(callback: CallbackQuery):
    """View order details as admin"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return
    
    order_id = int(callback.data.split("_")[2])
    
    db = SessionLocal()
    try:
        order = get_order(db, order_id)
        if not order:
            await callback.message.edit_text("❌ Order not found.")
            await callback.answer()
            return
        
        user = get_user_by_id(db, order.user_id)
        
        status_emoji = get_status_emoji(order.status.value)
        order_icon = "📱" if order.order_type.value == "activation" else "🔄"
        
        order_text = (
            f"{status_emoji} <b>Order #{order.id}</b> {order_icon}\n\n"
            f"<b>User:</b> {user.telegram_id} (@{user.username or 'No username'})\n"
            f"<b>Type:</b> {order.order_type.value.upper()}\n"
            f"<b>Country:</b> {order.country_name}\n"
            f"<b>Service:</b> {order.service_name}\n"
            f"<b>Number:</b> <code>{order.number}</code>\n"
            f"<b>Cost:</b> {format_price(order.cost)}\n"
            f"<b>Status:</b> {order.status.value.upper()}\n"
            f"<b>Created:</b> {format_date(order.created_at)}\n"
            f"<b>Expires:</b> {format_date(order.expires_at)}\n"
        )
        
        if order.otp_code:
            order_text += f"<b>OTP Code:</b> <code>{order.otp_code}</code>\n"
        
        order_text += f"\n<button>Actions:</b>\n"
        order_text += f"• /refund {order.id} - Issue refund\n"
        
        await callback.message.edit_text(
            order_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💰 Refund Order", callback_data=f"admin_refund_confirm_{order.id}")],
                [InlineKeyboardButton(text="🔙 Back to Orders", callback_data="admin_orders")]
            ])
        )
        await callback.answer()
    finally:
        db.close()

@router.callback_query(F.data == "admin_refund")
async def admin_refund_prompt(callback: CallbackQuery, state: FSMContext):
    """Prompt for refund order ID"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return
    
    await state.set_state(AdminStates.waiting_for_refund_order_id)
    await callback.message.edit_text(
        "💰 <b>Process Refund</b>\n\n"
        "Please enter the order ID to refund:\n\n"
        "<i>Example: 12345</i>\n"
        "Send /cancel to abort.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="admin_panel")]
        ])
    )
    await callback.answer()

@router.callback_query(F.data == "admin_add_balance")
async def admin_add_balance_prompt(callback: CallbackQuery, state: FSMContext):
    """Prompt for add balance"""
    if not is_admin(callback.from_user.id):
        await callback.answer("Unauthorized", show_alert=True)
        return
    
    await state.set_state(AdminStates.waiting_for_add_balance_user)
    await callback.message.edit_text(
        "➕ <b>Add Balance</b>\n\n"
        "Please enter the user (Telegram ID or @username):\n\n"
        "<i>Example: 123456789 or @username</i>\n"
        "Send /cancel to abort.",
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Cancel", callback_data="admin_panel")]
        ])
    )
    await callback.answer()

# Import required models
from database.models import User, Order
import asyncio
