# SMS-Man API client
import aiohttp
from typing import Dict, List, Tuple

class SMSManClient:
    def __init__(self, token: str, base_url: str = "https://api.sms-man.com/control"):
        self.token = token
        self.base_url = base_url
        self.session = None
        
    async def _request(self, endpoint: str, params: Dict = None) -> Dict:
        if not self.session:
            self.session = aiohttp.ClientSession()
        
        params = params or {}
        params['token'] = self.token
        
        async with self.session.get(f"{self.base_url}/{endpoint}", params=params) as resp:
            return await resp.json()
    
    async def get_balance(self) -> float:
        data = await self._request('get-balance')
        return float(data.get('balance', 0))
    
    async def get_countries(self) -> List[Dict]:
        return await self._request('countries')
    
    async def get_services(self) -> List[Dict]:
        return await self._request('applications')
    
    async def get_prices(self, country_id: int = None) -> Dict:
        params = {'country_id': country_id} if country_id else {}
        return await self._request('get-prices', params)
    
    async def rent_number(self, country_id: int, service_id: int) -> Tuple[int, str]:
        params = {'country_id': country_id, 'application_id': service_id, 'currency': 'USD'}
        data = await self._request('get-number', params)
        return data.get('request_id'), data.get('number')
    
    async def get_sms(self, request_id: int) -> Dict:
        data = await self._request('get-sms', {'request_id': request_id})
        if 'sms_code' in data:
            return {'status': 'received', 'code': data['sms_code']}
        return {'status': 'waiting', 'code': None}
    
    async def cancel_order(self, request_id: int) -> bool:
        data = await self._request('set-status', {'request_id': request_id, 'status': 'close'})
        return data.get('success', False)
    
    async def close(self):
        if self.session:
            await self.session.close()
