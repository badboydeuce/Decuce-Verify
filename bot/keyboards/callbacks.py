"""
Callback data constants for inline keyboards
"""

from aiogram.filters.callback_data import CallbackData

class CountryCallback(CallbackData, prefix="country"):
    """Country selection callback"""
    country_id: int

class ServiceCallback(CallbackData, prefix="service"):
    """Service selection callback"""
    country_id: int
    service_id: int

class RentalDurationCallback(CallbackData, prefix="rental"):
    """Rental duration callback"""
    country_id: int
    service_id: int
    duration_type: str  # hour, day, week, month
    time: str  # 1, 3, 7, etc.

class OrderCallback(CallbackData, prefix="order"):
    """Order action callback"""
    action: str  # refresh, copy, cancel, view, check_sms, close
    order_id: int

class PaymentCallback(CallbackData, prefix="payment"):
    """Payment callback"""
    action: str  # verify, cancel
    reference: str

class TransactionCallback(CallbackData, prefix="tx"):
    """Transaction history callback"""
    page: int

class AdminCallback(CallbackData, prefix="admin"):
    """Admin actions callback"""
    action: str
    user_id: int = None
    order_id: int = None

class NavigationCallback(CallbackData, prefix="nav"):
    """Navigation callbacks"""
    action: str  # back_to_main, back_to_wallet, etc.
