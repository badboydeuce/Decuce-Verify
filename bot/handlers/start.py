from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from database.crud import get_or_create_user
from bot.keyboards.main_menu import get_main_menu_keyboard
from bot.keyboards.inline_keyboards import get_back_keyboard

router = Router()

@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    """Handle /start command"""
    await state.clear()
    
    # Get or create user
    user = await get_or_create_user(
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

@router.callback_query(F.data == "back_to_main")
async def back_to_main(callback: CallbackQuery, state: FSMContext):
    """Return to main menu"""
    await state.clear()
    await callback.message.edit_text(
        "🏠 <b>Main Menu</b>\n\nChoose an option:",
        reply_markup=get_main_menu_keyboard()
    )
    await callback.answer()
