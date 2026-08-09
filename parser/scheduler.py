"""Планировщик периодической проверки цен и рассылки уведомлений."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from config.settings import settings
from core.db import SessionLocal
from core.models import Item, PriceAlert, User
from core.pricing import nice_price
from core.tracker import record_price
from parser.ozon.client import OzonClient
from parser.wb.client import WbClient

log = logging.getLogger(__name__)


class Tracker:
    def __init__(self) -> None:
        self.wb = WbClient()
        self.ozon = OzonClient()
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._notify = None

    def set_notifier(self, notify_func) -> None:
        """Установить функцию рассылки: async notify(tg_id: int, text: str)."""
        self._notify = notify_func

    async def close(self) -> None:
        await self.wb.close()
        await self.ozon.close()

    async def _fetch_card(self, item: Item) -> object | None:
        if item.marketplace == "wb":
            return await self.wb.get_card(item.sku)
        if item.marketplace == "ozon":
            return await self.ozon.get_product_by_sku(item.sku)
        return None

    async def _check_alerts(self, item: Item, data) -> None:
        """Проверить целевые цены: если цена упала до цели — уведомить и отключить."""
        if data.price is None:
            return
        async with SessionLocal() as session:
            result = await session.execute(
                select(PriceAlert)
                .where(PriceAlert.item_id == item.id, PriceAlert.active.is_(True))
            )
            alerts = list(result.scalars().all())
            for alert in alerts:
                if data.price <= alert.target_price:
                    alert.active = False
                    user_result = await session.execute(
                        select(User).where(User.id == item.user_id)
                    )
                    user = user_result.scalar_one_or_none()
                    if user and self._notify:
                        try:
                            await self._notify(
                                user.tg_id,
                                f"🔔 <b>Цена достигла цели!</b>\n\n"
                                f"{item.title or item.sku} ({item.sku})\n"
                                f"Цена: <b>{nice_price(data.price)}</b> (цель была "
                                f"{nice_price(alert.target_price)})\n\n"
                                f"Успейте закупиться! 📦",
                            )
                        except Exception as exc:  # noqa: BLE001
                            log.warning("alert notify %s failed: %s", user.tg_id, exc)
            if alerts:
                await session.commit()

    async def tick(self) -> None:
        """Один проход: обойти все товары, записать цены, разослать изменения."""
        async with SessionLocal() as session:
            result = await session.execute(select(Item))
            items = list(result.scalars().all())
            if not items:
                return

            for item in items:
                data = await self._fetch_card(item)
                if data is None:
                    continue
                change = await record_price(session, item, data)
                if change and self._notify:
                    user_result = await session.execute(
                        select(User).where(User.id == item.user_id)
                    )
                    user = user_result.scalar_one_or_none()
                    if user and user.is_subscribed:
                        try:
                            await self._notify(user.tg_id, change.message)
                        except Exception as exc:  # noqa: BLE001
                            log.warning("notify %s failed: %s", user.tg_id, exc)
                await self._check_alerts(item, data)

            await session.commit()

    def start(self) -> None:
        interval = max(1, settings.track_interval_min) * 60
        self._scheduler.add_job(self.tick, "interval", seconds=interval, id="tracker")
        self._scheduler.add_job(self.tick, "date", run_date=None, id="tracker_once")
        self._scheduler.start()
        log.info("Tracker started, interval=%s min", settings.track_interval_min)
