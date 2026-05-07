"""
Handlers module initialization
"""

from .start import router as start_router
from .wallet import router as wallet_router
from .activation import router as activation_router
from .rental import router as rental_router
from .orders import router as orders_router
from .admin import router as admin_router

__all__ = [
    'start_router',
    'wallet_router', 
    'activation_router',
    'rental_router',
    'orders_router',
    'admin_router'
]
