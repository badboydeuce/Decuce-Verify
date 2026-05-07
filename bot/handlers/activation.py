"""
Activation handlers for DeuceVerify bot
Handles one-time SMS verification number purchases
"""

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta
import asyncio
import logging

from database.db import SessionLocal
from database.crud import (
    get_user_by_telegram_id,
    update_user_balance,
    create_transaction,
    create_order,
    get_order,
    update_order_status,
    update_order_otp
)
from database.models import OrderStatus, OrderType
from api.services.sms_man import sms_man
from config import settings

logger = logging.getLogger(__name__)
router = Router()

# ============ FSM STATES ============

class ActivationStates(StatesGroup):
    """Activation FSM states"""
    selecting_country = State()
    selecting_service = State()
    confirming_purchase = State()
    waiting_for_otp = State()

# ============ HELPER FUNCTIONS ============

def format_price(amount: float) -> str:
    """Format price with currency"""
    return f"₦{amount:,.2f}"

def get_country_flag(country_name: str) -> str:
    """Get emoji flag for country"""
    flags = {
        'Russia': '🇷🇺', 'USA': '🇺🇸', 'United States': '🇺🇸', 
        'UK': '🇬🇧', 'United Kingdom': '🇬🇧', 'China': '🇨🇳',
        'India': '🇮🇳', 'Germany': '🇩🇪', 'France': '🇫🇷',
        'Japan': '🇯🇵', 'Brazil': '🇧🇷', 'Canada': '🇨🇦',
        'Australia': '🇦🇺', 'Mexico': '🇲🇽', 'Indonesia': '🇮🇩',
        'Turkey': '🇹🇷', 'Nigeria': '🇳🇬', 'Vietnam': '🇻🇳',
        'Philippines': '🇵🇭', 'Egypt': '🇪🇬', 'South Africa': '🇿🇦'
    }
    
    for key, flag in flags.items():
        if key.lower() in country_name.lower():
            return flag
    return '🌍'

def get_activation_keyboard(country_id: int = None, service_id: int = None) -> InlineKeyboardMarkup:
    """Get activation flow keyboard"""
    builder = []
    
    if country_id is None:
        builder.append([InlineKeyboardButton(text="🌍 Select Country", callback_data="select_activation_country")])
    elif service_id is None:
        builder.append([InlineKeyboardButton(text="📱 Select Service", callback_data="select_activation_service")])
    else:
        builder.append([InlineKeyboardButton(text="✅ Confirm Purchase", callback_data="confirm_activation")])
    
    builder.append([InlineKeyboardButton(text="🔙 Back", callback_data="back_to_buy_type")])
    
    return InlineKeyboardMarkup(inline_keyboard=builder)

def get_countries_keyboard(countries: list) -> InlineKeyboardMarkup:
    """Get countries selection keyboard"""
    keyboard = []
    
    for country in countries[:20]:  # Limit to 20 per page
        flag = get_country_flag(country.get('title', ''))
        keyboard.append([
            InlineKeyboardButton(
                text=f"{flag} {country.get('title', 'Unknown')}",
                callback_data=f"activation_country_{country.get('id')}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="back_to_buy_type")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_services_keyboard(services: list, country_id: int) -> InlineKeyboardMarkup:
    """Get services selection keyboard"""
    keyboard = []
    
    for service in services[:20]:  # Limit to 20 per page
        keyboard.append([
            InlineKeyboardButton(
                text=f"📱 {service.get('name', 'Unknown')}",
                callback_data=f"activation_service_{country_id}_{service.get('id')}"
            )
        ])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="back_to_activation_countries")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_otp_refresh_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Get OTP refresh keyboard"""
    keyboard = [
        [InlineKeyboardButton(text="🔄 Refresh OTP", callback_data=f"refresh_otp_{order_id}")],
        [InlineKeyboardButton(text="📋 Copy Code", callback_data=f"copy_otp_{order_id}")],
        [InlineKeyboardButton(text="❌ Cancel Order", callback_data=f"cancel_activation_{order_id}")],
        [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_main")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ============ BUY ACTIVATION FLOW ============

@router.callback_query(F.data == "buy_activation")
async def buy_activation_start(callback: CallbackQuery, state: FSMContext):
    """Start activation purchase flow"""
    await state.set_state(ActivationStates.selecting_country)
    
    # Fetch countries from SMS-Man API
    try:
        countries = await sms_man.get_countries()
        
        if not countries:
            await callback.message.edit_text(
                "❌ <b>Service Error</b>\n\n"
                "Unable to fetch countries list. Please try again later.",
                parse_mode="HTML",
                reply_markup=get_activation_keyboard()
            )
            await callback.answer()
            return
        
        # Store countries in state for later use
        await state.update_data(countries=countries)
        
        countries_text = "🌍 <b>Select a Country</b>\n\n"
        countries_text += "Choose the country for your virtual number:\n\n"
        countries_text += f"<i>Showing {len(countries)} countries</i>"
        
        await callback.message.edit_text(
            countries_text,
            parse_mode="HTML",
            reply_markup=get_countries_keyboard(countries)
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error fetching countries: {e}")
        await callback.message.edit_text(
            "❌ <b>Service Error</b>\n\n"
            "Unable to fetch countries. Please try again later.",
            parse_mode="HTML",
            reply_markup=get_activation_keyboard()
        )
        await callback.answer()

@router.callback_query(F.data.startswith("activation_country_"))
async def activation_country_selected(callback: CallbackQuery, state: FSMContext):
    """Handle country selection"""
    country_id = int(callback.data.split("_")[2])
    
    await state.set_state(ActivationStates.selecting_service)
    await state.update_data(selected_country_id=country_id)
    
    # Get country name
    data = await state.get_data()
    countries = data.get('countries', [])
    country_name = next((c.get('title') for c in countries if c.get('id') == country_id), 'Unknown')
    await state.update_data(selected_country_name=country_name)
    
    # Fetch services from SMS-Man API
    try:
        services = await sms_man.get_services()
        
        if not services:
            await callback.message.edit_text(
                "❌ <b>Service Error</b>\n\n"
                "Unable to fetch services list. Please try again later.",
                parse_mode="HTML",
                reply_markup=get_activation_keyboard()
            )
            await callback.answer()
            return
        
        await state.update_data(services=services)
        
        services_text = f"📱 <b>Select a Service</b>\n\n"
        services_text += f"Country: {get_country_flag(country_name)} {country_name}\n\n"
        services_text += f"Choose the service you need verification for:\n\n"
        services_text += f"<i>Showing {len(services)} services</i>"
        
        await callback.message.edit_text(
            services_text,
            parse_mode="HTML",
            reply_markup=get_services_keyboard(services, country_id)
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error fetching services: {e}")
        await callback.message.edit_text(
            "❌ <b>Service Error</b>\n\n"
            "Unable to fetch services. Please try again later.",
            parse_mode="HTML",
            reply_markup=get_activation_keyboard()
        )
        await callback.answer()

@router.callback_query(F.data.startswith("activation_service_"))
async def activation_service_selected(callback: CallbackQuery, state: FSMContext):
    """Handle service selection and show price"""
    parts = callback.data.split("_")
    country_id = int(parts[2])
    service_id = int(parts[3])
    
    await state.update_data(selected_service_id=service_id)
    
    # Get service name
    data = await state.get_data()
    services = data.get('services', [])
    service_name = next((s.get('name') for s in services if s.get('id') == service_id), 'Unknown')
    await state.update_data(selected_service_name=service_name)
    
    # Get price from SMS-Man API
    try:
        prices = await sms_man.get_prices(country_id)
        
        # Find price for selected service
        base_price = 0
        if str(service_id) in prices:
            base_price = float(prices[str(service_id)]['cost'])
        elif str(service_id) in prices.get(str(country_id), {}):
            base_price = float(prices[str(country_id)][str(service_id)]['cost'])
        
        # Apply 1.5% profit margin
        final_price = base_price * (1 + settings.profit_margin / 100)
        
        await state.update_data(
            base_price=base_price,
            final_price=final_price
        )
        
        # Show price confirmation
        country_name = data.get('selected_country_name', 'Unknown')
        
        confirmation_text = (
            f"✅ <b>Confirm Purchase</b>\n\n"
            f"<b>Details:</b>\n"
            f"• Country: {get_country_flag(country_name)} {country_name}\n"
            f"• Service: 📱 {service_name}\n"
            f"• Service ID: {service_id}\n\n"
            f"<b>Price Breakdown:</b>\n"
            f"• Base Price: {format_price(base_price)}\n"
            f"• Service Fee (1.5%): {format_price(final_price - base_price)}\n"
            f"• <b>Total: {format_price(final_price)}</b>\n\n"
            f"<i>Click Confirm to proceed with purchase.</i>"
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Confirm Purchase", callback_data="confirm_activation_purchase")],
            [InlineKeyboardButton(text="🔙 Back to Services", callback_data=f"back_to_activation_services_{country_id}")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
        ])
        
        await callback.message.edit_text(
            confirmation_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error getting price: {e}")
        await callback.message.edit_text(
            "❌ <b>Price Error</b>\n\n"
            "Unable to fetch price. Please try again later.",
            parse_mode="HTML",
            reply_markup=get_activation_keyboard()
        )
        await callback.answer()

@router.callback_query(F.data == "confirm_activation_purchase")
async def confirm_activation_purchase(callback: CallbackQuery, state: FSMContext):
    """Process the activation purchase"""
    data = await state.get_data()
    
    user_id = callback.from_user.id
    country_id = data.get('selected_country_id')
    country_name = data.get('selected_country_name')
    service_id = data.get('selected_service_id')
    service_name = data.get('selected_service_name')
    final_price = data.get('final_price')
    
    # Validate required data
    if not all([country_id, service_id, final_price]):
        await callback.message.edit_text(
            "❌ <b>Invalid Session</b>\n\n"
            "Please start the purchase process again.",
            parse_mode="HTML",
            reply_markup=get_activation_keyboard()
        )
        await callback.answer()
        return
    
    # Check user balance
    db = SessionLocal()
    try:
        user = get_user_by_telegram_id(db, user_id)
        if not user:
            await callback.message.edit_text(
                "❌ <b>User Not Found</b>\n\n"
                "Please use /start to register first.",
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        # Check sufficient balance
        if user.balance < final_price:
            await callback.message.edit_text(
                f"❌ <b>Insufficient Balance</b>\n\n"
                f"Required: {format_price(final_price)}\n"
                f"Your balance: {format_price(user.balance)}\n\n"
                f"Please fund your wallet first.\n"
                f"Minimum funding: {format_price(settings.minimum_funding_ngn)}",
                parse_mode="HTML",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💰 Fund Wallet", callback_data="fund_wallet")],
                    [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_buy_type")]
                ])
            )
            await callback.answer()
            return
        
        # Show processing message
        processing_msg = await callback.message.edit_text(
            "⏳ <b>Processing Purchase...</b>\n\n"
            "Requesting virtual number from provider...",
            parse_mode="HTML"
        )
        
        # Request number from SMS-Man API
        try:
            number, request_id = await sms_man.get_activation_number(country_id, service_id)
            
            if not number or not request_id:
                await processing_msg.edit_text(
                    "❌ <b>No Numbers Available</b>\n\n"
                    "No virtual numbers available for this country/service combination.\n\n"
                    "Please try a different country or service.",
                    parse_mode="HTML",
                    reply_markup=get_activation_keyboard()
                )
                await callback.answer()
                return
            
            # Deduct balance
            user = update_user_balance(db, user.id, final_price, "debit")
            
            # Create transaction record
            transaction = create_transaction(
                db=db,
                user_id=user.id,
                amount=final_price,
                transaction_type="debit",
                description=f"Activation number purchase - {service_name} ({country_name})",
                status="completed"
            )
            
            # Create order
            expires_at = datetime.utcnow() + timedelta(seconds=settings.activation_timeout_seconds)
            order = create_order(
                db=db,
                user_id=user.id,
                order_type="activation",
                service_id=str(service_id),
                service_name=service_name,
                country_id=str(country_id),
                country_name=country_name,
                number=number,
                request_id=str(request_id),
                cost=final_price,
                expires_at=expires_at
            )
            
            # Format number for display (mask middle digits)
            masked_number = number[:4] + "***" + number[-4:] if len(number) > 8 else number
            
            success_text = (
                f"✅ <b>Purchase Successful!</b>\n\n"
                f"<b>Order ID:</b> #{order.id}\n"
                f"<b>Number:</b> <code>{masked_number}</code>\n"
                f"<b>Service:</b> {service_name}\n"
                f"<b>Country:</b> {get_country_flag(country_name)} {country_name}\n"
                f"<b>Amount Paid:</b> {format_price(final_price)}\n"
                f"<b>New Balance:</b> {format_price(user.balance)}\n\n"
                f"<b>⏰ Timeout:</b> {settings.activation_timeout_seconds // 60} minutes\n\n"
                f"<i>Waiting for SMS. The OTP will appear here automatically...</i>"
            )
            
            await processing_msg.edit_text(
                success_text,
                parse_mode="HTML",
                reply_markup=get_otp_refresh_keyboard(order.id)
            )
            
            # Start background OTP polling
            asyncio.create_task(poll_otp_background(order.id, callback.message.chat.id))
            
        except Exception as e:
            logger.error(f"Error requesting number: {e}")
            await processing_msg.edit_text(
                "❌ <b>Purchase Failed</b>\n\n"
                "Unable to get virtual number. Please try again later.",
                parse_mode="HTML",
                reply_markup=get_activation_keyboard()
            )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in confirm_activation_purchase: {e}")
        await callback.message.edit_text(
            "❌ <b>Purchase Error</b>\n\n"
            "An unexpected error occurred. Please try again.",
            parse_mode="HTML"
        )
    finally:
        db.close()

# ============ OTP POLLING ============

async def poll_otp_background(order_id: int, chat_id: int):
    """Background task to poll for OTP"""
    from bot.main import bot
    
    max_attempts = settings.activation_timeout_seconds // 5  # Poll every 5 seconds
    attempts = 0
    
    while attempts < max_attempts:
        await asyncio.sleep(5)
        attempts += 1
        
        db = SessionLocal()
        try:
            order = get_order(db, order_id)
            if not order or order.status != OrderStatus.PENDING:
                # Order cancelled or expired
                break
            
            # Check if expired
            if datetime.utcnow() > order.expires_at:
                update_order_status(db, order_id, "expired")
                await bot.send_message(
                    chat_id,
                    f"⏰ <b>Order Expired</b>\n\n"
                    f"Order #{order_id} has expired without receiving OTP.\n\n"
                    f"Please create a new order.",
                    parse_mode="HTML"
                )
                break
            
            # Fetch OTP from SMS-Man
            try:
                result = await sms_man.get_activation_sms(int(order.request_id))
                
                if result.get("sms_code"):
                    # OTP received!
                    otp_code = result["sms_code"]
                    update_order_otp(db, order_id, otp_code)
                    
                    await bot.send_message(
                        chat_id,
                        f"🔐 <b>OTP Received!</b>\n\n"
                        f"<b>Order #{order_id}</b>\n"
                        f"<b>Number:</b> <code>{order.number}</code>\n"
                        f"<b>OTP Code:</b> <code>{otp_code}</code>\n\n"
                        f"<i>Use this code for verification. The number will expire soon.</i>",
                        parse_mode="HTML",
                        reply_markup=get_otp_refresh_keyboard(order_id)
                    )
                    break
                    
                elif result.get("error_code") != "wait_sms":
                    # Error occurred
                    logger.error(f"SMS-Man error: {result}")
                    
            except Exception as e:
                logger.error(f"Error polling OTP: {e}")
                
        finally:
            db.close()

# ============ OTP REFRESH ============

@router.callback_query(F.data.startswith("refresh_otp_"))
async def refresh_otp(callback: CallbackQuery):
    """Manual refresh OTP"""
    order_id = int(callback.data.split("_")[2])
    
    await callback.answer("🔄 Checking for OTP...")
    
    db = SessionLocal()
    try:
        order = get_order(db, order_id, callback.from_user.id)
        if not order:
            await callback.message.edit_text(
                "❌ Order not found.",
                parse_mode="HTML"
            )
            return
        
        # Fetch OTP
        result = await sms_man.get_activation_sms(int(order.request_id))
        
        if result.get("sms_code"):
            otp_code = result["sms_code"]
            update_order_otp(db, order_id, otp_code)
            
            await callback.message.edit_text(
                f"🔐 <b>OTP Code</b>\n\n"
                f"<b>Order #{order.id}</b>\n"
                f"<b>Number:</b> <code>{order.number}</code>\n"
                f"<b>OTP Code:</b> <code>{otp_code}</code>\n\n"
                f"<i>Use this code for verification.</i>",
                parse_mode="HTML",
                reply_markup=get_otp_refresh_keyboard(order_id)
            )
        else:
            # Still waiting
            await callback.message.answer(
                f"⏳ Still waiting for SMS...\n\n"
                f"Please wait a few more seconds.",
                parse_mode="HTML"
            )
            
    except Exception as e:
        logger.error(f"Error refreshing OTP: {e}")
        await callback.message.answer(
            "❌ Error checking OTP. Please try again.",
            parse_mode="HTML"
        )
    finally:
        db.close()

@router.callback_query(F.data.startswith("copy_otp_"))
async def copy_otp(callback: CallbackQuery):
    """Copy OTP code"""
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

@router.callback_query(F.data.startswith("cancel_activation_"))
async def cancel_activation(callback: CallbackQuery):
    """Cancel activation order"""
    order_id = int(callback.data.split("_")[2])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yes, Cancel", callback_data=f"confirm_cancel_activation_{order_id}")],
        [InlineKeyboardButton(text="❌ No, Keep", callback_data=f"view_order_{order_id}")]
    ])
    
    await callback.message.edit_text(
        "⚠️ <b>Cancel Order</b>\n\n"
        "Are you sure you want to cancel this order?\n\n"
        "<i>Note: Refunds are only issued if no SMS was received within the timeout period.</i>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_cancel_activation_"))
async def confirm_cancel_activation(callback: CallbackQuery):
    """Confirm activation cancellation"""
    order_id = int(callback.data.split("_")[3])
    
    db = SessionLocal()
    try:
        order = get_order(db, order_id, callback.from_user.id)
        if order and order.status == OrderStatus.PENDING:
            # Cancel in SMS-Man API
            await sms_man.set_activation_status(int(order.request_id), "cancel")
            
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
                    f"✅ <b>Order Cancelled</b>\n\n"
                    f"Order #{order_id} has been cancelled.\n"
                    f"Refund of {format_price(order.cost)} has been issued.\n\n"
                    f"Your new balance: {format_price(user.balance + order.cost)}",
                    parse_mode="HTML",
                    reply_markup=get_activation_keyboard()
                )
            else:
                await callback.message.edit_text(
                    f"✅ <b>Order Cancelled</b>\n\n"
                    f"Order #{order_id} has been cancelled.\n"
                    f"No refund issued as OTP was already received.",
                    parse_mode="HTML",
                    reply_markup=get_activation_keyboard()
                )
        else:
            await callback.message.edit_text(
                "❌ Cannot cancel order in its current state.",
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Error cancelling activation: {e}")
        await callback.message.edit_text(
            "❌ Error cancelling order. Please try again.",
            parse_mode="HTML"
        )
    finally:
        db.close()
    await callback.answer()

@router.callback_query(F.data == "back_to_activation_countries")
async def back_to_activation_countries(callback: CallbackQuery, state: FSMContext):
    """Go back to country selection"""
    await buy_activation_start(callback, state)

@router.callback_query(F.data.startswith("back_to_activation_services_"))
async def back_to_activation_services(callback: CallbackQuery, state: FSMContext):
    """Go back to service selection"""
    country_id = int(callback.data.split("_")[3])
    
    data = await state.get_data()
    services = data.get('services', [])
    
    services_text = f"📱 <b>Select a Service</b>\n\n"
    services_text += f"Choose the service you need verification for:\n\n"
    
    await callback.message.edit_text(
        services_text,
        parse_mode="HTML",
        reply_markup=get_services_keyboard(services, country_id)
    )
    await callback.answer()
