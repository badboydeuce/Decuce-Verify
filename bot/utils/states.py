"""
FSM states for the bot
"""

from aiogram.fsm.state import State, StatesGroup

class Form(StatesGroup):
    """Form states for various flows"""
    # Wallet
    funding_amount = State()
    
    # Activation
    activation_country = State()
    activation_service = State()
    activation_confirm = State()
    
    # Rental
    rental_country = State()
    rental_service = State()
    rental_duration = State()
    rental_confirm = State()
    
    # Support
    support_message = State()
