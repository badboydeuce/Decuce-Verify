"""
Inline keyboards for DeuceVerify bot
"""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

def get_back_keyboard(back_data: str = "back_to_main") -> InlineKeyboardMarkup:
    """Simple back button keyboard"""
    builder = InlineKeyboardBuilder()
    builder.button(text="🔙 Back", callback_data=back_data)
    return builder.as_markup()

def get_confirmation_keyboard(action: str, item_id: str = None) -> InlineKeyboardMarkup:
    """Confirmation keyboard with Yes/No buttons"""
    builder = InlineKeyboardBuilder()
    builder.button(text="✅ Yes", callback_data=f"confirm_{action}_{item_id}" if item_id else f"confirm_{action}")
    builder.button(text="❌ No", callback_data="cancel_action")
    builder.adjust(2)
    return builder.as_markup()

def get_country_keyboard(countries: list) -> InlineKeyboardMarkup:
    """Keyboard for country selection"""
    builder = InlineKeyboardBuilder()
    for country in countries[:20]:  # Limit to 20 countries per page
        flag = get_country_flag(country.get('title', ''))
        builder.button(
            text=f"{flag} {country.get('title', 'Unknown')}", 
            callback_data=f"country_{country.get('id')}"
        )
    builder.button(text="🔙 Back", callback_data="back_to_buy_type")
    builder.adjust(2)
    return builder.as_markup()

def get_service_keyboard(services: list, country_id: int) -> InlineKeyboardMarkup:
    """Keyboard for service selection"""
    builder = InlineKeyboardBuilder()
    for service in services[:20]:  # Limit to 20 services per page
        builder.button(
            text=f"📱 {service.get('name', 'Unknown')}", 
            callback_data=f"service_{country_id}_{service.get('id')}"
        )
    builder.button(text="🔙 Back", callback_data="back_to_countries")
    builder.adjust(2)
    return builder.as_markup()

def get_rental_duration_keyboard(country_id: int, service_id: int = None) -> InlineKeyboardMarkup:
    """Keyboard for rental duration selection"""
    builder = InlineKeyboardBuilder()
    durations = [
        ("1 Hour", "hour", "1"),
        ("1 Day", "day", "1"),
        ("3 Days", "day", "3"),
        ("1 Week", "week", "1"),
        ("1 Month", "month", "1")
    ]
    
    for label, duration_type, time in durations:
        if service_id:
            callback = f"rental_duration_{country_id}_{service_id}_{duration_type}_{time}"
        else:
            callback = f"rental_duration_{country_id}_0_{duration_type}_{time}"
        builder.button(text=label, callback_data=callback)
    
    builder.button(text="🔙 Back", callback_data="back_to_rental_country")
    builder.adjust(2)
    return builder.as_markup()

def get_order_action_keyboard(order_id: int, order_type: str) -> InlineKeyboardMarkup:
    """Keyboard for order actions"""
    builder = InlineKeyboardBuilder()
    
    if order_type == "activation":
        builder.button(text="🔄 Refresh OTP", callback_data=f"refresh_otp_{order_id}")
        builder.button(text="📋 Copy Code", callback_data=f"copy_otp_{order_id}")
        builder.button(text="❌ Cancel Order", callback_data=f"cancel_order_{order_id}")
    else:  # rental
        builder.button(text="📨 Check SMS", callback_data=f"check_sms_{order_id}")
        builder.button(text="❌ Close Rental", callback_data=f"close_rental_{order_id}")
    
    builder.button(text="🔙 Back to Orders", callback_data="my_orders")
    builder.adjust(2)
    return builder.as_markup()

def get_orders_list_keyboard(orders: list) -> InlineKeyboardMarkup:
    """Keyboard for orders list"""
    builder = InlineKeyboardBuilder()
    
    for order in orders[:10]:  # Limit to 10 orders
        status_emoji = "⏳" if order.status.value == "pending" else "✅" if order.status.value == "received" else "❌"
        builder.button(
            text=f"{status_emoji} {order.service_name} - {order.number}", 
            callback_data=f"view_order_{order.id}"
        )
    
    builder.button(text="🔙 Back to Menu", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_payment_keyboard(payment_url: str, reference: str) -> InlineKeyboardMarkup:
    """Keyboard for payment"""
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Pay Now", url=payment_url)
    builder.button(text="✅ Verify Payment", callback_data=f"verify_payment_{reference}")
    builder.button(text="🔙 Cancel", callback_data="back_to_wallet")
    builder.adjust(1)
    return builder.as_markup()

def get_transaction_history_keyboard(page: int = 1, total_pages: int = 1) -> InlineKeyboardMarkup:
    """Keyboard for transaction history pagination"""
    builder = InlineKeyboardBuilder()
    
    nav_buttons = []
    if page > 1:
        nav_buttons.append(InlineKeyboardButton(text="◀️ Previous", callback_data=f"tx_page_{page-1}"))
    if page < total_pages:
        nav_buttons.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"tx_page_{page+1}"))
    
    if nav_buttons:
        builder.row(*nav_buttons)
    
    builder.button(text="🔙 Back to Wallet", callback_data="back_to_wallet")
    return builder.as_markup()

def get_wallet_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for wallet menu"""
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Fund Wallet", callback_data="fund_wallet")
    builder.button(text="📜 Transaction History", callback_data="transaction_history")
    builder.button(text="🔙 Back to Menu", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_buy_type_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for buy type selection"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📱 One-Time SMS", callback_data="buy_activation")
    builder.button(text="🔄 Rent Number", callback_data="buy_rental")
    builder.button(text="🔙 Back to Menu", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()

def get_main_menu_inline() -> InlineKeyboardMarkup:
    """Inline version of main menu (alternative to reply keyboard)"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📱 Buy Number", callback_data="buy_number")
    builder.button(text="💰 Wallet", callback_data="wallet_menu")
    builder.button(text="📋 My Orders", callback_data="my_orders")
    builder.button(text="👤 Profile", callback_data="profile")
    builder.button(text="❓ Support", callback_data="support")
    builder.adjust(2)
    return builder.as_markup()

def get_country_flag(country_name: str) -> str:
    """Get emoji flag for country name"""
    flags = {
        'Russia': '🇷🇺', 'USA': '🇺🇸', 'United States': '🇺🇸', 'UK': '🇬🇧', 'United Kingdom': '🇬🇧',
        'China': '🇨🇳', 'India': '🇮🇳', 'Germany': '🇩🇪', 'France': '🇫🇷', 'Japan': '🇯🇵',
        'Brazil': '🇧🇷', 'Canada': '🇨🇦', 'Australia': '🇦🇺', 'Mexico': '🇲🇽', 'Indonesia': '🇮🇩',
        'Turkey': '🇹🇷', 'Nigeria': '🇳🇬', 'Vietnam': '🇻🇳', 'Philippines': '🇵🇭', 'Egypt': '🇪🇬'
    }
    
    for key, flag in flags.items():
        if key.lower() in country_name.lower():
            return flag
    return '🌍'

def get_support_keyboard() -> InlineKeyboardMarkup:
    """Keyboard for support"""
    builder = InlineKeyboardBuilder()
    builder.button(text="📖 FAQ", callback_data="faq")
    builder.button(text="📞 Contact Support", callback_data="contact_support")
    builder.button(text="🔙 Back", callback_data="back_to_main")
    builder.adjust(1)
    return builder.as_markup()
