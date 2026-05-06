from pydantic_settings import BaseSettings
from typing import List

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
