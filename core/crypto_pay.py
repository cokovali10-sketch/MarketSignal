"""Интеграция CryptoBot (Crypto Pay API) для авто-оплаты подписок.

Документация: https://doc.crypt.bot/crypto-pay-api
Токен получается в @CryptoBot → Разработчикам → API Token.
"""

import logging

import aiohttp

from config.settings import settings
from core.pricing import TARIFFS

log = logging.getLogger(__name__)

API_BASE = "https://pay.crypt.bot/api"
HEADERS = {
    "User-Agent": "MarketSignal/0.1",
    "Content-Type": "application/json",
}


class CryptoPayError(Exception):
    pass


class CryptoPayClient:
    def __init__(self, token: str = "") -> None:
        self._token = token or settings.crypto_pay_token
        self._session: aiohttp.ClientSession | None = None

    @property
    def configured(self) -> bool:
        return bool(self._token)

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=HEADERS)
        return self._session

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

    async def _call(self, method: str, payload: dict | None = None) -> dict:
        if not self.configured:
            raise CryptoPayError("Crypto Pay API token is not configured")
        session = await self._get_session()
        headers = {"Authorization": f"Bearer {self._token}", **HEADERS}
        url = f"{API_BASE}/{method}"
        async with session.post(url, json=payload or {}, headers=headers) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise CryptoPayError(f"HTTP {resp.status}: {text[:200]}")
            data = await resp.json()
        if not data.get("ok"):
            raise CryptoPayError(f"API error: {data.get('error', data)[:200]}")
        return data.get("result") or {}

    async def get_me(self) -> dict:
        """Проверить токен и получить информацию об аккаунте."""
        return await self._call("getMe")

    async def create_invoice(
        self,
        amount: float,
        currency: str = "USDT",
        payload: str = "",
    ) -> dict:
        """Создать счёт на оплату. Возвращает поле pay_url — ссылку на оплату."""
        body = {
            "asset": currency,
            "amount": str(amount),
            "allow_anonymous": True,
            "expires_in": 3600,  # 1 час
        }
        if payload:
            body["payload"] = payload
        return await self._call("createInvoice", body)

    async def get_invoices(self, invoice_id: int | None = None) -> list[dict]:
        """Получить счета; invoice_id — если нужно проверить конкретный."""
        payload = {"invoice_ids": str(invoice_id)} if invoice_id else {}
        result = await self._call("getInvoices", payload)
        return result.get("items") or []


def currency_for_tariff(tariff: str) -> str:
    """Валюта для тарифа: Pro дороже — принимаем USDT, Starter тоже USDT."""
    return "USDT"


def amount_for_tariff(tariff: str) -> float:
    """Цена тарифа в USDT (фикс. курс: 1 USDT ≈ 1 USD, округляем вверх)."""
    price_rub = TARIFFS[tariff]["price"]
    # Примерный курс RUB->USDT (реальный можно править в .env)
    rate = settings.usdt_rate or 95.0
    import math

    return math.ceil(price_rub / rate * 100) / 100
