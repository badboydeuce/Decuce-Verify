"""
SMS-Man API Service for DeuceVerify
Handles both Activation (one-time SMS) and Rent (number rental) APIs
"""

import aiohttp
import requests
import asyncio
from typing import Optional, Dict, List, Tuple, Any
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
        """Add profit margin to base cost"""
        return round(base_cost * (1 + self.profit_margin / 100), 2)
    
    # ============ ACTIVATION API (One-time SMS) ============
    
    async def get_balance(self) -> float:
        """Get SMS-Man account balance"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/get-balance", 
                    params={"token": self.token},
                    timeout=30
                ) as resp:
                    data = await resp.json()
                    balance = float(data.get("balance", 0))
                    logger.info(f"SMS-Man balance: ₦{balance}")
                    return balance
        except Exception as e:
            logger.error(f"Error getting balance: {e}")
            return 0.0
    
    def get_balance_sync(self) -> float:
        """Synchronous version of get_balance"""
        try:
            response = requests.get(
                f"{self.base_url}/get-balance",
                params={"token": self.token},
                timeout=30
            )
            data = response.json()
            return float(data.get("balance", 0))
        except Exception as e:
            logger.error(f"Error getting balance sync: {e}")
            return 0.0
    
    async def get_countries(self) -> List[Dict]:
        """Get list of all countries"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/countries",
                    params={"token": self.token},
                    timeout=30
                ) as resp:
                    countries = await resp.json()
                    logger.info(f"Fetched {len(countries)} countries")
                    return countries
        except Exception as e:
            logger.error(f"Error fetching countries: {e}")
            return []
    
    def get_countries_sync(self) -> List[Dict]:
        """Synchronous version of get_countries"""
        try:
            response = requests.get(
                f"{self.base_url}/countries",
                params={"token": self.token},
                timeout=30
            )
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching countries sync: {e}")
            return []
    
    async def get_services(self) -> List[Dict]:
        """Get list of all services (applications)"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/applications",
                    params={"token": self.token},
                    timeout=30
                ) as resp:
                    services = await resp.json()
                    logger.info(f"Fetched {len(services)} services")
                    return services
        except Exception as e:
            logger.error(f"Error fetching services: {e}")
            return []
    
    def get_services_sync(self) -> List[Dict]:
        """Synchronous version of get_services"""
        try:
            response = requests.get(
                f"{self.base_url}/applications",
                params={"token": self.token},
                timeout=30
            )
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching services sync: {e}")
            return []
    
    async def get_prices(self, country_id: int) -> Dict:
        """Get current prices for activation by country"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/get-prices",
                    params={"token": self.token, "country_id": country_id},
                    timeout=30
                ) as resp:
                    prices = await resp.json()
                    logger.info(f"Fetched prices for country {country_id}")
                    return prices
        except Exception as e:
            logger.error(f"Error fetching prices: {e}")
            return {}
    
    def get_prices_sync(self, country_id: int) -> Dict:
        """Synchronous version of get_prices"""
        try:
            response = requests.get(
                f"{self.base_url}/get-prices",
                params={"token": self.token, "country_id": country_id},
                timeout=30
            )
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching prices sync: {e}")
            return {}
    
    async def get_activation_number(self, country_id: int, service_id: int, max_price: int = None) -> Tuple[Optional[str], Optional[int]]:
        """Request a phone number for activation (one-time SMS)"""
        try:
            params = {
                "token": self.token,
                "country_id": country_id,
                "application_id": service_id
            }
            if max_price:
                params["maxPrice"] = max_price
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/get-number",
                    params=params,
                    timeout=30
                ) as resp:
                    data = await resp.json()
                    
                    if "request_id" in data and "number" in data:
                        logger.info(f"Got activation number: {data['number']} (request_id: {data['request_id']})")
                        return data.get("number"), data.get("request_id")
                    else:
                        logger.error(f"Error getting number: {data}")
                        return None, None
        except Exception as e:
            logger.error(f"Error requesting activation number: {e}")
            return None, None
    
    def get_activation_number_sync(self, country_id: int, service_id: int, max_price: int = None) -> Tuple[Optional[str], Optional[int]]:
        """Synchronous version of get_activation_number"""
        try:
            params = {
                "token": self.token,
                "country_id": country_id,
                "application_id": service_id
            }
            if max_price:
                params["maxPrice"] = max_price
            
            response = requests.get(
                f"{self.base_url}/get-number",
                params=params,
                timeout=30
            )
            data = response.json()
            
            if "request_id" in data and "number" in data:
                return data.get("number"), data.get("request_id")
            else:
                logger.error(f"Error getting number sync: {data}")
                return None, None
        except Exception as e:
            logger.error(f"Error requesting activation number sync: {e}")
            return None, None
    
    async def get_activation_sms(self, request_id: int) -> Dict:
        """Get SMS/OTP for activation"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/get-sms",
                    params={"token": self.token, "request_id": request_id},
                    timeout=30
                ) as resp:
                    data = await resp.json()
                    
                    if "sms_code" in data:
                        logger.info(f"Got SMS code for request {request_id}: {data['sms_code']}")
                    elif "error_code" in data and data["error_code"] == "wait_sms":
                        logger.debug(f"Still waiting for SMS on request {request_id}")
                    else:
                        logger.warning(f"Unexpected response for SMS: {data}")
                    
                    return data
        except Exception as e:
            logger.error(f"Error getting activation SMS: {e}")
            return {"error_code": "request_failed", "error_msg": str(e)}
    
    def get_activation_sms_sync(self, request_id: int) -> Dict:
        """Synchronous version of get_activation_sms for Flask routes"""
        try:
            response = requests.get(
                f"{self.base_url}/get-sms",
                params={"token": self.token, "request_id": request_id},
                timeout=30
            )
            data = response.json()
            
            if "sms_code" in data:
                logger.info(f"Got SMS code for request {request_id}: {data['sms_code']}")
            elif "error_code" in data and data["error_code"] == "wait_sms":
                logger.debug(f"Still waiting for SMS on request {request_id}")
            
            return data
        except Exception as e:
            logger.error(f"Error getting activation SMS sync: {e}")
            return {"error_code": "request_failed", "error_msg": str(e)}
    
    async def set_activation_status(self, request_id: int, status: str) -> bool:
        """Change activation status: ready/close/reject/used"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/set-status",
                    params={"token": self.token, "request_id": request_id, "status": status},
                    timeout=30
                ) as resp:
                    data = await resp.json()
                    success = data.get("success", False)
                    if success:
                        logger.info(f"Set activation status for request {request_id} to {status}")
                    else:
                        logger.error(f"Failed to set status: {data}")
                    return success
        except Exception as e:
            logger.error(f"Error setting activation status: {e}")
            return False
    
    def set_activation_status_sync(self, request_id: int, status: str) -> bool:
        """Synchronous version of set_activation_status"""
        try:
            response = requests.get(
                f"{self.base_url}/set-status",
                params={"token": self.token, "request_id": request_id, "status": status},
                timeout=30
            )
            data = response.json()
            return data.get("success", False)
        except Exception as e:
            logger.error(f"Error setting activation status sync: {e}")
            return False
    
    # ============ RENT API (Number Rental) ============
    
    async def get_rental_limits(self, country_id: int, rent_type: str, time_value: str) -> List[Dict]:
        """Get rental number availability and pricing"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.rent_base_url}/limits",
                    params={
                        "token": self.token,
                        "country_id": country_id,
                        "type": rent_type,  # hour/day/week/month
                        "time": time_value
                    },
                    timeout=30
                ) as resp:
                    data = await resp.json()
                    limits = data.get("limits", [])
                    logger.info(f"Got rental limits for country {country_id}: {len(limits)} options")
                    return limits
        except Exception as e:
            logger.error(f"Error getting rental limits: {e}")
            return []
    
    def get_rental_limits_sync(self, country_id: int, rent_type: str, time_value: str) -> List[Dict]:
        """Synchronous version of get_rental_limits"""
        try:
            response = requests.get(
                f"{self.rent_base_url}/limits",
                params={
                    "token": self.token,
                    "country_id": country_id,
                    "type": rent_type,
                    "time": time_value
                },
                timeout=30
            )
            data = response.json()
            return data.get("limits", [])
        except Exception as e:
            logger.error(f"Error getting rental limits sync: {e}")
            return []
    
    async def get_rental_number(self, country_id: int, rent_type: str, time_value: str, service_id: int = None) -> Tuple[Optional[str], Optional[int]]:
        """Order a number for rent"""
        try:
            params = {
                "token": self.token,
                "country_id": country_id,
                "type": rent_type,
                "time": time_value
            }
            if service_id and service_id > 0:
                params["application_id"] = service_id
                params["partial"] = 1  # Partial number for specific service
            
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.rent_base_url}/get-number",
                    params=params,
                    timeout=30
                ) as resp:
                    data = await resp.json()
                    
                    if "request_id" in data and "number" in data:
                        logger.info(f"Got rental number: {data['number']} (request_id: {data['request_id']})")
                        return data.get("number"), data.get("request_id")
                    else:
                        logger.error(f"Error getting rental number: {data}")
                        return None, None
        except Exception as e:
            logger.error(f"Error requesting rental number: {e}")
            return None, None
    
    def get_rental_number_sync(self, country_id: int, rent_type: str, time_value: str, service_id: int = None) -> Tuple[Optional[str], Optional[int]]:
        """Synchronous version of get_rental_number"""
        try:
            params = {
                "token": self.token,
                "country_id": country_id,
                "type": rent_type,
                "time": time_value
            }
            if service_id and service_id > 0:
                params["application_id"] = service_id
                params["partial"] = 1
            
            response = requests.get(
                f"{self.rent_base_url}/get-number",
                params=params,
                timeout=30
            )
            data = response.json()
            
            if "request_id" in data and "number" in data:
                return data.get("number"), data.get("request_id")
            else:
                logger.error(f"Error getting rental number sync: {data}")
                return None, None
        except Exception as e:
            logger.error(f"Error requesting rental number sync: {e}")
            return None, None
    
    async def get_rental_sms(self, request_id: int) -> Dict:
        """Get the last SMS for rental number"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.rent_base_url}/get-sms",
                    params={"token": self.token, "request_id": request_id},
                    timeout=30
                ) as resp:
                    data = await resp.json()
                    
                    if "sms" in data:
                        logger.info(f"Got SMS for rental request {request_id}")
                    else:
                        logger.debug(f"No SMS yet for rental request {request_id}")
                    
                    return data
        except Exception as e:
            logger.error(f"Error getting rental SMS: {e}")
            return {"error": str(e)}
    
    def get_rental_sms_sync(self, request_id: int) -> Dict:
        """Synchronous version of get_rental_sms"""
        try:
            response = requests.get(
                f"{self.rent_base_url}/get-sms",
                params={"token": self.token, "request_id": request_id},
                timeout=30
            )
            return response.json()
        except Exception as e:
            logger.error(f"Error getting rental SMS sync: {e}")
            return {"error": str(e)}
    
    async def get_all_rental_sms(self, request_id: int) -> List[Dict]:
        """Get all SMS for rental number"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.rent_base_url}/get-all-sms",
                    params={"token": self.token, "request_id": request_id},
                    timeout=30
                ) as resp:
                    data = await resp.json()
                    sms_list = data.get("sms", [])
                    logger.info(f"Got {len(sms_list)} SMS messages for rental request {request_id}")
                    return sms_list
        except Exception as e:
            logger.error(f"Error getting all rental SMS: {e}")
            return []
    
    def get_all_rental_sms_sync(self, request_id: int) -> List[Dict]:
        """Synchronous version of get_all_rental_sms"""
        try:
            response = requests.get(
                f"{self.rent_base_url}/get-all-sms",
                params={"token": self.token, "request_id": request_id},
                timeout=30
            )
            data = response.json()
            return data.get("sms", [])
        except Exception as e:
            logger.error(f"Error getting all rental SMS sync: {e}")
            return []
    
    async def set_rental_status(self, request_id: int, status: str) -> bool:
        """Change rental status: cancel/close"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.rent_base_url}/set-status",
                    params={"token": self.token, "request_id": request_id, "status": status},
                    timeout=30
                ) as resp:
                    data = await resp.json()
                    success = data.get("success", False)
                    if success:
                        logger.info(f"Set rental status for request {request_id} to {status}")
                    else:
                        logger.error(f"Failed to set rental status: {data}")
                    return success
        except Exception as e:
            logger.error(f"Error setting rental status: {e}")
            return False
    
    def set_rental_status_sync(self, request_id: int, status: str) -> bool:
        """Synchronous version of set_rental_status"""
        try:
            response = requests.get(
                f"{self.rent_base_url}/set-status",
                params={"token": self.token, "request_id": request_id, "status": status},
                timeout=30
            )
            data = response.json()
            return data.get("success", False)
        except Exception as e:
            logger.error(f"Error setting rental status sync: {e}")
            return False
    
    async def get_all_rental_numbers(self) -> List[Dict]:
        """Get list of all rented numbers"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.rent_base_url}/get-all-requests",
                    params={"token": self.token},
                    timeout=30
                ) as resp:
                    data = await resp.json()
                    logger.info(f"Got {len(data)} rental requests")
                    return data
        except Exception as e:
            logger.error(f"Error getting all rental numbers: {e}")
            return []
    
    def get_all_rental_numbers_sync(self) -> List[Dict]:
        """Synchronous version of get_all_rental_numbers"""
        try:
            response = requests.get(
                f"{self.rent_base_url}/get-all-requests",
                params={"token": self.token},
                timeout=30
            )
            return response.json()
        except Exception as e:
            logger.error(f"Error getting all rental numbers sync: {e}")
            return []
    
    # ============ UTILITY METHODS ============
    
    def extract_otp_from_sms(self, sms_text: str) -> Optional[str]:
        """Extract OTP code from SMS text"""
        import re
        
        # Common OTP patterns
        patterns = [
            r'\b\d{4,8}\b',  # 4-8 digit numbers
            r'code[:\s]*(\d{4,8})',  # code: 1234
            r'OTP[:\s]*(\d{4,8})',  # OTP: 1234
            r'verification[:\s]*(\d{4,8})',  # verification: 1234
            r'密码[:\s]*(\d{4,8})',  # Chinese: password: 1234
            r'کد[:\s]*(\d{4,8})',  # Persian: code: 1234
        ]
        
        for pattern in patterns:
            match = re.search(pattern, sms_text, re.IGNORECASE)
            if match:
                code = match.group(1) if match.lastindex else match.group(0)
                if code and code.isdigit():
                    return code
        
        return None
    
    async def check_service_availability(self, country_id: int, service_id: int) -> Dict:
        """Check if a specific service has available numbers"""
        try:
            # Try to get a number (but don't actually rent it)
            # This is a hack since SMS-Man doesn't have a direct availability endpoint
            number, request_id = await self.get_activation_number(country_id, service_id)
            
            if number and request_id:
                # Cancel the request immediately
                await self.set_activation_status(request_id, "cancel")
                return {"available": True, "message": "Service available"}
            else:
                return {"available": False, "message": "No numbers available"}
        except Exception as e:
            logger.error(f"Error checking availability: {e}")
            return {"available": False, "message": str(e)}

# Create singleton instance
sms_man = SMSManAPI()
