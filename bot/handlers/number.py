# Number rental handler
from aiogram import Router, F
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from datetime import datetime, timedelta
import asyncio
from models.database import Order, OrderStatus, Transaction, TransactionType, TransactionStatus

router = Router()

class BuyStates(StatesGroup):
    selecting_country = State()
    selecting_service = State()

@router.callback_query(F.data == "menu_buy")
async def buy_start(callback: CallbackQuery, state: FSMContext, sms_client):
    countries = await sms_client.get_countries()
    keyboard = []
    for country in countries[:15]:  # Show top 15 countries
        keyboard.append([InlineKeyboardButton(text=country.get('title'), callback_data=f"country_{country.get('id')}")])
    keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="back_to_menu")])
    
    await callback.message.edit_text("🌍 Select country:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await state.set_state(BuyStates.selecting_country)

@router.callback_query(BuyStates.selecting_country, F.data.startswith("country_"))
async def select_country(callback: CallbackQuery, state: FSMContext, sms_client):
    country_id = int(callback.data.split("_")[1])
    await state.update_data(country_id=country_id)
    
    services = await sms_client.get_services()
    keyboard = []
    for service in services[:15]:
        keyboard.append([InlineKeyboardButton(text=service.get('name'), callback_data=f"service_{service.get('id')}")])
    keyboard.append([InlineKeyboardButton(text="🔙 Back", callback_data="menu_buy")])
    
    await callback.message.edit_text("📱 Select service:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))
    await state.set_state(BuyStates.selecting_service)

@router.callback_query(BuyStates.selecting_service, F.data.startswith("service_"))
async def confirm_purchase(callback: CallbackQuery, state: FSMContext, sms_client, db_manager):
    service_id = int(callback.data.split("_")[1])
    user_data = await state.get_data()
    country_id = user_data['country_id']
    
    # Get price (simplified - in production, fetch actual price)
    cost = 5.0  # Default price
    
    session = db_manager.get_session()
    try:
        user = session.query(User).filter_by(telegram_id=callback.from_user.id).first()
        if user.balance < cost:
            await callback.message.edit_text(f"❌ Insufficient balance! Need ${cost:.2f}", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💰 Fund Wallet", callback_data="menu_wallet")]]))
            return
        
        # Rent number
        request_id, number = await sms_client.rent_number(country_id, service_id)
        
        # Deduct balance
        user.balance -= cost
        user.total_spent += cost
        user.total_orders += 1
        
        # Create order
        order = Order(
            user_id=user.telegram_id,
            request_id=request_id,
            service_id=service_id,
            service_name="Service",
            country_id=country_id,
            number=number,
            cost=cost,
            expires_at=datetime.utcnow() + timedelta(minutes=10)
        )
        session.add(order)
        session.commit()
        
        await callback.message.edit_text(
            f"✅ Number rented!\n\n📱 Number: <code>{number}</code>\n💰 Cost: ${cost:.2f}\n\n⏳ Waiting for OTP...",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔄 Refresh OTP", callback_data=f"refresh_{order.id}")],
                [InlineKeyboardButton(text="❌ Cancel", callback_data=f"cancel_{order.id}")]
            ])
        )
        await state.clear()
        
        # Start OTP monitoring (simplified)
        asyncio.create_task(monitor_otp(callback.message, order.id, sms_client, db_manager))
        
    finally:
        session.close()

async def monitor_otp(message, order_id, sms_client, db_manager):
    await asyncio.sleep(30)  # Wait 30 seconds
    session = db_manager.get_session()
    try:
        order = session.query(Order).filter_by(id=order_id).first()
        if order and order.status == OrderStatus.ACTIVE:
            result = await sms_client.get_sms(order.request_id)
            if result['status'] == 'received':
                order.otp_code = result['code']
                order.status = OrderStatus.RECEIVED
                session.commit()
                await message.edit_text(f"✅ OTP Received!\n\nCode: <code>{result['code']}</code>")
    finally:
        session.close()
