"""
Orders handlers for DeuceVerify bot
Handles viewing, managing, and tracking all user orders
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from datetime import datetime
import asyncio
import logging

from database.db import SessionLocal
from database.crud import (
    get_user_by_telegram_id,
    get_user_orders,
    get_order,
    update_order_status,
    update_order_otp
)
from database.models import OrderStatus, OrderType
from api.services.sms_man import sms_man
from config import settings

logger = logging.getLogger(__name__)
router = Router()

# ============ HELPER FUNCTIONS ============

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

def get_country_flag(country_name: str) -> str:
    """Get emoji flag for country"""
    flags = {
        'Russia': '🇷🇺', 'USA': '🇺🇸', 'United States': '🇺🇸', 
        'UK': '🇬🇧', 'United Kingdom': '🇬🇧', 'China': '🇨🇳',
        'India': '🇮🇳', 'Germany': '🇩🇪', 'France': '🇫🇷',
        'Japan': '🇯🇵', 'Brazil': '🇧🇷', 'Canada': '🇨🇦',
        'Australia': '🇦🇺', 'Mexico': '🇲🇽', 'Indonesia': '🇮🇩',
        'Turkey': '🇹🇷', 'Nigeria': '🇳🇬', 'Vietnam': '🇻🇳'
    }
    
    for key, flag in flags.items():
        if key.lower() in country_name.lower():
            return flag
    return '🌍'

def get_orders_keyboard(orders: list, page: int = 1, total_pages: int = 1) -> InlineKeyboardMarkup:
    """Get orders list keyboard with pagination"""
    keyboard = []
    
    # Add order buttons
    for order in orders[:10]:
        status_emoji = get_status_emoji(order.status.value)
        order_type_icon = "📱" if order.order_type.value == "activation" else "🔄"
        
        keyboard.append([
            InlineKeyboardButton(
                text=f"{status_emoji} {order_type_icon} {order.service_name} - {order.number}",
                callback_data=f"view_order_{order.id}"
            )
        ])
    
    # Pagination buttons
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Previous", callback_data=f"orders_page_{page-1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"orders_page_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    # Filter buttons
    keyboard.append([
        InlineKeyboardButton(text="📱 Active", callback_data="filter_orders_active"),
        InlineKeyboardButton(text="✅ Received", callback_data="filter_orders_received"),
        InlineKeyboardButton(text="❌ Expired", callback_data="filter_orders_expired")
    ])
    
    keyboard.append([InlineKeyboardButton(text="🔄 All Orders", callback_data="filter_orders_all")])
    keyboard.append([InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_main")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_order_detail_keyboard(order_id: int, order_type: str, status: str) -> InlineKeyboardMarkup:
    """Get order detail action keyboard"""
    keyboard = []
    
    if status == "pending":
        if order_type == "activation":
            keyboard.append([
                InlineKeyboardButton(text="🔄 Refresh OTP", callback_data=f"refresh_otp_{order_id}"),
                InlineKeyboardButton(text="📋 Copy Code", callback_data=f"copy_otp_{order_id}")
            ])
            keyboard.append([InlineKeyboardButton(text="❌ Cancel Order", callback_data=f"cancel_order_{order_id}")])
        else:  # rental
            keyboard.append([
                InlineKeyboardButton(text="📨 Check SMS", callback_data=f"check_rental_sms_{order_id}"),
                InlineKeyboardButton(text="📜 All Messages", callback_data=f"view_all_sms_{order_id}")
            ])
            keyboard.append([InlineKeyboardButton(text="❌ Close Rental", callback_data=f"close_rental_{order_id}")])
    
    elif status == "received":
        if order_type == "activation":
            keyboard.append([
                InlineKeyboardButton(text="📋 Copy Code", callback_data=f"copy_otp_{order_id}")
            ])
        else:
            keyboard.append([
                InlineKeyboardButton(text="📨 Check SMS", callback_data=f"check_rental_sms_{order_id}"),
                InlineKeyboardButton(text="📜 All Messages", callback_data=f"view_all_sms_{order_id}")
            ])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Back to Orders", callback_data="my_orders")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def format_time_remaining(expires_at: datetime) -> str:
    """Format time remaining until expiry"""
    remaining = expires_at - datetime.utcnow()
    
    if remaining.total_seconds() <= 0:
        return "Expired"
    
    days = remaining.days
    hours = remaining.seconds // 3600
    minutes = (remaining.seconds % 3600) // 60
    
    if days > 0:
        return f"{days}d {hours}h remaining"
    elif hours > 0:
        return f"{hours}h {minutes}m remaining"
    else:
        return f"{minutes}m remaining"

# ============ MAIN ORDERS MENU ============

@router.message(F.text == "📋 My Orders")
async def my_orders(message: Message, state: FSMContext):
    """Handle My Orders button"""
    await state.clear()
    
    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(db, message.from_user.id)
        if not user:
            await message.answer(
                "❌ <b>User Not Found</b>\n\n"
                "Please use /start to register first.",
                parse_mode="HTML"
            )
            return
        
        # Get all orders
        orders = get_user_orders(db, user.id, limit=20)
        
        if not orders:
            await message.answer(
                "📋 <b>No Orders Found</b>\n\n"
                "You haven't placed any orders yet.\n\n"
                "Use the 'Buy Number' button to get started!",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📱 Buy Number", callback_data="buy_number")],
                    [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_main")]
                ])
            )
            return
        
        # Group orders by status
        active_orders = [o for o in orders if o.status.value in ["pending", "received"]]
        completed_orders = [o for o in orders if o.status.value in ["expired", "cancelled", "completed"]]
        
        response = f"📋 <b>My Orders</b>\n\n"
        
        if active_orders:
            response += f"<b>🟢 Active Orders ({len(active_orders)})</b>\n"
            for order in active_orders[:5]:
                status_emoji = get_status_emoji(order.status.value)
                order_icon = "📱" if order.order_type.value == "activation" else "🔄"
                time_remaining = format_time_remaining(order.expires_at)
                
                response += (
                    f"{status_emoji} {order_icon} <b>#{order.id}</b> - {order.service_name}\n"
                    f"   └─ {order.number} | {time_remaining}\n"
                )
            response += "\n"
        
        if completed_orders:
            response += f"<b>📜 Completed/Expired ({len(completed_orders)})</b>\n"
            for order in completed_orders[:5]:
                status_emoji = get_status_emoji(order.status.value)
                order_icon = "📱" if order.order_type.value == "activation" else "🔄"
                
                response += (
                    f"{status_emoji} {order_icon} <b>#{order.id}</b> - {order.service_name}\n"
                    f"   └─ {format_date(order.created_at)}\n"
                )
        
        if len(orders) > 10:
            response += f"\n<i>Showing last 10 of {len(orders)} orders</i>"
        
        response += f"\n\n<i>Click an order below to view details:</i>"
        
        # Create keyboard with orders
        keyboard = []
        for order in orders[:10]:
            status_emoji = get_status_emoji(order.status.value)
            order_icon = "📱" if order.order_type.value == "activation" else "🔄"
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{status_emoji} {order_icon} #{order.id} - {order.service_name}",
                    callback_data=f"view_order_{order.id}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_main")])
        
        await message.answer(
            response,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
    except Exception as e:
        logger.error(f"Error in my_orders: {e}")
        await message.answer(
            "❌ <b>Error Loading Orders</b>\n\n"
            "Unable to fetch your orders. Please try again later.",
            parse_mode="HTML"
        )
    finally:
        db.close()

@router.callback_query(F.data == "my_orders")
async def my_orders_callback(callback: CallbackQuery, state: FSMContext):
    """Handle my orders callback"""
    await state.clear()
    
    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(db, callback.from_user.id)
        if not user:
            await callback.message.edit_text(
                "❌ <b>User Not Found</b>\n\n"
                "Please use /start to register first.",
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        orders = get_user_orders(db, user.id, limit=20)
        
        if not orders:
            await callback.message.edit_text(
                "📋 <b>No Orders Found</b>\n\n"
                "You haven't placed any orders yet.\n\n"
                "Use the 'Buy Number' button to get started!",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📱 Buy Number", callback_data="buy_number")],
                    [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_main")]
                ])
            )
            await callback.answer()
            return
        
        # Build response
        response = f"📋 <b>My Orders</b>\n\n"
        
        active_orders = [o for o in orders if o.status.value in ["pending", "received"]]
        if active_orders:
            response += f"<b>🟢 Active Orders ({len(active_orders)})</b>\n"
            for order in active_orders[:5]:
                status_emoji = get_status_emoji(order.status.value)
                order_icon = "📱" if order.order_type.value == "activation" else "🔄"
                time_remaining = format_time_remaining(order.expires_at)
                response += f"{status_emoji} {order_icon} #{order.id} - {order.service_name}\n"
                response += f"   └─ {order.number} | {time_remaining}\n"
            response += "\n"
        
        completed_orders = [o for o in orders if o.status.value in ["expired", "cancelled", "completed"]]
        if completed_orders:
            response += f"<b>📜 Completed/Expired ({len(completed_orders)})</b>\n"
            for order in completed_orders[:5]:
                status_emoji = get_status_emoji(order.status.value)
                order_icon = "📱" if order.order_type.value == "activation" else "🔄"
                response += f"{status_emoji} {order_icon} #{order.id} - {order.service_name}\n"
                response += f"   └─ {format_date(order.created_at)}\n"
        
        response += f"\n<i>Click an order below to view details:</i>"
        
        # Create keyboard
        keyboard = []
        for order in orders[:10]:
            status_emoji = get_status_emoji(order.status.value)
            order_icon = "📱" if order.order_type.value == "activation" else "🔄"
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{status_emoji} {order_icon} #{order.id} - {order.service_name}",
                    callback_data=f"view_order_{order.id}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_main")])
        
        await callback.message.edit_text(
            response,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in my_orders_callback: {e}")
        await callback.message.edit_text(
            "❌ <b>Error Loading Orders</b>\n\n"
            "Unable to fetch your orders. Please try again later.",
            parse_mode="HTML"
        )
        await callback.answer()
    finally:
        db.close()

# ============ ORDER DETAILS ============

@router.callback_query(F.data.startswith("view_order_"))
async def view_order_details(callback: CallbackQuery):
    """View detailed order information"""
    order_id = int(callback.data.split("_")[2])
    
    db = SessionLocal()
    try:
        order = get_order(db, order_id, callback.from_user.id)
        if not order:
            await callback.answer("Order not found", show_alert=True)
            return
        
        status_emoji = get_status_emoji(order.status.value)
        order_icon = "📱" if order.order_type.value == "activation" else "🔄"
        
        # Build order details
        details = (
            f"{status_emoji} <b>Order #{order.id}</b> {order_icon}\n\n"
            f"<b>📋 Order Type:</b> {order.order_type.value.upper()}\n"
            f"<b>🌍 Country:</b> {get_country_flag(order.country_name)} {order.country_name}\n"
            f"<b>📱 Service:</b> {order.service_name}\n"
            f"<b>📞 Number:</b> <code>{order.number}</code>\n"
            f"<b>💰 Cost:</b> {format_price(order.cost)}\n"
            f"<b>📅 Created:</b> {format_date(order.created_at)}\n"
        )
        
        if order.order_type.value == "activation":
            details += f"<b>⏰ Expires:</b> {format_date(order.expires_at)}\n"
            details += f"<b>⏱️ Time Remaining:</b> {format_time_remaining(order.expires_at)}\n"
            
            if order.otp_code:
                details += f"\n<b>🔐 OTP Code:</b> <code>{order.otp_code}</code>\n"
            elif order.status.value == "pending":
                details += f"\n<i>⏳ Waiting for SMS... The OTP will appear here automatically.</i>\n"
        else:  # rental
            details += f"<b>⏰ Expires:</b> {format_date(order.expires_at)}\n"
            details += f"<b>⏱️ Time Remaining:</b> {format_time_remaining(order.expires_at)}\n"
            if order.rental_duration:
                details += f"<b>📆 Duration:</b> {order.rental_duration.replace('_', ' ')}\n"
        
        details += f"\n<b>📊 Status:</b> {status_emoji} {order.status.value.upper()}\n"
        
        await callback.message.edit_text(
            details,
            parse_mode="HTML",
            reply_markup=get_order_detail_keyboard(order.id, order.order_type.value, order.status.value)
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error viewing order details: {e}")
        await callback.answer("Error loading order details", show_alert=True)
    finally:
        db.close()

# ============ ORDER ACTIONS ============

@router.callback_query(F.data.startswith("cancel_order_"))
async def cancel_order_prompt(callback: CallbackQuery):
    """Prompt to cancel order"""
    order_id = int(callback.data.split("_")[2])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yes, Cancel", callback_data=f"confirm_cancel_{order_id}")],
        [InlineKeyboardButton(text="❌ No, Keep", callback_data=f"view_order_{order_id}")]
    ])
    
    await callback.message.edit_text(
        "⚠️ <b>Cancel Order?</b>\n\n"
        "Are you sure you want to cancel this order?\n\n"
        "<i>Note: Refunds are only issued if no SMS was received\n"
        "within the timeout period (20 minutes).</i>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_cancel_"))
async def confirm_cancel_order(callback: CallbackQuery):
    """Confirm order cancellation"""
    order_id = int(callback.data.split("_")[2])
    
    db = SessionLocal()
    try:
        from database.crud import update_user_balance, create_transaction
        
        order = get_order(db, order_id, callback.from_user.id)
        if not order:
            await callback.answer("Order not found", show_alert=True)
            return
        
        if order.status.value != "pending":
            await callback.answer("Order cannot be cancelled in its current state", show_alert=True)
            return
        
        # Cancel in SMS-Man API
        try:
            if order.order_type.value == "activation":
                await sms_man.set_activation_status(int(order.request_id), "cancel")
            else:
                await sms_man.set_rental_status(int(order.request_id), "cancel")
        except Exception as e:
            logger.error(f"Error cancelling in SMS-Man: {e}")
        
        # Update order status
        update_order_status(db, order_id, "cancelled")
        
        # Refund if no OTP received
        if not order.otp_code:
            user = get_user_by_telegram_id(db, callback.from_user.id)
            update_user_balance(db, user.id, order.cost, "credit")
            create_transaction(
                db=db,
                user_id=user.id,
                amount=order.cost,
                transaction_type="credit",
                description=f"Refund for cancelled order #{order_id}"
            )
            
            await callback.message.edit_text(
                f"✅ <b>Order Cancelled & Refunded</b>\n\n"
                f"Order #{order_id} has been cancelled.\n"
                f"Refund of {format_price(order.cost)} has been issued.\n\n"
                f"Your new balance has been updated.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📋 My Orders", callback_data="my_orders")],
                    [InlineKeyboardButton(text="💰 Check Balance", callback_data="wallet_menu")],
                    [InlineKeyboardButton(text="🔙 Main Menu", callback_data="back_to_main")]
                ])
            )
        else:
            await callback.message.edit_text(
                f"✅ <b>Order Cancelled</b>\n\n"
                f"Order #{order_id} has been cancelled.\n"
                f"No refund issued as OTP was already received.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📋 My Orders", callback_data="my_orders")],
                    [InlineKeyboardButton(text="🔙 Main Menu", callback_data="back_to_main")]
                ])
            )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error cancelling order: {e}")
        await callback.message.edit_text(
            "❌ <b>Error Cancelling Order</b>\n\n"
            "Unable to cancel order. Please try again later.",
            parse_mode="HTML"
        )
        await callback.answer()
    finally:
        db.close()

# ============ OTP ACTIONS ============

@router.callback_query(F.data.startswith("refresh_otp_"))
async def refresh_otp_order(callback: CallbackQuery):
    """Manual refresh OTP for order"""
    order_id = int(callback.data.split("_")[2])
    
    await callback.answer("🔄 Checking for OTP...")
    
    db = SessionLocal()
    try:
        order = get_order(db, order_id, callback.from_user.id)
        if not order:
            await callback.message.edit_text("❌ Order not found.")
            return
        
        # Check if expired
        if datetime.utcnow() > order.expires_at:
            update_order_status(db, order_id, "expired")
            await callback.message.edit_text(
                "⏰ <b>Order Expired</b>\n\n"
                "This order has expired without receiving OTP.",
                parse_mode="HTML"
            )
            return
        
        # Fetch OTP
        result = await sms_man.get_activation_sms(int(order.request_id))
        
        if result.get("sms_code"):
            otp_code = result["sms_code"]
            update_order_otp(db, order_id, otp_code)
            
            await callback.message.edit_text(
                f"🔐 <b>OTP Received!</b>\n\n"
                f"<b>Order #{order.id}</b>\n"
                f"<b>Number:</b> <code>{order.number}</code>\n"
                f"<b>OTP Code:</b> <code>{otp_code}</code>\n\n"
                f"<i>Use this code for verification.</i>",
                parse_mode="HTML",
                reply_markup=get_order_detail_keyboard(order.id, "activation", "received")
            )
        else:
            # Still waiting
            await callback.message.answer(
                f"⏳ <b>Still Waiting for SMS...</b>\n\n"
                f"Order #{order.id}\n"
                f"Number: <code>{order.number}</code>\n\n"
                f"No OTP received yet. Please wait a few more seconds.\n"
                f"Time remaining: {format_time_remaining(order.expires_at)}",
                parse_mode="HTML"
            )
            
    except Exception as e:
        logger.error(f"Error refreshing OTP: {e}")
        await callback.message.answer(
            "❌ <b>Error Checking OTP</b>\n\n"
            "Unable to fetch OTP. Please try again.",
            parse_mode="HTML"
        )
    finally:
        db.close()

@router.callback_query(F.data.startswith("copy_otp_"))
async def copy_otp_code(callback: CallbackQuery):
    """Copy OTP code to clipboard"""
    order_id = int(callback.data.split("_")[2])
    
    db = SessionLocal()
    try:
        order = get_order(db, order_id, callback.from_user.id)
        if order and order.otp_code:
            await callback.answer(f"✅ Code copied: {order.otp_code}", show_alert=True)
        else:
            await callback.answer("❌ No OTP code found yet", show_alert=True)
    finally:
        db.close()

# ============ FILTER ORDERS ============

@router.callback_query(F.data.startswith("filter_orders_"))
async def filter_orders(callback: CallbackQuery):
    """Filter orders by status"""
    filter_type = callback.data.split("_")[2]
    
    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(db, callback.from_user.id)
        if not user:
            await callback.answer("User not found", show_alert=True)
            return
        
        # Determine status filter
        status_filter = None
        if filter_type == "active":
            status_filter = ["pending", "received"]
        elif filter_type == "received":
            status_filter = ["received"]
        elif filter_type == "expired":
            status_filter = ["expired", "cancelled"]
        elif filter_type == "all":
            status_filter = None
        
        # Get filtered orders
        if status_filter:
            orders = []
            for status in status_filter:
                orders.extend(get_user_orders(db, user.id, status=status, limit=20))
            orders = sorted(orders, key=lambda x: x.created_at, reverse=True)[:20]
        else:
            orders = get_user_orders(db, user.id, limit=20)
        
        if not orders:
            await callback.message.edit_text(
                f"📋 <b>No Orders Found</b>\n\n"
                f"No {filter_type} orders to display.",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔙 Back to Orders", callback_data="my_orders")]
                ])
            )
            await callback.answer()
            return
        
        # Build response
        response = f"📋 <b>Orders - {filter_type.upper()}</b>\n\n"
        
        for order in orders[:10]:
            status_emoji = get_status_emoji(order.status.value)
            order_icon = "📱" if order.order_type.value == "activation" else "🔄"
            time_remaining = format_time_remaining(order.expires_at) if order.status.value in ["pending", "received"] else format_date(order.created_at)
            
            response += (
                f"{status_emoji} {order_icon} <b>#{order.id}</b> - {order.service_name}\n"
                f"   └─ {order.number} | {time_remaining}\n"
            )
        
        response += f"\n<i>Click an order to view details:</i>"
        
        # Create keyboard
        keyboard = []
        for order in orders[:10]:
            status_emoji = get_status_emoji(order.status.value)
            order_icon = "📱" if order.order_type.value == "activation" else "🔄"
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{status_emoji} {order_icon} #{order.id} - {order.service_name}",
                    callback_data=f"view_order_{order.id}"
                )
            ])
        
        keyboard.append([InlineKeyboardButton(text="🔙 Back to Orders", callback_data="my_orders")])
        
        await callback.message.edit_text(
            response,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error filtering orders: {e}")
        await callback.answer("Error filtering orders", show_alert=True)
    finally:
        db.close()

# ============ PAGINATION ============

@router.callback_query(F.data.startswith("orders_page_"))
async def orders_page(callback: CallbackQuery):
    """Handle orders pagination"""
    page = int(callback.data.split("_")[2])
    
    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(db, callback.from_user.id)
        if not user:
            await callback.answer("User not found", show_alert=True)
            return
        
        limit = 10
        offset = (page - 1) * limit
        orders = get_user_orders(db, user.id, limit=limit, offset=offset)
        total_orders = len(get_user_orders(db, user.id))
        total_pages = (total_orders + limit - 1) // limit
        
        if not orders:
            await callback.answer("No more orders", show_alert=True)
            return
        
        response = f"📋 <b>My Orders - Page {page}/{total_pages}</b>\n\n"
        
        for order in orders:
            status_emoji = get_status_emoji(order.status.value)
            order_icon = "📱" if order.order_type.value == "activation" else "🔄"
            time_remaining = format_time_remaining(order.expires_at) if order.status.value in ["pending", "received"] else format_date(order.created_at)
            
            response += (
                f"{status_emoji} {order_icon} <b>#{order.id}</b> - {order.service_name}\n"
                f"   └─ {order.number} | {time_remaining}\n"
            )
        
        response += f"\n<i>Click an order to view details:</i>"
        
        await callback.message.edit_text(
            response,
            parse_mode="HTML",
            reply_markup=get_orders_keyboard(orders, page, total_pages)
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in orders pagination: {e}")
        await callback.answer("Error loading page", show_alert=True)
    finally:
        db.close()

# ============ COMMAND HANDLERS ============

@router.message(F.text == "📋 View Orders")
async def view_orders_command(message: Message):
    """Handle view orders command"""
    await my_orders(message, None)

@router.message(F.text == "🔄 Refresh Orders")
async def refresh_orders(message: Message):
    """Handle refresh orders"""
    await my_orders(message, None)
