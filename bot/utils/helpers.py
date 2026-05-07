"""
Helper functions for the bot
"""

from datetime import datetime
from typing import Optional

def format_price(amount: float) -> str:
    """Format price with currency symbol"""
    return f"₦{amount:,.2f}"

def format_date(date: datetime) -> str:
    """Format datetime for display"""
    return date.strftime("%Y-%m-%d %H:%M:%S")

def format_countdown(expires_at: datetime) -> str:
    """Format countdown timer"""
    remaining = expires_at - datetime.utcnow()
    if remaining.total_seconds() <= 0:
        return "Expired"
    
    minutes = int(remaining.total_seconds() // 60)
    seconds = int(remaining.total_seconds() % 60)
    return f"{minutes}m {seconds}s"

def validate_amount(amount: str, min_amount: float = 1500) -> Optional[float]:
    """Validate amount input"""
    try:
        amount_float = float(amount)
        if amount_float < min_amount:
            return None
        return amount_float
    except ValueError:
        return None

def mask_phone_number(number: str) -> str:
    """Mask phone number for display"""
    if len(number) <= 8:
        return number
    return f"{number[:4]}***{number[-4:]}"

def get_otp_from_sms(text: str) -> Optional[str]:
    """Extract OTP code from SMS text"""
    import re
    
    # Common OTP patterns
    patterns = [
        r'\b\d{4,8}\b',  # 4-8 digit numbers
        r'code[:\s]*(\d{4,8})',  # code: 1234
        r'OTP[:\s]*(\d{4,8})',  # OTP: 1234
        r'verification[:\s]*(\d{4,8})',  # verification: 1234
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1) if match.lastindex else match.group(0)
    
    return None
