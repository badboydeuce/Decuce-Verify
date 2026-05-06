import os
from typing import List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    """Simple configuration without pydantic"""
    
    def __init__(self):
        # Bot Configuration
        self.BOT_TOKEN = os.getenv("BOT_TOKEN")
        
        # Parse ADMIN_IDS - handles both single ID and comma-separated
        admin_ids_str = os.getenv("ADMIN_IDS", "")
        self.ADMIN_IDS = []
        if admin_ids_str:
            # Split by comma and convert to int
            for id_str in admin_ids_str.split(","):
                id_str = id_str.strip()
                if id_str and id_str.isdigit():
                    self.ADMIN_IDS.append(int(id_str))
        
        # Database
        self.DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://localhost:5432/deuceverify")
        
        # SMS-Man API
        self.SMS_MAN_TOKEN = os.getenv("SMS_MAN_TOKEN")
        self.SMS_MAN_BASE_URL = os.getenv("SMS_MAN_BASE_URL", "https://api.sms-man.com/control")
        self.SMS_MAN_RENT_BASE_URL = "https://api.sms-man.com/rent-api"
        
        # Paystack
        self.PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
        self.PAYSTACK_PUBLIC_KEY = os.getenv("PAYSTACK_PUBLIC_KEY")
        self.PAYSTACK_CALLBACK_URL = os.getenv("PAYSTACK_CALLBACK_URL")
        
        # Flask
        self.FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "default-dev-key-change-in-production")
        self.FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
        
        # App Settings
        self.PROFIT_MARGIN = float(os.getenv("PROFIT_MARGIN", "1.5"))
        self.MINIMUM_FUNDING_NGN = int(os.getenv("MINIMUM_FUNDING_NGN", "1500"))
        self.ACTIVATION_TIMEOUT_SECONDS = int(os.getenv("ACTIVATION_TIMEOUT_SECONDS", "1200"))
        self.RENTAL_TIMEOUT_HOURS = int(os.getenv("RENTAL_TIMEOUT_HOURS", "24"))
    
    # Properties for backward compatibility (code that expects lowercase attributes)
    @property
    def bot_token(self) -> Optional[str]:
        return self.BOT_TOKEN
    
    @property
    def admin_ids(self) -> List[int]:
        return self.ADMIN_IDS
    
    @property
    def database_url(self) -> str:
        return self.DATABASE_URL
    
    @property
    def sms_man_token(self) -> Optional[str]:
        return self.SMS_MAN_TOKEN
    
    @property
    def sms_man_base_url(self) -> str:
        return self.SMS_MAN_BASE_URL
    
    @property
    def paystack_secret_key(self) -> Optional[str]:
        return self.PAYSTACK_SECRET_KEY
    
    @property
    def paystack_public_key(self) -> Optional[str]:
        return self.PAYSTACK_PUBLIC_KEY
    
    @property
    def paystack_callback_url(self) -> Optional[str]:
        return self.PAYSTACK_CALLBACK_URL
    
    @property
    def flask_secret_key(self) -> str:
        return self.FLASK_SECRET_KEY
    
    @property
    def flask_port(self) -> int:
        return self.FLASK_PORT
    
    @property
    def profit_margin(self) -> float:
        return self.PROFIT_MARGIN
    
    @property
    def minimum_funding_ngn(self) -> int:
        return self.MINIMUM_FUNDING_NGN
    
    @property
    def activation_timeout_seconds(self) -> int:
        return self.ACTIVATION_TIMEOUT_SECONDS
    
    @property
    def rental_timeout_hours(self) -> int:
        return self.RENTAL_TIMEOUT_HOURS

# Create singleton instance
settings = Config()

# Validation
if not settings.BOT_TOKEN:
    raise ValueError("❌ BOT_TOKEN is required in .env file")

print(f"✅ Configuration loaded successfully!")
print(f"   Bot Token: {settings.BOT_TOKEN[:20]}...")
print(f"   Admin IDs: {settings.ADMIN_IDS}")
print(f"   Database: {settings.DATABASE_URL[:50]}...")
print(f"   Flask Port: {settings.FLASK_PORT}")
print(f"   Profit Margin: {settings.PROFIT_MARGIN}%")
