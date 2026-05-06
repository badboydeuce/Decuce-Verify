"""
SMS-Man API Client with 2x profit margin
All prices are doubled automatically
"""

import aiohttp
import asyncio
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from loguru import logger
import json

class SMSManClient:
    def __init__(self, token: str, base_url: str = "https://api.sms-man.com/control", 
                 profit_margin: float = 2.0, redis_url: str = None):
        self.token = token
        self.base_url = base_url
        self.profit_margin = profit_margin  # 2.0 = 2x markup (100% profit)
        self.session = None
        self.redis_client = None
        
        if redis_url:
            import redis.asyncio as redis
            self.redis_client = redis.from_url(redis_url)
        
        logger.info(f"SMS-Man client initialized with {profit_margin}x profit margin")
        
    async def _request(self, method: str, endpoint: str, params: Dict = None, retry: int = 3) -> Dict:
        """Make request to SMS-Man API with retry logic"""
        if not self.session:
            self.session = aiohttp.ClientSession()
            
        if params is None:
            params = {}
        params['token'] = self.token
        
        for attempt in range(retry):
            try:
                async with self.session.request(method, f"{self.base_url}/{endpoint}", params=params) as response:
                    data = await response.json()
                    
                    if isinstance(data, dict) and data.get('success') is False:
                        error_code = data.get('error_code', 'unknown')
                        error_msg = data.get('error_msg', 'Unknown error')
                        
                        if error_code == 'wrong_token':
                            raise Exception(f"Invalid API token: {error_msg}")
                        elif error_code == 'no_numbers':
                            raise Exception("No numbers available for this service/country")
                        else:
                            raise Exception(f"SMS-Man error ({error_code}): {error_msg}")
                    
                    return data
                    
            except aiohttp.ClientError as e:
                logger.error(f"Request error (attempt {attempt+1}/{retry}): {e}")
                if attempt == retry - 1:
                    raise
                await asyncio.sleep(2 ** attempt)
    
    def apply_markup(self, cost: float) -> float:
        """Apply profit markup to SMS-Man price"""
        marked_up_price = cost * self.profit_margin
        # Round to 2 decimal places for cleaner display
        return round(marked_up_price, 2)
    
    async def get_balance(self) -> float:
        """Get account balance (no markup - internal use)"""
        data = await self._request('GET', 'get-balance')
        return float(data.get('balance', 0))
    
    async def get_all_countries(self, force_refresh: bool = False) -> List[Dict]:
        """Get list of ALL countries"""
        cache_key = "smsman:countries"
        
        if not force_refresh and self.redis_client:
            cached = await self.redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        
        data = await self._request('GET', 'countries')
        
        countries = []
        for country in data:
            country_data = {
                'id': country.get('id'),
                'name': country.get('title'),
                'code': self._get_country_code(country.get('title')),
                'flag': self._get_country_flag(country.get('title')),
            }
            countries.append(country_data)
            
        if self.redis_client:
            await self.redis_client.setex(cache_key, 3600, json.dumps(countries))
            
        return countries
    
    async def get_all_services(self, force_refresh: bool = False) -> List[Dict]:
        """Get list of ALL services"""
        cache_key = "smsman:services"
        
        if not force_refresh and self.redis_client:
            cached = await self.redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        
        data = await self._request('GET', 'applications')
        
        services = []
        for service in data:
            service_data = {
                'id': service.get('id'),
                'name': service.get('name'),
                'code': service.get('code', service.get('name').lower()),
                'category': self._get_service_category(service.get('name')),
                'icon': self._get_service_icon(service.get('name')),
                'popularity': self._get_service_popularity(service.get('id'))
            }
            services.append(service_data)
            
        if self.redis_client:
            await self.redis_client.setex(cache_key, 3600, json.dumps(services))
            
        return services
    
    async def get_prices_for_all_services(self, country_id: int = None) -> Dict:
        """
        Get current prices for all services with profit markup applied
        Returns prices with 2x markup
        """
        cache_key = f"smsman:prices:{country_id if country_id else 'all'}"
        
        if self.redis_client:
            cached = await self.redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        
        params = {}
        if country_id:
            params['country_id'] = country_id
            
        data = await self._request('GET', 'get-prices', params)
        
        # Parse and apply markup to prices
        prices = {}
        for country_str, services in data.items():
            country = int(country_str)
            prices[country] = {}
            for service_str, price_info in services.items():
                service = int(service_str)
                original_cost = float(price_info.get('cost', 0))
                marked_up_cost = self.apply_markup(original_cost)
                
                prices[country][service] = {
                    'original_cost': original_cost,
                    'cost': marked_up_cost,  # This is what customers pay
                    'profit': marked_up_cost - original_cost,
                    'profit_margin_percent': ((marked_up_cost - original_cost) / original_cost * 100) if original_cost > 0 else 0,
                    'count': price_info.get('count', 0),
                    'currency': price_info.get('currency', 'RUB')
                }
                
        if self.redis_client:
            await self.redis_client.setex(cache_key, 300, json.dumps(prices))
            
        return prices
    
    async def get_number_availability(self, country_id: int = None, service_id: int = None) -> List[Dict]:
        """Get number availability/limits"""
        cache_key = f"smsman:limits:{country_id if country_id else 'all'}:{service_id if service_id else 'all'}"
        
        if self.redis_client:
            cached = await self.redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        
        params = {}
        if country_id:
            params['country_id'] = country_id
        if service_id:
            params['application_id'] = service_id
            
        data = await self._request('GET', 'limits', params)
        
        if self.redis_client:
            await self.redis_client.setex(cache_key, 120, json.dumps(data))
            
        return data
    
    async def rent_number(
        self, 
        country_id: int, 
        service_id: int, 
        max_price: float = None,
        currency: str = "USD",
        operator: str = "any"
    ) -> Tuple[int, str, int, float, float]:
        """
        Rent a phone number
        Returns: (request_id, number, actual_country, actual_original_cost, actual_marked_up_cost)
        """
        # SMS-Man expects original price for max_price parameter
        params = {
            'country_id': country_id,
            'application_id': service_id,
            'currency': currency
        }
        
        if max_price:
            # Convert marked up max price back to original for SMS-Man
            original_max_price = max_price / self.profit_margin
            params['maxPrice'] = original_max_price
        if operator and operator != "any":
            params['operator'] = operator
            
        data = await self._request('GET', 'get-number', params)
        
        request_id = data.get('request_id')
        number = data.get('number')
        actual_country = data.get('country_id', country_id)
        original_cost = float(data.get('price', 0)) if 'price' in data else 0.0
        marked_up_cost = self.apply_markup(original_cost)
        
        logger.info(f"Rented number: {number} | Original: ${original_cost:.2f} | Selling: ${marked_up_cost:.2f} | Profit: ${marked_up_cost - original_cost:.2f}")
        
        return request_id, number, actual_country, original_cost, marked_up_cost
    
    async def get_sms(self, request_id: int) -> Dict:
        """Get SMS/OTP for rented number"""
        params = {'request_id': request_id}
        data = await self._request('GET', 'get-sms', params)
        
        if 'sms_code' in data:
            return {
                'status': 'received',
                'code': data['sms_code'],
                'text': data.get('sms_text', ''),
                'full_sms': data.get('full_sms', '')
            }
        elif 'error_code' in data:
            error_code = data['error_code']
            if error_code == 'wait_sms':
                return {'status': 'waiting', 'code': None}
            else:
                return {'status': 'error', 'code': None, 'error': data.get('error_msg')}
        else:
            return {'status': 'unknown', 'code': None}
    
    async def cancel_order(self, request_id: int) -> bool:
        """Cancel/close an order"""
        params = {'request_id': request_id, 'status': 'close'}
        data = await self._request('GET', 'set-status', params)
        return data.get('success', False)
    
    async def mark_completed(self, request_id: int) -> bool:
        """Mark order as completed"""
        params = {'request_id': request_id, 'status': 'ready'}
        data = await self._request('GET', 'set-status', params)
        return data.get('success', False)
    
    # Helper methods
    def _get_country_code(self, country_name: str) -> str:
        """Get ISO country code"""
        country_codes = {
            'Russia': 'RU', 'Ukraine': 'UA', 'Kazakhstan': 'KZ',
            'USA': 'US', 'Canada': 'CA', 'UK': 'GB', 'Germany': 'DE',
            'France': 'FR', 'Spain': 'ES', 'Italy': 'IT', 'China': 'CN',
            'India': 'IN', 'Brazil': 'BR', 'Mexico': 'MX', 'Australia': 'AU'
        }
        return country_codes.get(country_name, 'XX')
    
    def _get_country_flag(self, country_name: str) -> str:
        """Get flag emoji"""
        flags = {
            'Russia': '🇷🇺', 'Ukraine': '🇺🇦', 'Kazakhstan': '🇰🇿',
            'USA': '🇺🇸', 'Canada': '🇨🇦', 'UK': '🇬🇧', 'Germany': '🇩🇪',
            'France': '🇫🇷', 'Spain': '🇪🇸', 'Italy': '🇮🇹', 'China': '🇨🇳',
            'India': '🇮🇳', 'Brazil': '🇧🇷', 'Mexico': '🇲🇽', 'Australia': '🇦🇺'
        }
        return flags.get(country_name, '🌍')
    
    def _get_service_category(self, service_name: str) -> str:
        """Categorize service"""
        social_media = ['Telegram', 'WhatsApp', 'Vkontakte', 'Facebook', 'Instagram', 'Twitter', 'TikTok']
        email = ['Gmail', 'Outlook', 'Yahoo', 'Mail.ru']
        crypto = ['Binance', 'Coinbase', 'Kucoin', 'Bybit', 'OKX']
        messaging = ['WeChat', 'Line', 'Viber', 'Signal']
        
        name_lower = service_name.lower()
        if any(s.lower() in name_lower for s in social_media):
            return "Social Media"
        elif any(s.lower() in name_lower for s in email):
            return "Email"
        elif any(s.lower() in name_lower for s in crypto):
            return "Cryptocurrency"
        elif any(s.lower() in name_lower for s in messaging):
            return "Messaging"
        else:
            return "Other"
    
    def _get_service_icon(self, service_name: str) -> str:
        """Get icon for service"""
        icons = {
            'Telegram': '📱', 'WhatsApp': '💬', 'Gmail': '📧', 'Binance': '₿',
            'Facebook': '👥', 'Instagram': '📸', 'Twitter': '🐦', 'TikTok': '🎵',
            'WeChat': '💬', 'Line': '💬', 'Viber': '📞', 'Signal': '🔒'
        }
        for key, icon in icons.items():
            if key in service_name:
                return icon
        return '🔧'
    
    def _get_service_popularity(self, service_id: int) -> int:
        """Get popularity score (1-100)"""
        popular_services = {3: 100, 6: 95, 7: 90, 12: 85, 1: 80, 2: 75}
        return popular_services.get(service_id, 50)
    
    async def close(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
        if self.redis_client:
            await self.redis_client.close()
