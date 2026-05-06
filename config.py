import os
from typing import List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Try to use pydantic-settings if available, otherwise fallback to os.getenv
try:
    from pydantic_settings import BaseSettings
    
    class Settings(BaseSettings):
        # Bot
        bot_token: str
        admin_ids: List[int]
        
        # Database
        database_url: str
        
        # SMS-Man
        sms_man_token: str
        sms_man_base_url: str = "https://api.sms-man.com/control"
        
        # Paystack
        paystack_secret_key: str
        paystack_public_key: str
        paystack_callback_url: str
        
        # Flask
        flask_secret_key: str
        flask_port: int = 5000
        
        # App
        profit_margin: float = 1.5
        minimum_funding_ngn: int = 1500
        activation_timeout_seconds: int = 1200
        rental_timeout_hours: int = 24
        
        class Config:
            env_file = ".env"
            env_file_encoding = "utf-8"
    
    settings = Settings()
    
except ImportError:
    # Fallback to simple config without pydantic-settings
    class Settings:
        def __init__(self):
            # Bot
            self.bot_token = os.getenv("BOT_TOKEN")
            self.admin_ids = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
            
            # Database
            self.database_url = os.getenv("DATABASE_URL")
            
            # SMS-Man
            self.sms_man_token = os.getenv("SMS_MAN_TOKEN")
            self.sms_man_base_url = os.getenv("SMS_MAN_BASE_URL", "https://api.sms-man.com/control")
            
            # Paystack
            self.paystack_secret_key = os.getenv("PAYSTACK_SECRET_KEY")
            self.paystack_public_key = os.getenv("PAYSTACK_PUBLIC_KEY")
            self.paystack_callback_url = os.getenv("PAYSTACK_CALLBACK_URL")
            
            # Flask
            self.flask_secret_key = os.getenv("FLASK_SECRET_KEY")
            self.flask_port = int(os.getenv("FLASK_PORT", "5000"))
            
            # App
            self.profit_margin = float(os.getenv("PROFIT_MARGIN", "1.5"))
            self.minimum_funding_ngn = int(os.getenv("MINIMUM_FUNDING_NGN", "1500"))
            self.activation_timeout_seconds = int(os.getenv("ACTIVATION_TIMEOUT_SECONDS", "1200"))
            self.rental_timeout_hours = int(os.getenv("RENTAL_TIMEOUT_HOURS", "24"))
    
    settings = Settings()
