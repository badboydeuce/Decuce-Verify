# Inline keyboards
"""
Keyboards module initialization
"""

from .main_menu import get_main_menu_keyboard
from .inline_keyboards import (
    get_back_keyboard,
    get_confirmation_keyboard,
    get_country_keyboard,
    get_service_keyboard,
    get_rental_duration_keyboard,
    get_order_action_keyboard,
    get_orders_list_keyboard,
    get_payment_keyboard,
    get_transaction_history_keyboard,
    get_wallet_keyboard,
    get_buy_type_keyboard,
    get_main_menu_inline,
    get_support_keyboard
)

__all__ = [
    'get_main_menu_keyboard',
    'get_back_keyboard',
    'get_confirmation_keyboard',
    'get_country_keyboard',
    'get_service_keyboard',
    'get_rental_duration_keyboard',
    'get_order_action_keyboard',
    'get_orders_list_keyboard',
    'get_payment_keyboard',
    'get_transaction_history_keyboard',
    'get_wallet_keyboard',
    'get_buy_type_keyboard',
    'get_main_menu_inline',
    'get_support_keyboard'
]
