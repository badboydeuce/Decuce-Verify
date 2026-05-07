"""
Rental handlers for DeuceVerify bot
Handles number rental for multiple SMS reception over time
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
    update_order_status
)
from database.models import OrderStatus, OrderType
from api.services.sms_man import sms_man
from config import settings

logger = logging.getLogger(__name__)
router = Router()

# ============ FSM STATES ============

class RentalStates(StatesGroup):
    """Rental FSM states"""
    selecting_country = State()
    selecting_service = State()
    selecting_duration = State()
    confirming_purchase = State()
    viewing_messages = State()

# ============ HELPER FUNCTIONS ============

def format_price(amount: float) -> str:
    """Format price with currency"""
    return f"₦{amount:,.2f}"

def format_duration(duration_type: str, time_value: str) -> str:
    """Format duration for display"""
    duration_map = {
        'hour': 'hour' if int(time_value) == 1 else 'hours',
        'day': 'day' if int(time_value) == 1 else 'days',
        'week': 'week' if int(time_value) == 1 else 'weeks',
        'month': 'month' if int(time_value) == 1 else 'months'
    }
    return f"{time_value} {duration_map.get(duration_type, duration_type)}"

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

def get_rental_duration_keyboard(country_id: int, service_id: int = None) -> InlineKeyboardMarkup:
    """Get rental duration selection keyboard"""
    keyboard = []
    
    durations = [
        ("1 Hour", "hour", "1"),
        ("3 Hours", "hour", "3"),
        ("1 Day", "day", "1"),
        ("3 Days", "day", "3"),
        ("1 Week", "week", "1"),
        ("2 Weeks", "week", "2"),
        ("1 Month", "month", "1")
    ]
    
    for label, duration_type, time_value in durations:
        if service_id:
            callback = f"rental_duration_{country_id}_{service_id}_{duration_type}_{time_value}"
        else:
            callback = f"rental_duration_{country_id}_0_{duration_type}_{time_value}"
        keyboard.append([InlineKeyboardButton(text=label, callback_data=callback)])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="back_to_rental_services")])
    keyboard.append([InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_rental_control_keyboard(order_id: int) -> InlineKeyboardMarkup:
    """Get rental control keyboard for active rental"""
    keyboard = [
        [InlineKeyboardButton(text="📨 Check New SMS", callback_data=f"check_rental_sms_{order_id}")],
        [InlineKeyboardButton(text="📜 View All Messages", callback_data=f"view_all_sms_{order_id}")],
        [InlineKeyboardButton(text="❌ Close Rental", callback_data=f"close_rental_{order_id}")],
        [InlineKeyboardButton(text="🔙 Back to Orders", callback_data="my_orders")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

def get_messages_keyboard(order_id: int, messages: list, page: int = 1) -> InlineKeyboardMarkup:
    """Get messages pagination keyboard"""
    keyboard = []
    items_per_page = 5
    total_pages = (len(messages) + items_per_page - 1) // items_per_page
    
    # Navigation buttons
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Previous", callback_data=f"sms_page_{order_id}_{page-1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"sms_page_{order_id}_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton(text="🔄 Refresh", callback_data=f"refresh_rental_{order_id}")])
    keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data=f"view_order_{order_id}")])
    
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ============ BUY RENTAL FLOW ============

@router.callback_query(F.data == "buy_rental")
async def buy_rental_start(callback: CallbackQuery, state: FSMContext):
    """Start rental purchase flow"""
    await state.set_state(RentalStates.selecting_country)
    
    # Fetch countries from SMS-Man API
    try:
        countries = await sms_man.get_countries()
        
        if not countries:
            await callback.message.edit_text(
                "❌ <b>Service Error</b>\n\n"
                "Unable to fetch countries list. Please try again later.",
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        await state.update_data(countries=countries)
        
        # Build countries keyboard
        keyboard = []
        for country in countries[:20]:
            flag = get_country_flag(country.get('title', ''))
            keyboard.append([
                InlineKeyboardButton(
                    text=f"{flag} {country.get('title', 'Unknown')}",
                    callback_data=f"rental_country_{country.get('id')}"
                )
            ])
        keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="back_to_buy_type")])
        
        countries_text = "🌍 <b>Select a Country for Rental</b>\n\n"
        countries_text += "Choose the country for your rented number:\n\n"
        countries_text += f"<i>Showing {len(countries)} countries</i>"
        
        await callback.message.edit_text(
            countries_text,
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error fetching countries for rental: {e}")
        await callback.message.edit_text(
            "❌ <b>Service Error</b>\n\n"
            "Unable to fetch countries. Please try again later.",
            parse_mode="HTML"
        )
        await callback.answer()

@router.callback_query(F.data.startswith("rental_country_"))
async def rental_country_selected(callback: CallbackQuery, state: FSMContext):
    """Handle country selection for rental"""
    country_id = int(callback.data.split("_")[2])
    
    await state.set_state(RentalStates.selecting_service)
    await state.update_data(selected_country_id=country_id)
    
    # Get country name
    data = await state.get_data()
    countries = data.get('countries', [])
    country_name = next((c.get('title') for c in countries if c.get('id') == country_id), 'Unknown')
    await state.update_data(selected_country_name=country_name)
    
    # Ask if they want to specify a service or rent any number
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Specific Service", callback_data=f"rental_with_service_{country_id}")],
        [InlineKeyboardButton(text="🔄 Any Number (No Service)", callback_data=f"rental_no_service_{country_id}")],
        [InlineKeyboardButton(text="🔙 Back to Countries", callback_data="buy_rental")]
    ])
    
    await callback.message.edit_text(
        f"🌍 <b>Service Selection</b>\n\n"
        f"Country: {get_country_flag(country_name)} {country_name}\n\n"
        f"Do you want a number specifically for a certain service,\n"
        f"or will any number work?\n\n"
        f"<i>Note: Service-specific numbers have higher success rates.</i>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data.startswith("rental_with_service_"))
async def rental_with_service(callback: CallbackQuery, state: FSMContext):
    """Handle rental with specific service"""
    country_id = int(callback.data.split("_")[3])
    await state.update_data(rental_with_service=True)
    
    # Fetch services
    try:
        services = await sms_man.get_services()
        
        if not services:
            await callback.message.edit_text(
                "❌ <b>Service Error</b>\n\n"
                "Unable to fetch services. Please try again.",
                parse_mode="HTML"
            )
            await callback.answer()
            return
        
        await state.update_data(services=services)
        
        # Build services keyboard
        keyboard = []
        for service in services[:20]:
            keyboard.append([
                InlineKeyboardButton(
                    text=f"📱 {service.get('name', 'Unknown')}",
                    callback_data=f"rental_service_{country_id}_{service.get('id')}"
                )
            ])
        keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data=f"rental_country_{country_id}")])
        
        await callback.message.edit_text(
            f"📱 <b>Select a Service</b>\n\n"
            f"Choose the service you need the number for:",
            parse_mode="HTML",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error fetching services: {e}")
        await callback.message.edit_text(
            "❌ <b>Service Error</b>\n\n"
            "Unable to fetch services. Please try again.",
            parse_mode="HTML"
        )
        await callback.answer()

@router.callback_query(F.data.startswith("rental_no_service_"))
async def rental_no_service(callback: CallbackQuery, state: FSMContext):
    """Handle rental without specific service"""
    country_id = int(callback.data.split("_")[3])
    await state.update_data(rental_with_service=False, selected_service_id=0, selected_service_name="Any Service")
    
    await state.set_state(RentalStates.selecting_duration)
    
    # Show duration selection
    await callback.message.edit_text(
        f"⏰ <b>Select Rental Duration</b>\n\n"
        f"Choose how long you want to rent the number:",
        parse_mode="HTML",
        reply_markup=get_rental_duration_keyboard(country_id)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("rental_service_"))
async def rental_service_selected(callback: CallbackQuery, state: FSMContext):
    """Handle service selection for rental"""
    parts = callback.data.split("_")
    country_id = int(parts[2])
    service_id = int(parts[3])
    
    # Get service name
    data = await state.get_data()
    services = data.get('services', [])
    service_name = next((s.get('name') for s in services if s.get('id') == service_id), 'Unknown')
    
    await state.update_data(
        selected_service_id=service_id,
        selected_service_name=service_name
    )
    await state.set_state(RentalStates.selecting_duration)
    
    # Show duration selection
    await callback.message.edit_text(
        f"⏰ <b>Select Rental Duration</b>\n\n"
        f"Service: {service_name}\n\n"
        f"Choose how long you want to rent the number:",
        parse_mode="HTML",
        reply_markup=get_rental_duration_keyboard(country_id, service_id)
    )
    await callback.answer()

@router.callback_query(F.data.startswith("rental_duration_"))
async def rental_duration_selected(callback: CallbackQuery, state: FSMContext):
    """Handle duration selection and show pricing"""
    parts = callback.data.split("_")
    country_id = int(parts[2])
    service_id = int(parts[3])
    duration_type = parts[4]
    time_value = parts[5]
    
    await state.update_data(
        rental_duration_type=duration_type,
        rental_time_value=time_value
    )
    
    # Get pricing from SMS-Man Rent API
    try:
        limits = await sms_man.get_rental_limits(country_id, duration_type, time_value)
        
        # Find pricing for this country/service
        base_price = 0
        for limit in limits:
            if str(country_id) == limit.get('country_id'):
                base_price = float(limit.get('cost', 0))
                break
        
        # If no price found, use a default or show error
        if base_price == 0 and limits:
            base_price = float(limits[0].get('cost', 5.0))
        
        # Apply 1.5% profit margin
        final_price = base_price * (1 + settings.profit_margin / 100)
        
        await state.update_data(
            base_price=base_price,
            final_price=final_price
        )
        
        data = await state.get_data()
        country_name = data.get('selected_country_name', 'Unknown')
        service_name = data.get('selected_service_name', 'Any Service')
        
        duration_text = format_duration(duration_type, time_value)
        
        confirmation_text = (
            f"✅ <b>Confirm Rental Purchase</b>\n\n"
            f"<b>Details:</b>\n"
            f"• Country: {get_country_flag(country_name)} {country_name}\n"
            f"• Service: 📱 {service_name}\n"
            f"• Duration: {duration_text}\n\n"
            f"<b>Price Breakdown:</b>\n"
            f"• Base Price: {format_price(base_price)}\n"
            f"• Service Fee (1.5%): {format_price(final_price - base_price)}\n"
            f"• <b>Total: {format_price(final_price)}</b>\n\n"
            f"<i>The number will be available for the entire rental period.\n"
            f"You can check messages anytime during this period.</i>\n\n"
            f"Click Confirm to proceed with purchase."
        )
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Confirm Purchase", callback_data="confirm_rental_purchase")],
            [InlineKeyboardButton(text="🔙 Back to Duration", callback_data=f"rental_country_{country_id}")],
            [InlineKeyboardButton(text="🏠 Main Menu", callback_data="back_to_main")]
        ])
        
        await callback.message.edit_text(
            confirmation_text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error getting rental price: {e}")
        await callback.message.edit_text(
            "❌ <b>Pricing Error</b>\n\n"
            "Unable to fetch pricing. Please try again later.",
            parse_mode="HTML"
        )
        await callback.answer()

@router.callback_query(F.data == "confirm_rental_purchase")
async def confirm_rental_purchase(callback: CallbackQuery, state: FSMContext):
    """Process the rental purchase"""
    data = await state.get_data()
    
    user_id = callback.from_user.id
    country_id = data.get('selected_country_id')
    country_name = data.get('selected_country_name')
    service_id = data.get('selected_service_id', 0)
    service_name = data.get('selected_service_name', 'Any Service')
    duration_type = data.get('rental_duration_type')
    time_value = data.get('rental_time_value')
    final_price = data.get('final_price')
    rental_with_service = data.get('rental_with_service', False)
    
    # Calculate expiry time
    expiry_map = {
        'hour': timedelta(hours=int(time_value)),
        'day': timedelta(days=int(time_value)),
        'week': timedelta(weeks=int(time_value)),
        'month': timedelta(days=int(time_value) * 30)
    }
    expires_at = datetime.utcnow() + expiry_map.get(duration_type, timedelta(hours=1))
    
    # Validate required data
    if not all([country_id, final_price]):
        await callback.message.edit_text(
            "❌ <b>Invalid Session</b>\n\n"
            "Please start the rental process again.",
            parse_mode="HTML"
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
                f"Please fund your wallet first.",
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
            "⏳ <b>Processing Rental Purchase...</b>\n\n"
            "Requesting rental number from provider...",
            parse_mode="HTML"
        )
        
        # Request rental number from SMS-Man API
        try:
            if rental_with_service and service_id > 0:
                # Get service-specific number
                number, request_id = await sms_man.get_rental_number(
                    country_id, duration_type, time_value, service_id
                )
            else:
                # Get any number
                number, request_id = await sms_man.get_rental_number(
                    country_id, duration_type, time_value
                )
            
            if not number or not request_id:
                await processing_msg.edit_text(
                    "❌ <b>No Numbers Available</b>\n\n"
                    "No rental numbers available for this selection.\n\n"
                    "Please try different country, service, or duration.",
                    parse_mode="HTML"
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
                description=f"Number rental - {service_name} ({duration_type}/{time_value})",
                status="completed"
            )
            
            # Create order
            duration_str = f"{duration_type}_{time_value}"
            order = create_order(
                db=db,
                user_id=user.id,
                order_type="rental",
                service_id=str(service_id),
                service_name=service_name,
                country_id=str(country_id),
                country_name=country_name,
                number=number,
                request_id=str(request_id),
                cost=final_price,
                expires_at=expires_at,
                rental_duration=duration_str
            )
            
            # Format number for display
            masked_number = number[:4] + "***" + number[-4:] if len(number) > 8 else number
            duration_text = format_duration(duration_type, time_value)
            
            success_text = (
                f"✅ <b>Rental Purchase Successful!</b>\n\n"
                f"<b>Order ID:</b> #{order.id}\n"
                f"<b>Number:</b> <code>{masked_number}</code>\n"
                f"<b>Service:</b> {service_name}\n"
                f"<b>Country:</b> {get_country_flag(country_name)} {country_name}\n"
                f"<b>Duration:</b> {duration_text}\n"
                f"<b>Amount Paid:</b> {format_price(final_price)}\n"
                f"<b>New Balance:</b> {format_price(user.balance)}\n\n"
                f"<b>⏰ Expires:</b> {expires_at.strftime('%Y-%m-%d %H:%M:%S')} UTC\n\n"
                f"<i>You can receive unlimited SMS during this period.\n"
                f"Use the buttons below to check messages.</i>"
            )
            
            await processing_msg.edit_text(
                success_text,
                parse_mode="HTML",
                reply_markup=get_rental_control_keyboard(order.id)
            )
            
        except Exception as e:
            logger.error(f"Error requesting rental number: {e}")
            await processing_msg.edit_text(
                "❌ <b>Purchase Failed</b>\n\n"
                "Unable to get rental number. Please try again later.",
                parse_mode="HTML"
            )
        
        await callback.answer()
        
    except Exception as e:
        logger.error(f"Error in confirm_rental_purchase: {e}")
        await callback.message.edit_text(
            "❌ <b>Purchase Error</b>\n\n"
            "An unexpected error occurred. Please try again.",
            parse_mode="HTML"
        )
    finally:
        db.close()

# ============ RENTAL MANAGEMENT ============

@router.callback_query(F.data.startswith("check_rental_sms_"))
async def check_rental_sms(callback: CallbackQuery):
    """Check for new SMS on rental number"""
    order_id = int(callback.data.split("_")[3])
    
    await callback.answer("📨 Checking for new messages...")
    
    db = SessionLocal()
    try:
        order = get_order(db, order_id, callback.from_user.id)
        if not order:
            await callback.message.edit_text("❌ Order not found.")
            return
        
        # Fetch latest SMS from SMS-Man Rent API
        result = await sms_man.get_rental_sms(int(order.request_id))
        
        if result and result.get("sms"):
            sms_data = result["sms"]
            message_text = sms_data.get("message", "")
            code = sms_data.get("code", "")
            time_received = sms_data.get("time", "")
            
            # Try to extract OTP if present
            import re
            if not code:
                # Look for common OTP patterns
                patterns = [r'\b\d{4,8}\b', r'code[:\s]*(\d{4,8})', r'OTP[:\s]*(\d{4,8})']
                for pattern in patterns:
                    match = re.search(pattern, message_text, re.IGNORECASE)
                    if match:
                        code = match.group(1) if match.lastindex else match.group(0)
                        break
            
            response_text = (
                f"📨 <b>Latest SMS Received</b>\n\n"
                f"<b>Number:</b> <code>{order.number}</code>\n"
                f"<b>Time:</b> {time_received or 'Just now'}\n"
                f"<b>Message:</b>\n"
                f"<code>{message_text[:500]}</code>\n\n"
            )
            
            if code:
                response_text += f"<b>📋 Extracted Code:</b> <code>{code}</code>\n\n"
            
            response_text += f"<i>Use the buttons below to view all messages or refresh.</i>"
            
            await callback.message.edit_text(
                response_text,
                parse_mode="HTML",
                reply_markup=get_rental_control_keyboard(order_id)
            )
        else:
            await callback.message.answer(
                f"📭 <b>No New Messages</b>\n\n"
                f"No SMS received yet for number {order.number}.\n\n"
                f"<i>Messages will appear here when received.</i>",
                parse_mode="HTML"
            )
            
    except Exception as e:
        logger.error(f"Error checking rental SMS: {e}")
        await callback.message.answer(
            "❌ <b>Error Checking Messages</b>\n\n"
            "Unable to fetch SMS. Please try again.",
            parse_mode="HTML"
        )
    finally:
        db.close()

@router.callback_query(F.data.startswith("view_all_sms_"))
async def view_all_sms(callback: CallbackQuery, state: FSMContext):
    """View all SMS received on rental number"""
    order_id = int(callback.data.split("_")[3])
    
    await callback.answer("📜 Fetching all messages...")
    
    db = SessionLocal()
    try:
        order = get_order(db, order_id, callback.from_user.id)
        if not order:
            await callback.message.edit_text("❌ Order not found.")
            return
        
        # Fetch all SMS from SMS-Man Rent API
        result = await sms_man.get_all_rental_sms(int(order.request_id))
        
        if result and result.get("sms"):
            messages = result["sms"]
            
            # Store messages in state for pagination
            await state.update_data(rental_messages=messages, current_order_id=order_id)
            
            # Display first page
            await display_messages_page(callback, state, order_id, messages, 1)
        else:
            await callback.message.edit_text(
                f"📭 <b>No Messages Yet</b>\n\n"
                f"No SMS received for number {order.number}.\n\n"
                f"<i>Messages will appear here when they arrive.</i>",
                parse_mode="HTML",
                reply_markup=get_rental_control_keyboard(order_id)
            )
            
    except Exception as e:
        logger.error(f"Error viewing all SMS: {e}")
        await callback.message.answer(
            "❌ <b>Error Fetching Messages</b>\n\n"
            "Unable to fetch SMS history. Please try again.",
            parse_mode="HTML"
        )
    finally:
        db.close()

async def display_messages_page(callback: CallbackQuery, state: FSMContext, order_id: int, messages: list, page: int):
    """Display a page of messages"""
    items_per_page = 3
    start_idx = (page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    page_messages = messages[start_idx:end_idx]
    
    if not page_messages:
        await callback.answer("No more messages", show_alert=True)
        return
    
    total_pages = (len(messages) + items_per_page - 1) // items_per_page
    
    messages_text = f"📜 <b>SMS History (Page {page}/{total_pages})</b>\n\n"
    messages_text += f"<b>Number:</b> <code>{messages[0].get('number', 'Unknown')}</code>\n\n"
    
    for i, msg in enumerate(page_messages, start=start_idx + 1):
        msg_time = msg.get('time', 'Unknown time')
        msg_text = msg.get('message', 'No content')[:200]
        msg_code = msg.get('code', '')
        
        messages_text += f"<b>{i}. 📅 {msg_time}</b>\n"
        messages_text += f"<code>{msg_text}</code>\n"
        if msg_code:
            messages_text += f"<b>Code:</b> <code>{msg_code}</code>\n"
        messages_text += f"{'─' * 30}\n\n"
    
    # Build pagination keyboard
    keyboard = []
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Previous", callback_data=f"sms_page_{order_id}_{page-1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"sms_page_{order_id}_{page+1}"))
    
    if nav_buttons:
        keyboard.append(nav_buttons)
    
    keyboard.append([InlineKeyboardButton(text="🔄 Refresh", callback_data=f"view_all_sms_{order_id}")])
    keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data=f"view_order_{order_id}")])
    
    await callback.message.edit_text(
        messages_text,
        parse_mode="HTML",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
    )

@router.callback_query(F.data.startswith("sms_page_"))
async def sms_page_callback(callback: CallbackQuery, state: FSMContext):
    """Handle SMS pagination"""
    parts = callback.data.split("_")
    order_id = int(parts[2])
    page = int(parts[3])
    
    data = await state.get_data()
    messages = data.get('rental_messages', [])
    
    if messages:
        await display_messages_page(callback, state, order_id, messages, page)
    else:
        await callback.answer("Session expired. Please refresh.", show_alert=True)

@router.callback_query(F.data.startswith("refresh_rental_"))
async def refresh_rental(callback: CallbackQuery):
    """Refresh rental view"""
    order_id = int(callback.data.split("_")[2])
    await view_all_sms(callback)

@router.callback_query(F.data.startswith("close_rental_"))
async def close_rental(callback: CallbackQuery):
    """Close rental early"""
    order_id = int(callback.data.split("_")[2])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yes, Close Rental", callback_data=f"confirm_close_rental_{order_id}")],
        [InlineKeyboardButton(text="❌ No, Keep It", callback_data=f"view_order_{order_id}")]
    ])
    
    await callback.message.edit_text(
        "⚠️ <b>Close Rental Early?</b>\n\n"
        "Are you sure you want to close this rental?\n\n"
        "<i>Note: No refund will be issued for early closure.\n"
        "The number will be released immediately.</i>",
        parse_mode="HTML",
        reply_markup=keyboard
    )
    await callback.answer()

@router.callback_query(F.data.startswith("confirm_close_rental_"))
async def confirm_close_rental(callback: CallbackQuery):
    """Confirm rental closure"""
    order_id = int(callback.data.split("_")[3])
    
    db = SessionLocal()
    try:
        order = get_order(db, order_id, callback.from_user.id)
        if order and order.status == OrderStatus.PENDING:
            # Cancel in SMS-Man API
            await sms_man.set_rental_status(int(order.request_id), "close")
            
            # Update order status
            update_order_status(db, order_id, "cancelled")
            
            await callback.message.edit_text(
                f"✅ <b>Rental Closed</b>\n\n"
                f"Rental #{order_id} has been closed.\n"
                f"The number has been released.\n\n"
                f"Thank you for using DeuceVerify!",
                parse_mode="HTML",
                reply_markup=get_rental_control_keyboard(order_id)
            )
        else:
            await callback.message.edit_text(
                "❌ Cannot close rental in its current state.",
                parse_mode="HTML"
            )
    except Exception as e:
        logger.error(f"Error closing rental: {e}")
        await callback.message.edit_text(
            "❌ Error closing rental. Please try again.",
            parse_mode="HTML"
        )
    finally:
        db.close()
    await callback.answer()

@router.callback_query(F.data == "back_to_rental_services")
async def back_to_rental_services(callback: CallbackQuery, state: FSMContext):
    """Go back to service selection"""
    data = await state.get_data()
    country_id = data.get('selected_country_id')
    
    if country_id:
        await rental_country_selected(callback, state)
    else:
        await buy_rental_start(callback, state)
