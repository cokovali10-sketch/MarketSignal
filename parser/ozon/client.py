"""Парсер Ozon: API продавца (по ключу) + открытые карточки."""

import asyncio
import logging

import aiohttp

from config.settings import settings
from core.pricing import CardData

log = logging.getLogger(__name__)

SELLER_INFO_URL = "https://api-seller.ozon.ru/v1/product/info/list"
OPEN_INFO_URL = "https://api-seller.ozon.ru/v1/product/info"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


class OzonClient:
    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None
        self._sem: asyncio.Semaphore = asyncio.Semaphore(settings.parser_concurrency)
        self._last_request: float = 0.0
        self._client_id = settings.ozon_client_id
        self._api_key = settings.ozon_api_key

    @property
    def configured(self) -> bool:
        return bool(self._client_id and self._api_key)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=HEADERS)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    def _auth_headers(self) -> dict:
        return {
            "Client-Id": self._client_id,
            "Api-Key": self._api_key,
        }

    async def _rate_limited_post(
        self, url: str, json_body: dict, auth: bool = True
    ) -> dict:
        async with self._sem:
            now = asyncio.get_event_loop().time()
            wait = settings.ozon_request_interval - (now - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = asyncio.get_event_loop().time()

            session = await self._get_session()
            headers = dict(HEADERS)
            if auth:
                headers.update(self._auth_headers())
            async with session.post(
                url, json=json_body, headers=headers, timeout=aiohttp.ClientTimeout(total=25)
            ) as resp:
                resp.raise_for_status()
                return await resp.json()

    async def get_product_by_sku(self, sku: str) -> CardData | None:
        """Получить товар по артикулу (offer_id) через API продавца."""
        if not self.configured:
            return None
        try:
            data = await self._rate_limited_post(
                SELLER_INFO_URL,
                {"product_id": [sku], "sku": []},
            )
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.warning("Ozon sku %s failed: %s", sku, exc)
            return None

        items = data.get("result", {}).get("items") or []
        if not items:
            return None
        it = items[0]

        price = None
        price_info = it.get("price") or {}
        if price_info.get("price"):
            price = float(price_info["price"]) / 100
        if price is None and price_info.get("marketing_price"):
            price = float(price_info["marketing_price"]) / 100
        elif price is None and price_info.get("old_price"):
            price = float(price_info["old_price"]) / 100

        old_price = None
        if price_info.get("old_price"):
            old_price = float(price_info["old_price"]) / 100

        stock = None
        stocks = it.get("stocks") or {}
        if stocks.get("present"):
            stock = stocks["present"]

        return CardData(
            marketplace="ozon",
            sku=sku,
            title=it.get("name"),
            price=price,
            old_price=old_price,
            stock=stock,
            seller_id=str(it.get("seller_id")) if it.get("seller_id") else None,
        )
