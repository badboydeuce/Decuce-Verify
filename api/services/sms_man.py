import aiohttp
import asyncio
from typing import Optional, Dict, List, Tuple
from config import settings
import logging

logger = logging.getLogger(__name__)

class SMSManAPI:
    """SMS-Man API wrapper for both Activation and Rent services"""
    
    def __init__(self):
        self.token = settings.sms_man_token
        self.base_url = settings.sms_man_base_url
        self.rent_base_url = "https://api.sms-man.com/rent-api"
        self.profit_margin = settings.profit_margin
    
    def calculate_price(self, base_cost: float) -> float:
        """Add 1.5% profit margin"""
        return round(base_cost * (1 + self.profit_margin / 100), 2)
    
    async def get_balance(self) -> float:
        """Get SMS-Man account balance"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/get-balance", params={"token": self.token}) as resp:
                data = await resp.json()
                return float(data.get("balance", 0))
    
    async def get_countries(self) -> List[Dict]:
        """Get list of all countries"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/countries", params={"token": self.token}) as resp:
                return await resp.json()
    
    async def get_services(self) -> List[Dict]:
        """Get list of all services (applications)"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/applications", params={"token": self.token}) as resp:
                return await resp.json()
    
    async def get_prices(self, country_id: int) -> Dict:
        """Get current prices for activation"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/get-prices", 
                                  params={"token": self.token, "country_id": country_id}) as resp:
                return await resp.json()
    
    # ACTIVATION API Methods
    async def get_activation_number(self, country_id: int, service_id: int) -> Tuple[Optional[str], Optional[int]]:
        """Request a phone number for activation (one-time SMS)"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/get-number", 
                                  params={
                                      "token": self.token,
                                      "country_id": country_id,
                                      "application_id": service_id
                                  }) as resp:
                data = await resp.json()
                if "request_id" in data:
                    return data.get("number"), data.get("request_id")
                return None, None
    
    async def get_activation_sms(self, request_id: int) -> Dict:
        """Get SMS/OTP for activation"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/get-sms",
                                  params={"token": self.token, "request_id": request_id}) as resp:
                return await resp.json()
    
    async def set_activation_status(self, request_id: int, status: str) -> bool:
        """Change activation status: ready/close/reject/used"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/set-status",
                                  params={"token": self.token, "request_id": request_id, "status": status}) as resp:
                data = await resp.json()
                return data.get("success", False)
    
    # RENT API Methods
    async def get_rental_limits(self, country_id: int, rent_type: str, time: str) -> List[Dict]:
        """Get rental number availability and pricing"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.rent_base_url}/limits",
                                  params={
                                      "token": self.token,
                                      "country_id": country_id,
                                      "type": rent_type,  # hour/day/week/month
                                      "time": time
                                  }) as resp:
                data = await resp.json()
                return data.get("limits", [])
    
    async def get_rental_number(self, country_id: int, rent_type: str, time: str, service_id: int = None) -> Tuple[Optional[str], Optional[int]]:
        """Order a number for rent"""
        params = {
            "token": self.token,
            "country_id": country_id,
            "type": rent_type,
            "time": time
        }
        if service_id:
            params["application_id"] = service_id
            params["partial"] = 1  # Partial number for specific service
        
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.rent_base_url}/get-number", params=params) as resp:
                data = await resp.json()
                if "request_id" in data:
                    return data.get("number"), data.get("request_id")
                return None, None
    
    async def get_rental_sms(self, request_id: int) -> Dict:
        """Get the last SMS for rental number"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.rent_base_url}/get-sms",
                                  params={"token": self.token, "request_id": request_id}) as resp:
                return await resp.json()
    
    async def get_all_rental_sms(self, request_id: int) -> List[Dict]:
        """Get all SMS for rental number"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.rent_base_url}/get-all-sms",
                                  params={"token": self.token, "request_id": request_id}) as resp:
                data = await resp.json()
                return data.get("sms", [])
    
    async def set_rental_status(self, request_id: int, status: str) -> bool:
        """Change rental status: cancel/close"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.rent_base_url}/set-status",
                                  params={"token": self.token, "request_id": request_id, "status": status}) as resp:
                data = await resp.json()
                return data.get("success", False)
    
    async def get_all_rental_numbers(self) -> List[Dict]:
        """Get list of all rented numbers"""
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.rent_base_url}/get-all-requests",
                                  params={"token": self.token}) as resp:
                return await resp.json()

sms_man = SMSManAPI()
