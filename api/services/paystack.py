import requests
import json
from typing import Dict, Optional
from config import settings
import logging

logger = logging.getLogger(__name__)

class PaystackService:
    def __init__(self):
        self.secret_key = settings.paystack_secret_key
        self.public_key = settings.paystack_public_key
        self.base_url = "https://api.paystack.co"
        self.headers = {
            "Authorization": f"Bearer {self.secret_key}",
            "Content-Type": "application/json"
        }
    
    def initialize_transaction(self, email: str, amount: int, user_id: int, telegram_id: int) -> Optional[Dict]:
        """Initialize a Paystack transaction"""
        # Convert NGN to kobo (subunit)
        amount_in_kobo = amount * 100
        
        payload = {
            "email": email,
            "amount": amount_in_kobo,
            "currency": "NGN",
            "callback_url": settings.paystack_callback_url,
            "metadata": {
                "user_id": user_id,
                "telegram_id": telegram_id
            }
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/transaction/initialize",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            result = response.json()
            if result.get("status"):
                return {
                    "authorization_url": result["data"]["authorization_url"],
                    "reference": result["data"]["reference"]
                }
            return None
        except Exception as e:
            logger.error(f"Paystack init error: {e}")
            return None
    
    def verify_transaction(self, reference: str) -> Optional[Dict]:
        """Verify a Paystack transaction"""
        try:
            response = requests.get(
                f"{self.base_url}/transaction/verify/{reference}",
                headers=self.headers,
                timeout=30
            )
            result = response.json()
            if result.get("status") and result["data"]["status"] == "success":
                return result["data"]
            return None
        except Exception as e:
            logger.error(f"Paystack verify error: {e}")
            return None
    
    def handle_webhook(self, payload: bytes, signature: str) -> Optional[Dict]:
        """Verify and handle Paystack webhook"""
        # Verify signature
        import hashlib
        import hmac
        
        expected_signature = hmac.new(
            self.secret_key.encode('utf-8'),
            payload,
            hashlib.sha512
        ).hexdigest()
        
        if signature != expected_signature:
            logger.error("Invalid webhook signature")
            return None
        
        event = json.loads(payload)
        if event.get("event") == "charge.success":
            return event.get("data")
        return None

paystack = PaystackService()
