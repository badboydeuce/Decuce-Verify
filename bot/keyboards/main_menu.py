"""
Main menu reply keyboard
"""

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

def get_main_menu_keyboard() -> ReplyKeyboardMarkup:
    """Get main menu reply keyboard"""
    buttons = [
        [KeyboardButton(text="📱 Buy Number")],
        [KeyboardButton(text="💰 Wallet"), KeyboardButton(text="📋 My Orders")],
        [KeyboardButton(text="👤 Profile"), KeyboardButton(text="❓ Support")]
    ]
    return ReplyKeyboardMarkup(
        keyboard=buttons, 
        resize_keyboard=True,
        input_field_placeholder="Choose an option..."
    )

def get_cancel_keyboard() -> ReplyKeyboardMarkup:
    """Get cancel keyboard for state cancellation"""
    button = [[KeyboardButton(text="❌ Cancel")]]
    return ReplyKeyboardMarkup(
        keyboard=button,
        resize_keyboard=True
    )
