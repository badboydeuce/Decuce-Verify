"""Start and main menu handlers"""

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database.db import SessionLocal
from database.crud import get_or_create_user
from bot.keyboards.main_menu import get_main_menu_keyboard
from bot.keyboards.inline_keyboards import get_back_keyboard, get_main_menu_inline

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command"""
    await state.clear()
    
    db = SessionLocal()
    try:
        # Get or create user
        user = await get_or_create_user(
            db, 
            telegram_id=message.from_user.id,
            username=message.from_user.username
        )
        
        welcome_text = (
            f"🚀 <b>Welcome to DeuceVerify!</b>\n\n"
            f"Your trusted platform for instant virtual numbers and SMS verification.\n\n"
            f"<b>✨ What we offer:</b>\n"
            f"• 📱 <b>One-time SMS Codes</b> - For Telegram, WhatsApp, Gmail & 100+ services\n"
            f"• 🔄 <b>Number Rental</b> - Rent numbers for hours/days/weeks\n"
            f"• ⚡ <b>Instant Delivery</b> - Get codes in seconds\n"
            f"• 💰 <b>Pay with Naira</b> - via Paystack\n\n"
            f"<b>💰 Your Balance:</b> <code>₦{user.balance:,.2f}</code>\n\n"
            f"Use the menu below to get started!"
        )
        
        await message.answer(
            welcome_text,
            reply_markup=get_main_menu_keyboard()
        )
    finally:
        db.close()

@router.message(Command("help"))
async def cmd_help(message: Message):
    """Handle /help command"""
    help_text = (
        "📚 <b>How to Use DeuceVerify</b>\n\n"
        "<b>📱 One-Time SMS Codes:</b>\n"
        "1️⃣ Click 'Buy Number'\n"
        "2️⃣ Select 'One-Time SMS'\n"
        "3️⃣ Choose country & service\n"
        "4️⃣ Pay and receive number\n"
        "5️⃣ Wait for SMS code\n\n"
        "<b>🔄 Number Rental:</b>\n"
        "1️⃣ Click 'Buy Number'\n"
        "2️⃣ Select 'Rent Number'\n"
        "3️⃣ Choose duration (hour/day/week/month)\n"
        "4️⃣ Receive number for multiple SMS\n\n"
        "<b>💳 Payments:</b>\n"
        "• Minimum funding: ₦1,500\n"
        "• Instant wallet topup via Paystack\n"
        "• 1.5% service fee applies\n\n"
        "<b>⏱️ Timeouts:</b>\n"
        "• One-time SMS: 20 minutes\n"
        "• Rental: According to selected duration\n\n"
        "<b>❓ Need help?</b>\n"
        "Contact @DeuceVerifySupport"
    )
    await message.answer(help_text, reply_markup=get_back_keyboard())

@router.message(Command("balance"))
async def cmd_balance(message: Message):
    """Handle /balance command"""
    db = SessionLocal()
    try:
        user = await get_user_by_telegram_id(db, message.from_user.id)
        if user:
            await message.answer(
                f"💰 <b>Your Balance</b>\n\n"
                f"Current balance: <code>₦{user.balance:,.2f}</code>\n\n"
                f"Minimum funding: ₦1,500\n"
                f"Use /fund to add money to your wallet.",
                reply_markup=get_back_keyboard()
            )
        else:
            await message.answer("User not found. Please use /start to register.")
    finally:
        db.close()

@router.message(Command("profile"))
async def cmd_profile(message: Message):
    """Handle /profile command"""
    db = SessionLocal()
    try:
        from database.crud import get_user_stats
        user = await get_user_by_telegram_id(db, message.from_user.id)
        if user:
            stats = get_user_stats(db, user.id)
            profile_text = (
                f"👤 <b>Your Profile</b>\n\n"
                f"🆔 ID: <code>{user.telegram_id}</code>\n"
                f"📝 Username: @{user.username or 'Not set'}\n"
                f"💰 Balance: <code>₦{user.balance:,.2f}</code>\n"
                f"📦 Total Orders: {stats['total_orders']}\n"
                f"⏳ Active Orders: {stats['active_orders']}\n"
                f"💸 Total Spent: <code>₦{stats['total_spent']:,.2f}</code>\n"
                f"📅 Joined: {user.created_at.strftime('%Y-%m-%d')}\n"
            )
            await message.answer(profile_text, reply_markup=get_back_keyboard())
        else:
            await message.answer("User not found. Please use /start to register.")
    finally:
        db.close()

@router.message(F.text == "📱 Buy Number")
async def buy_number_menu(message: Message, state: FSMContext):
    """Handle Buy Number button"""
    from bot.keyboards.inline_keyboards import get_buy_type_keyboard
    await state.clear()
    await message.answer(
        "📱 <b>Select Service Type</b>\n\n"
        "Choose the type of virtual number you need:",
        reply_markup=get_buy_type_keyboard()
    )

@router.message(F.text == "💰 Wallet")
async def wallet_menu(message: Message, state: FSMContext):
    """Handle Wallet button"""
    from bot.keyboards.inline_keyboards import get_wallet_keyboard
    await state.clear()
    db = SessionLocal()
    try:
        user = await get_user_by_telegram_id(db, message.from_user.id)
        if user:
            await message.answer(
                f"💰 <b>Your Wallet</b>\n\n"
                f"Current balance: <code>₦{user.balance:,.2f}</code>\n\n"
                f"Choose an option below:",
                reply_markup=get_wallet_keyboard()
            )
        else:
            await message.answer("User not found. Please use /start to register.")
    finally:
        db.close()

@router.message(F.text == "📋 My Orders")
async def my_orders(message: Message, state: FSMContext):
    """Handle My Orders button"""
    from bot.keyboards.inline_keyboards import get_orders_list_keyboard
    await state.clear()
    db = SessionLocal()
    try:
        from database.crud import get_user_orders
        user = await get_user_by_telegram_id(db, message.from_user.id)
        if user:
            orders = get_user_orders(db, user.id, limit=10)
            if orders:
                await message.answer(
                    "📋 <b>Your Recent Orders</b>\n\n"
                    "Click on an order to view details:",
                    reply_markup=get_orders_list_keyboard(orders)
                )
            else:
                await message.answer(
                    "📋 <b>No Orders Found</b>\n\n"
                    "You haven't placed any orders yet.\n"
                    "Use the 'Buy Number' button to get started!",
                    reply_markup=get_back_keyboard()
                )
        else:
            await message.answer("User not found. Please use /start to register.")
    finally:
        db.close()

@router.message(F.text == "👤 Profile")
async def profile_button(message: Message):
    """Handle Profile button"""
    await cmd_profile(message)

@router.message(F.text == "❓ Support")
async def support_button(message: Message):
    """Handle Support button"""
    from bot.keyboards.inline_keyboards import get_support_keyboard
    support_text = (
        "❓ <b>Support Center</b>\n\n"
        "<b>Frequently Asked Questions:</b>\n"
        "• <b>How to get OTP?</b> - After purchasing, wait 10-60 seconds for SMS\n"
        "• <b>No code received?</b> - Use refresh button or request cancellation\n"
        "• <b>Refund policy?</b> - Refunds issued if no SMS within timeout\n\n"
        "<b>Contact Support:</b>\n"
        "Send a message below and admin will respond.\n\n"
        "Or contact directly: @DeuceVerifySupport"
    )
    await message.answer(support_text, reply_markup=get_support_keyboard())

@router.callback_query(F.data == "back_to_main")
async def back_to_main_callback(callback: CallbackQuery, state: FSMContext):
    """Handle back to main menu"""
    await state.clear()
    await callback.message.delete()
    await callback.message.answer(
        "🏠 <b>Main Menu</b>\n\nChoose an option:",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()

# Import helper functions
from database.crud import get_user_by_telegram_id
