import httpx
from decimal import Decimal, InvalidOperation
from typing import Dict, Any, Optional
from httpx import Timeout, HTTPStatusError, RequestError
from tenacity import retry, stop_after_attempt, wait_exponential
from datetime import datetime
from .config import (
    PRICES_API_URL, EXCHANGE_API_URL,
    REQUEST_TIMEOUT, MARKET_FEE, CACHE_TTL
)
from .decorators import cache_ttl

class PriceBot:
    def __init__(self):
        self.http_client = httpx.AsyncClient(timeout=Timeout(REQUEST_TIMEOUT))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1))
    async def fetch_data(self, url: str) -> Dict[str, Any]:
        try:
            response = await self.http_client.get(url)
            response.raise_for_status()
            return response.json()
        except HTTPStatusError as e:
            raise Exception(f"HTTP error {e.response.status_code}: {e}")
        except RequestError as e:
            raise Exception(f"Connection error: {e}")
        except ValueError as e:
            raise Exception(f"JSON parsing error: {e}")

    @cache_ttl(CACHE_TTL)
    async def get_prices(self) -> Dict[str, Decimal]:
        try:
            data = await self.fetch_data(PRICES_API_URL)
            return {
                k.lower(): Decimal(str(v)) 
                for k, v in data["data"]["p2p"].items()
            }
        except Exception as e:
            if hasattr(self, "_get_prices_cache"):
                return self._get_prices_cache
            raise Exception(f"Error getting prices: {e}")

    @cache_ttl(CACHE_TTL)
    async def get_exchange_rates(self) -> Dict[str, Dict[str, Decimal]]:
        try:
            data = await self.fetch_data(EXCHANGE_API_URL)
            return {
                k: {sub_k: Decimal(str(sub_v)) for sub_k, sub_v in v.items()}
                for k, v in data.items()
            }
        except Exception as e:
            if hasattr(self, "_get_exchange_rates_cache"):
                return self._get_exchange_rates_cache
            raise Exception(f"Error getting exchange rates: {e}")

    async def validate_amount(self, amount: Decimal) -> bool:
        return amount >= Decimal('0.00000001')
