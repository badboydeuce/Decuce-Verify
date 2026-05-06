from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Get main menu reply keyboard"""
    buttons = [
        [KeyboardButton(text="📱 Buy Number")],
        [KeyboardButton(text="💰 Wallet"), KeyboardButton(text="📋 My Orders")],
        [KeyboardButton(text="👤 Profile"), KeyboardButton(text="❓ Support")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_buy_type_keyboard() -> InlineKeyboardMarkup:
    """Get buy type selection keyboard"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📱 One-Time SMS Code", callback_data="buy_activation")
    builder.button(text="🔄 Rent Number", callback_data="buy_rental")
    builder.button(text="🔙 Back", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_activation_keyboard(country_id: int = None, service_id: int = None) -> InlineKeyboardMarkup:
    """Get activation flow keyboard"""
    builder = InlineKeyboardBuilder()
    if country_id is None:
        builder.button(text="🌍 Select Country", callback_data="select_activation_country")
    elif service_id is None:
        builder.button(text="📱 Select Service", callback_data="select_activation_service")
    else:
        builder.button(text="✅ Confirm Purchase", callback_data="confirm_activation")
    builder.button(text="🔙 Back", callback_data="back_to_buy_type")
    builder.adjust(1)
    return builder.as_markup()

def get_wallet_keyboard() -> InlineKeyboardMarkup:
    """Get wallet menu keyboard"""
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Fund Wallet (Paystack)", callback_data="fund_wallet")
    builder.button(text="📜 Transaction History", callback_data="transaction_history")
    builder.button(text="🔙 Back", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_back_keyboard() -> InlineKeyboardMarkup:
    """Simple back button"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Back to Menu", callback_data="back_to_main")
    return builder.as_markup()
