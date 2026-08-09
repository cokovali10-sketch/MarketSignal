"""Парсер Wildberries: открытые эндпоинты карточек и каталога."""

import asyncio
import logging
import ssl

import aiohttp

from config.settings import settings
from core.pricing import CardData

log = logging.getLogger(__name__)

CARD_URL = "https://card.wb.ru/cards/v2/detail"
CATALOG_URL = "https://catalog.wb.ru/catalog/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Accept-Language": "ru,en;q=0.9",
}


def _ssl_context():
    if settings.ssl_verify:
        return None
    return ssl.create_default_context()


def _session_kwargs() -> dict:
    kwargs: dict = {}
    ctx = _ssl_context()
    if ctx is not None:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        kwargs["connector"] = aiohttp.TCPConnector(ssl=ctx)
    if settings.http_proxy:
        kwargs["proxy"] = settings.http_proxy
    return kwargs


class WbClient:
    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None
        self._sem: asyncio.Semaphore = asyncio.Semaphore(settings.parser_concurrency)
        self._last_request: float = 0.0

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=HEADERS, **_session_kwargs())
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _rate_limited_get(self, url: str, params: dict | None = None) -> dict:
        async with self._sem:
            now = asyncio.get_event_loop().time()
            wait = settings.wb_request_interval - (now - self._last_request)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_request = asyncio.get_event_loop().time()

            session = await self._get_session()
            last_exc: Exception | None = None
            for attempt in range(settings.http_retries):
                try:
                    async with session.get(
                        url, params=params, timeout=aiohttp.ClientTimeout(total=20)
                    ) as resp:
                        if resp.status in (429, 500, 502, 503, 504):
                            await asyncio.sleep(1.5 * (attempt + 1))
                            last_exc = aiohttp.ClientResponseError(
                                resp.request_info, resp.history, status=resp.status
                            )
                            continue
                        resp.raise_for_status()
                        return await resp.json()
                except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                    last_exc = exc
                    await asyncio.sleep(1.0 * (attempt + 1))
            raise last_exc if last_exc else RuntimeError(f"request failed: {url}")

    async def get_card(self, nm: str) -> CardData | None:
        """Получить данные карточки по артикулу (nm)."""
        params = {
            "appType": "1",
            "curr": "rub",
            "dest": "-1257786",
            "spp": "30",
            "nm": nm,
        }
        try:
            data = await self._rate_limited_get(CARD_URL, params)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.warning("WB card %s failed: %s", nm, exc)
            return None

        products = data.get("data", {}).get("products") or []
        if not products:
            return None
        p = products[0]

        sizes = p.get("sizes") or []
        stock = sum(s.get("qty") or 0 for s in sizes)

        # Цены приходят в копейках относительно 100
        price_raw = p.get("salePriceU") or p.get("priceU")
        price = price_raw / 100 if price_raw else None
        old_price_raw = p.get("priceU")
        old_price = old_price_raw / 100 if old_price_raw else None

        seller_id = None
        for s in sizes:
            for st in s.get("stocks") or []:
                seller_id = st.get("wh") or seller_id
                break
        seller_id = str(seller_id) if seller_id is not None else None

        return CardData(
            marketplace="wb",
            sku=nm,
            title=p.get("name"),
            price=price,
            old_price=old_price,
            stock=stock,
            seller_id=seller_id,
        )

    async def get_catalog(self, query: str, limit: int = 30) -> list[CardData]:
        """Поиск товаров по запросу (для «растущих товаров»)."""
        # Используем мобильный/каталог-эндпоинт поиска
        url = "https://search.wb.ru/exactmatch/ru/common/v4/search"
        params = {"query": query, "resultset": "catalog", "limit": limit}
        try:
            data = await self._rate_limited_get(url, params)
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.warning("WB catalog %s failed: %s", query, exc)
            return []

        products = data.get("data", {}).get("products") or []
        cards: list[CardData] = []
        for p in products:
            price_raw = p.get("salePriceU") or p.get("priceU")
            price = price_raw / 100 if price_raw else None
            sizes = p.get("sizes") or []
            stock = sum(s.get("qty") or 0 for s in sizes)
            cards.append(
                CardData(
                    marketplace="wb",
                    sku=str(p.get("id", "")),
                    title=p.get("name"),
                    price=price,
                    old_price=(p.get("priceU") or 0) / 100 if p.get("priceU") else None,
                    stock=stock,
                )
            )
        return cards
