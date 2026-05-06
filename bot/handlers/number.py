# Number rental handler
"""
Number rental handler with 2x profit margin
Shows customers the marked-up price
"""

from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta
import asyncio
from loguru import logger

router = Router()

class BuyNumberStates(StatesGroup):
    selecting_country = State()
    selecting_service = State()
    confirming_purchase = State()

@router.callback_query(F.data == "menu_buy")
async def buy_number_start(callback: CallbackQuery, state: FSMContext, sms_client):
    """Start number purchase flow"""
    await callback.answer("Loading countries...")
    
    try:
        countries = await sms_client.get_all_countries()
        
        # Cache countries for later use
        await state.update_data(countries=countries)
        
        # Build country selection keyboard
        keyboard = []
        row = []
        for country in countries[:20]:  # Show top 20 countries
            row.append(InlineKeyboardButton(
                text=f"{country['flag']} {country['name']}",
                callback_data=f"buy_country_{country['id']}"
            ))
            if len(row) == 2:
                keyboard.append(row)
                row = []
        if row:
            keyboard.append(row)
        
        keyboard.append([InlineKeyboardButton(text="🔍 Search Country", callback_data="search_country")])
        keyboard.append([InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_menu")])
        
        await callback.message.edit_text(
            "🌍 <b>Select Country</b>\n\n"
            "Choose the country for your virtual number:\n\n"
            "💡 <b>Tip:</b> Higher success rate countries may cost more\n"
            "💰 <b>Our prices include a small markup for service fees</b>\n\n"
            "Select a country:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await state.set_state(BuyNumberStates.selecting_country)
        
    except Exception as e:
        logger.error(f"Error loading countries: {e}")
        await callback.message.edit_text(
            "❌ Failed to load countries. Please try again.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Retry", callback_data="menu_buy")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")]
            ])
        )

@router.callback_query(BuyNumberStates.selecting_country, F.data.startswith("buy_country_"))
async def select_country_for_buy(callback: CallbackQuery, state: FSMContext, sms_client):
    """Handle country selection and show services"""
    country_id = int(callback.data.split("_")[2])
    
    await callback.answer("Loading services...")
    await state.update_data(selected_country_id=country_id)
    
    # Get country name
    user_data = await state.get_data()
    countries = user_data.get('countries', [])
    country = next((c for c in countries if c['id'] == country_id), None)
    country_name = country['name'] if country else "Selected"
    country_flag = country['flag'] if country else "🌍"
    
    try:
        # Get services with prices for this country
        services = await sms_client.get_all_services()
        prices = await sms_client.get_prices_for_all_services(country_id)
        
        # Build service list with prices
        service_list = []
        country_prices = prices.get(country_id, {})
        
        for service in services:
            price_info = country_prices.get(service['id'], {})
            if price_info and price_info.get('count', 0) > 0:
                service_list.append({
                    'id': service['id'],
                    'name': service['name'],
                    'icon': service['icon'],
                    'price': price_info['cost'],
                    'original_price': price_info.get('original_cost', 0),
                    'profit': price_info.get('profit', 0),
                    'available': price_info.get('count', 0)
                })
        
        # Sort by price (cheapest first)
        service_list.sort(key=lambda x: x['price'])
        
        if not service_list:
            await callback.message.edit_text(
                f"❌ No services available in {country_flag} {country_name}\n\n"
                f"Please try another country.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Try Another Country", callback_data="menu_buy")],
                    [InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")]
                ])
            )
            return
        
        await state.update_data(service_list=service_list)
        
        # Build service selection keyboard
        keyboard = []
        for service in service_list[:15]:  # Show top 15 services
            keyboard.append([InlineKeyboardButton(
                text=f"{service['icon']} {service['name']} - ${service['price']:.2f}",
                callback_data=f"buy_service_{service['id']}"
            )])
        
        keyboard.append([InlineKeyboardButton(text="🔍 Search Service", callback_data="search_service_in_country")])
        keyboard.append([InlineKeyboardButton(text="🔙 Back to Countries", callback_data="menu_buy")])
        
        await callback.message.edit_text(
            f"{country_flag} <b>{country_name}</b>\n\n"
            f"📱 <b>Available Services</b>\n\n"
            f"Showing {len(service_list)} services\n"
            f"💰 <b>Prices include our service fee</b>\n\n"
            f"Select a service:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard)
        )
        await state.set_state(BuyNumberStates.selecting_service)
        
    except Exception as e:
        logger.error(f"Error loading services: {e}")
        await callback.message.edit_text(
            "❌ Failed to load services. Please try again.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Retry", callback_data=f"buy_country_{country_id}")],
                [InlineKeyboardButton(text="🔙 Back", callback_data="menu_buy")]
            ])
        )

@router.callback_query(BuyNumberStates.selecting_service, F.data.startswith("buy_service_"))
async def confirm_service_purchase(callback: CallbackQuery, state: FSMContext, sms_client, db_manager):
    """Show confirmation before purchasing"""
    service_id = int(callback.data.split("_")[2])
    
    user_data = await state.get_data()
    service_list = user_data.get('service_list', [])
    service = next((s for s in service_list if s['id'] == service_id), None)
    
    if not service:
        await callback.answer("Service not found", show_alert=True)
        return
    
    country_id = user_data.get('selected_country_id')
    countries = user_data.get('countries', [])
    country = next((c for c in countries if c['id'] == country_id), None)
    
    await state.update_data(selected_service=service)
    
    # Get user's balance
    session = db_manager.get_session()
    try:
        from models.database import User
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        user_balance = user.balance if user else 0
        
        # Show price breakdown
        original_price = service.get('original_price', service['price'] / 2)
        markup_percent = ((service['price'] - original_price) / original_price * 100) if original_price > 0 else 100
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Confirm Purchase", callback_data="confirm_buy")],
            [InlineKeyboardButton(text="💰 Fund Wallet", callback_data="menu_wallet")],
            [InlineKeyboardButton(text="🔙 Back to Services", callback_data=f"buy_country_{country_id}")]
        ])
        
        await callback.message.edit_text(
            f"📱 <b>Order Summary</b>\n\n"
            f"🌍 Country: {country['flag']} {country['name']}\n"
            f"📱 Service: {service['icon']} {service['name']}\n\n"
            f"💰 <b>Price: ${service['price']:.2f}</b>\n"
            f"├─ Network fee: ${original_price:.2f}\n"
            f"└─ Service fee: ${service['price'] - original_price:.2f} ({markup_percent:.0f}%)\n\n"
            f"📊 Availability: {service.get('available', 'Good')} numbers\n"
            f"⏱️ Validity: 10 minutes\n"
            f"⭐ Success rate: 92-96%\n\n"
            f"💳 <b>Your balance: ${user_balance:.2f}</b>\n\n"
            f"{'✅ Sufficient funds!' if user_balance >= service['price'] else '❌ Insufficient funds! Please fund your wallet.'}\n\n"
            f"Click confirm to rent this number.",
            reply_markup=keyboard
        )
        await state.set_state(BuyNumberStates.confirming_purchase)
        
    finally:
        session.close()

@router.callback_query(BuyNumberStates.confirming_purchase, F.data == "confirm_buy")
async def execute_purchase(callback: CallbackQuery, state: FSMContext, sms_client, db_manager):
    """Execute the number purchase with profit markup"""
    await callback.answer("⏳ Processing your request...")
    
    user_data = await state.get_data()
    selected_service = user_data.get('selected_service')
    country_id = user_data.get('selected_country_id')
    
    if not selected_service:
        await callback.message.edit_text("❌ Session expired. Please start over.")
        await state.clear()
        return
    
    session = db_manager.get_session()
    
    try:
        from models.database import User, Order, OrderStatus, Transaction, TransactionType, TransactionStatus
        
        # Check balance
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        cost = selected_service['price']  # This is the marked-up price customers pay
        
        if user.balance < cost:
            await callback.message.edit_text(
                f"❌ Insufficient balance!\n\n"
                f"Required: ${cost:.2f}\n"
                f"Your balance: ${user.balance:.2f}\n"
                f"Shortage: ${cost - user.balance:.2f}\n\n"
                f"Please fund your wallet first.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💰 Fund Wallet", callback_data="menu_wallet")],
                    [InlineKeyboardButton(text="🔙 Back", callback_data="menu_buy")]
                ])
            )
            return
        
        # Rent number from SMS-Man (uses original price internally)
        request_id, number, actual_country, original_cost, marked_up_cost = await sms_client.rent_number(
            country_id=country_id,
            service_id=selected_service['id']
        )
        
        logger.info(f"Purchase - User: {callback.from_user.id} | Service: {selected_service['name']} | "
                   f"Original: ${original_cost:.2f} | Sold: ${marked_up_cost:.2f} | Profit: ${marked_up_cost - original_cost:.2f}")
        
        # Deduct balance (customer pays marked up price)
        user.balance -= marked_up_cost
        user.total_spent += marked_up_cost
        user.total_orders += 1
        
        # Create order with both costs for tracking
        order = Order(
            user_id=user.telegram_id,
            request_id=request_id,
            service_id=selected_service['id'],
            service_name=selected_service['name'],
            country_id=country_id,
            country_name=user_data.get('countries', [{}])[0].get('name', 'Unknown'),
            number=number,
            cost=marked_up_cost,  # Store what customer paid
            original_cost=original_cost,  # Store what we paid (if you add this field)
            profit=marked_up_cost - original_cost,  # Store profit (if you add this field)
            status=OrderStatus.ACTIVE,
            expires_at=datetime.utcnow() + timedelta(seconds=600)
        )
        session.add(order)
        
        # Create transaction record
        transaction = Transaction(
            user_id=user.telegram_id,
            amount=marked_up_cost,
            type=TransactionType.DEBIT,
            status=TransactionStatus.COMPLETED,
            description=f"Rented {selected_service['name']} number in {country_id}",
            order_id=order.id
        )
        session.add(transaction)
        session.commit()
        
        await state.clear()
        
        # Send success message with profit info (hidden from customer)
        profit_percent = ((marked_up_cost - original_cost) / original_cost * 100) if original_cost > 0 else 0
        
        await callback.message.edit_text(
            f"✅ <b>Number Rented Successfully!</b>\n\n"
            f"📱 <b>Number:</b> <code>{number}</code>\n"
            f"📱 Service: {selected_service['name']}\n"
            f"💰 Paid: ${marked_up_cost:.2f}\n"
            f"⏱️ Expires in: 10 minutes\n\n"
            f"🔐 <b>Waiting for OTP...</b>\n"
            f"⏳ Please check SMS from {selected_service['name']}\n"
            f"The code will appear here automatically.\n\n"
            f"💡 Tip: Click 'Refresh OTP' if you don't see the code",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Refresh OTP", callback_data=f"refresh_otp_{order.id}")],
                [InlineKeyboardButton(text="📋 Copy Number", callback_data=f"copy_number_{number}")],
                [InlineKeyboardButton(text="❌ Cancel Order", callback_data=f"cancel_order_{order.id}")],
                [InlineKeyboardButton(text="📋 My Orders", callback_data="menu_orders")]
            ])
        )
        
        # Start OTP monitoring
        asyncio.create_task(monitor_otp_for_order(callback.message, order.id, sms_client, db_manager))
        
        # Log profit for analytics (optional)
        logger.info(f"PROFIT: Order #{order.id} - Customer paid ${marked_up_cost:.2f}, Cost ${original_cost:.2f}, "
                   f"Profit ${marked_up_cost - original_cost:.2f} ({profit_percent:.0f}%)")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Purchase error: {e}")
        await callback.message.edit_text(
            f"❌ Failed to rent number: {str(e)}\n\nPlease try again later.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Retry", callback_data="menu_buy")],
                [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_menu")]
            ])
        )
    finally:
        session.close()

async def monitor_otp_for_order(message, order_id, sms_client, db_manager):
    """Monitor for OTP arrival"""
    session = db_manager.get_session()
    try:
        from models.database import Order, OrderStatus
        
        await asyncio.sleep(3)  # Initial delay
        
        for attempt in range(30):  # Monitor for 5 minutes
            await asyncio.sleep(10)
            
            order = session.query(Order).filter_by(id=order_id).first()
            if not order or order.status != OrderStatus.ACTIVE:
                break
            
            result = await sms_client.get_sms(order.request_id)
            
            if result['status'] == 'received':
                order.otp_code = result['code']
                order.status = OrderStatus.RECEIVED
                session.commit()
                
                await message.edit_text(
                    f"✅ <b>OTP Received!</b>\n\n"
                    f"📱 Number: <code>{order.number}</code>\n"
                    f"🔐 <b>Verification Code:</b>\n"
                    f"<code>{result['code']}</code>\n\n"
                    f"Use this code to verify your account.\n"
                    f"Number expires in remaining time.",
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="📋 Copy Code", callback_data=f"copy_code_{result['code']}")],
                        [InlineKeyboardButton(text="📋 Copy Number", callback_data=f"copy_number_{order.number}")],
                        [InlineKeyboardButton(text="📋 My Orders", callback_data="menu_orders")]
                    ])
                )
                return
        
        # Timeout
        order = session.query(Order).filter_by(id=order_id).first()
        if order and order.status == OrderStatus.ACTIVE:
            order.status = OrderStatus.EXPIRED
            session.commit()
            await message.edit_text(
                f"⏰ <b>Order Expired</b>\n\n"
                f"Number: {order.number}\n"
                f"Service: {order.service_name}\n\n"
                f"No OTP received within timeout period.\n\n"
                f"Please contact support for refund.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="🔄 Try Again", callback_data="menu_buy")],
                    [InlineKeyboardButton(text="💰 Request Refund", callback_data=f"request_refund_{order.id}")],
                    [InlineKeyboardButton(text="❓ Support", callback_data="menu_support")]
                ])
            )
    except Exception as e:
        logger.error(f"OTP monitoring error: {e}")
    finally:
        session.close()
        session.close()
