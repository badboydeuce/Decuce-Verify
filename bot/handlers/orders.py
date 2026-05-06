# Orders handler
"""
Order management handlers for DeuceVerify
View orders, check OTP status, cancel orders
"""

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from datetime import datetime, timedelta
import asyncio
from loguru import logger

router = Router()

# ==================== ORDER LIST ====================

@router.callback_query(F.data == "menu_orders")
async def list_orders(callback: CallbackQuery, db_manager):
    """Show user's active orders"""
    session = db_manager.get_session()
    
    try:
        from models.database import Order, OrderStatus
        
        # Get active orders
        active_orders = session.query(Order).filter(
            Order.user_id == callback.from_user.id,
            Order.status.in_([OrderStatus.ACTIVE, OrderStatus.PENDING])
        ).order_by(Order.created_at.desc()).all()
        
        # Get completed/expired orders (last 5)
        old_orders = session.query(Order).filter(
            Order.user_id == callback.from_user.id,
            Order.status.in_([OrderStatus.RECEIVED, OrderStatus.EXPIRED, OrderStatus.CANCELLED])
        ).order_by(Order.created_at.desc()).limit(5).all()
        
        if not active_orders and not old_orders:
            await callback.message.edit_text(
                "📋 <b>My Orders</b>\n\n"
                "You haven't rented any numbers yet.\n\n"
                "Tap the button below to get started!",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📱 Buy Number", callback_data="menu_buy")],
                    [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_menu")]
                ])
            )
            return
        
        text = "📋 <b>My Orders</b>\n\n"
        
        # Active orders section
        if active_orders:
            text += "🟢 <b>ACTIVE ORDERS</b>\n"
            for order in active_orders:
                remaining = ""
                if order.expires_at:
                    remaining_sec = (order.expires_at - datetime.utcnow()).total_seconds()
                    if remaining_sec > 0:
                        minutes = int(remaining_sec // 60)
                        seconds = int(remaining_sec % 60)
                        remaining = f" ⏱️ {minutes}:{seconds:02d}"
                
                text += f"\n└ <b>#{order.id}</b> - {order.service_name}\n"
                text += f"   📱 {order.country_name} | 💰 ${order.cost:.2f}{remaining}\n"
                text += f"   Status: {'⏳ Waiting for OTP' if order.status.value == 'active' else '🔄 Processing'}\n"
        
        # Recent orders section
        if old_orders:
            text += "\n📜 <b>RECENT ORDERS</b>\n"
            for order in old_orders[:3]:
                status_emoji = "✅" if order.status.value == "received" else "⏰" if order.status.value == "expired" else "❌"
                text += f"\n└ {status_emoji} <b>#{order.id}</b> - {order.service_name}\n"
                text += f"   {order.country_name} | ${order.cost:.2f}\n"
                text += f"   {order.created_at.strftime('%Y-%m-%d %H:%M')}\n"
        
        # Build keyboard with active order buttons
        keyboard = []
        for order in active_orders:
            keyboard.append([InlineKeyboardButton(
                text=f"📱 Order #{order.id} - {order.service_name}",
                callback_data=f"view_order_{order.id}"
            )])
        
        keyboard.append([InlineKeyboardButton(text="🔄 Refresh", callback_data="menu_orders")])
        keyboard.append([InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_menu")])
        
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
    except Exception as e:
        logger.error(f"Error listing orders: {e}")
        await callback.message.edit_text(
            "❌ Error loading orders. Please try again.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Retry", callback_data="menu_orders")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")]
            ])
        )
    finally:
        session.close()

# ==================== VIEW SINGLE ORDER ====================

@router.callback_query(F.data.startswith("view_order_"))
async def view_order(callback: CallbackQuery, db_manager, sms_client):
    """View detailed order information"""
    order_id = int(callback.data.split("_")[2])
    
    session = db_manager.get_session()
    
    try:
        from models.database import Order, OrderStatus
        
        order = session.query(Order).filter_by(id=order_id, user_id=callback.from_user.id).first()
        
        if not order:
            await callback.answer("Order not found", show_alert=True)
            await callback.message.edit_text(
                "Order not found.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📋 My Orders", callback_data="menu_orders")],
                    [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")]
                ])
            )
            return
        
        # Calculate time remaining
        time_remaining = ""
        if order.expires_at and order.status.value in ['active', 'pending']:
            remaining_sec = (order.expires_at - datetime.utcnow()).total_seconds()
            if remaining_sec > 0:
                minutes = int(remaining_sec // 60)
                seconds = int(remaining_sec % 60)
                time_remaining = f"\n⏱️ <b>Expires in:</b> {minutes}:{seconds:02d}"
            else:
                time_remaining = "\n⚠️ <b>Expired!</b>"
        
        # Status emoji and text
        status_map = {
            'active': ('🟢', 'Waiting for OTP'),
            'pending': ('🟡', 'Processing'),
            'received': ('✅', 'Code Received!'),
            'expired': ('⏰', 'Expired'),
            'cancelled': ('❌', 'Cancelled'),
            'refunded': ('💰', 'Refunded')
        }
        status_emoji, status_text = status_map.get(order.status.value if hasattr(order.status, 'value') else str(order.status), ('❓', 'Unknown'))
        
        # Build message
        text = f"📱 <b>Order #{order.id}</b>\n\n"
        text += f"{status_emoji} <b>Status:</b> {status_text}\n"
        text += f"📱 <b>Service:</b> {order.service_name}\n"
        text += f"🌍 <b>Country:</b> {order.country_name}\n"
        text += f"📞 <b>Number:</b> <code>{order.number}</code>\n"
        text += f"💰 <b>Cost:</b> ${order.cost:.2f}\n"
        text += f"📅 <b>Created:</b> {order.created_at.strftime('%Y-%m-%d %H:%M:%S')}{time_remaining}\n"
        
        # Show OTP if received
        if order.otp_code:
            text += f"\n🔐 <b>Verification Code:</b>\n"
            text += f"<code>{order.otp_code}</code>\n"
        
        # Build keyboard based on status
        keyboard = []
        
        if order.status.value in ['active', 'pending']:
            keyboard.append([InlineKeyboardButton(text="🔄 Refresh OTP", callback_data=f"refresh_otp_{order.id}")])
            keyboard.append([InlineKeyboardButton(text="📋 Copy Number", callback_data=f"copy_number_{order.number}")])
            keyboard.append([InlineKeyboardButton(text="❌ Cancel Order", callback_data=f"cancel_order_{order.id}")])
        elif order.status.value == 'received' and order.otp_code:
            keyboard.append([InlineKeyboardButton(text="📋 Copy Code", callback_data=f"copy_code_{order.otp_code}")])
            keyboard.append([InlineKeyboardButton(text="📋 Copy Number", callback_data=f"copy_number_{order.number}")])
        elif order.status.value == 'expired':
            keyboard.append([InlineKeyboardButton(text="🔄 Rent Again", callback_data="menu_buy")])
            keyboard.append([InlineKeyboardButton(text="💰 Request Refund", callback_data=f"request_refund_{order.id}")])
        
        keyboard.append([InlineKeyboardButton(text="📋 My Orders", callback_data="menu_orders")])
        keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")])
        
        await callback.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        
    except Exception as e:
        logger.error(f"Error viewing order {order_id}: {e}")
        await callback.message.edit_text(
            "❌ Error loading order details.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 My Orders", callback_data="menu_orders")]
            ])
        )
    finally:
        session.close()

# ==================== REFRESH OTP ====================

@router.callback_query(F.data.startswith("refresh_otp_"))
async def refresh_otp(callback: CallbackQuery, db_manager, sms_client):
    """Manually refresh OTP for an order"""
    order_id = int(callback.data.split("_")[2])
    
    await callback.answer("🔄 Checking for OTP...")
    
    session = db_manager.get_session()
    
    try:
        from models.database import Order, OrderStatus
        
        order = session.query(Order).filter_by(id=order_id, user_id=callback.from_user.id).first()
        
        if not order:
            await callback.answer("Order not found", show_alert=True)
            return
        
        if order.status.value != 'active':
            await callback.answer(f"Order is {order.status.value}", show_alert=True)
            return
        
        # Check SMS-Man for OTP
        result = await sms_client.get_sms(order.request_id)
        
        if result['status'] == 'received':
            # Update order with OTP
            order.otp_code = result['code']
            order.status = OrderStatus.RECEIVED
            session.commit()
            
            await callback.message.edit_text(
                f"✅ <b>OTP Received!</b>\n\n"
                f"📱 Order #{order.id}\n"
                f"Service: {order.service_name}\n\n"
                f"🔐 <b>Verification Code:</b>\n"
                f"<code>{result['code']}</code>\n\n"
                f"Use this code to verify your account.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📋 Copy Code", callback_data=f"copy_code_{result['code']}")],
                    [InlineKeyboardButton(text="📋 My Orders", callback_data="menu_orders")],
                    [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")]
                ])
            )
        elif result['status'] == 'waiting':
            await callback.answer("No OTP yet. Waiting for SMS...", show_alert=True)
        else:
            await callback.answer("Error checking OTP. Please try again.", show_alert=True)
            
    except Exception as e:
        logger.error(f"Error refreshing OTP: {e}")
        await callback.answer("Error checking OTP", show_alert=True)
    finally:
        session.close()

# ==================== CANCEL ORDER ====================

@router.callback_query(F.data.startswith("cancel_order_"))
async def cancel_order(callback: CallbackQuery, db_manager, sms_client):
    """Cancel an active order"""
    order_id = int(callback.data.split("_")[2])
    
    # Confirm cancellation
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yes, Cancel", callback_data=f"confirm_cancel_{order_id}"),
         InlineKeyboardButton(text="❌ No, Keep", callback_data=f"view_order_{order_id}")]
    ])
    
    await callback.message.edit_text(
        "⚠️ <b>Cancel Order?</b>\n\n"
        "Are you sure you want to cancel this order?\n"
        "This action cannot be undone.\n\n"
        "Refunds are only available for orders that never received OTP.",
        reply_markup=keyboard
    )

@router.callback_query(F.data.startswith("confirm_cancel_"))
async def confirm_cancel(callback: CallbackQuery, db_manager, sms_client):
    """Confirm order cancellation"""
    order_id = int(callback.data.split("_")[2])
    
    await callback.answer("⏳ Cancelling order...")
    
    session = db_manager.get_session()
    
    try:
        from models.database import Order, OrderStatus, Transaction, TransactionType, TransactionStatus, User
        
        order = session.query(Order).filter_by(id=order_id, user_id=callback.from_user.id).first()
        
        if not order:
            await callback.answer("Order not found", show_alert=True)
            return
        
        if order.status.value != 'active':
            await callback.answer(f"Cannot cancel order with status: {order.status.value}", show_alert=True)
            return
        
        # Cancel with SMS-Man
        try:
            await sms_client.cancel_order(order.request_id)
        except Exception as e:
            logger.error(f"Error cancelling with SMS-Man: {e}")
        
        # Update order status
        order.status = OrderStatus.CANCELLED
        order.cancelled_at = datetime.utcnow()
        
        # Refund user if no OTP received
        if not order.otp_code:
            user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
            if user:
                user.balance += order.cost
                
                # Create refund transaction
                refund_tx = Transaction(
                    user_id=callback.from_user.id,
                    amount=order.cost,
                    type=TransactionType.CREDIT,
                    status=TransactionStatus.COMPLETED,
                    payment_method="refund",
                    description=f"Refund for cancelled order #{order_id}"
                )
                session.add(refund_tx)
                
                await callback.answer("✅ Order cancelled and refunded!", show_alert=True)
        else:
            await callback.answer("✅ Order cancelled (no refund - OTP was received)", show_alert=True)
        
        session.commit()
        
        await callback.message.edit_text(
            f"✅ <b>Order Cancelled</b>\n\n"
            f"Order #{order.id} has been cancelled.\n"
            f"{'💰 Refund of $' + str(order.cost) + ' has been added to your wallet.' if not order.otp_code else ''}\n\n"
            f"Returning to orders...",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 My Orders", callback_data="menu_orders")]
            ])
        )
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error cancelling order: {e}")
        await callback.message.edit_text(
            "❌ Error cancelling order. Please try again.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Retry", callback_data=f"cancel_order_{order_id}")],
                [InlineKeyboardButton(text="📋 My Orders", callback_data="menu_orders")]
            ])
        )
    finally:
        session.close()

# ==================== REQUEST REFUND ====================

@router.callback_query(F.data.startswith("request_refund_"))
async def request_refund(callback: CallbackQuery, db_manager):
    """Request refund for expired order"""
    order_id = int(callback.data.split("_")[2])
    
    session = db_manager.get_session()
    
    try:
        from models.database import Order, OrderStatus
        
        order = session.query(Order).filter_by(id=order_id, user_id=callback.from_user.id).first()
        
        if not order:
            await callback.answer("Order not found", show_alert=True)
            return
        
        if order.status.value != 'expired':
            await callback.answer(f"Cannot request refund for order with status: {order.status.value}", show_alert=True)
            return
        
        # Create refund request (store for admin review)
        # For now, just notify admin
        admin_ids = os.getenv('ADMIN_IDS', '').split(',')
        
        for admin_id in admin_ids:
            if admin_id.strip():
                try:
                    from aiogram import Bot
                    bot = Bot(token=os.getenv('BOT_TOKEN'))
                    
                    admin_msg = (
                        f"💰 <b>Refund Request</b>\n\n"
                        f"User: {callback.from_user.id} (@{callback.from_user.username})\n"
                        f"Order: #{order.id}\n"
                        f"Amount: ${order.cost:.2f}\n"
                        f"Service: {order.service_name}\n"
                        f"Country: {order.country_name}\n\n"
                        f"Expired without OTP."
                    )
                    await bot.send_message(int(admin_id), admin_msg)
                    await bot.session.close()
                except Exception as e:
                    logger.error(f"Error notifying admin: {e}")
        
        await callback.message.edit_text(
            f"💰 <b>Refund Request Submitted</b>\n\n"
            f"Order #{order.id}\n"
            f"Amount: ${order.cost:.2f}\n\n"
            f"Your refund request has been sent to support.\n"
            f"Please wait 24-48 hours for processing.\n\n"
            f"Contact @DeuceVerifySupport for updates.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📋 My Orders", callback_data="menu_orders")],
                [InlineKeyboardButton(text="❓ Contact Support", callback_data="menu_support")]
            ])
        )
        
    except Exception as e:
        logger.error(f"Error requesting refund: {e}")
        await callback.answer("Error submitting refund request", show_alert=True)
    finally:
        session.close()

# ==================== COPY HANDLERS ====================

@router.callback_query(F.data.startswith("copy_number_"))
async def copy_number(callback: CallbackQuery):
    """Copy number to clipboard"""
    number = callback.data.split("_")[2]
    
    await callback.answer(f"📱 Number copied: {number}", show_alert=True)

@router.callback_query(F.data.startswith("copy_code_"))
async def copy_code(callback: CallbackQuery):
    """Copy OTP code to clipboard"""
    code = callback.data.split("_")[2]
    
    await callback.answer(f"🔐 Code copied: {code}", show_alert=True)
