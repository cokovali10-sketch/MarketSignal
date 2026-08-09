"""Вебхук для авто-оплаты CryptoBot.

CryptoBot уведомляет на этот адрес при изменении статуса счёта.
Поднять: uvicorn web.hooks:app --port 8000
"""

import logging

from fastapi import FastAPI, Request
from sqlalchemy import select

from core.db import SessionLocal
from core.models import Subscription, User
from core.pricing import TARIFFS

log = logging.getLogger(__name__)

app = FastAPI(title="MarketSignal webhooks")


async def activate_by_cryptopay(invoice: dict) -> None:
    """Активировать подписку по оплаченному счёту CryptoBot."""
    status = invoice.get("status")
    if status != "paid":
        return
    payload = invoice.get("payload") or ""
    # payload хранит тариф: "starter" / "pro"
    tariff = payload if payload in TARIFFS else "starter"
    amount = float(invoice.get("amount") or 0)
    if amount < 0.01:
        return

    tg_id = int(invoice.get("user_id") or 0)  # CryptoBot не даёт tg_id напрямую
    # Из payload можно передать tg_id в формате "tariff:tg_id"
    if ":" in payload:
        tariff, tg_id = payload.split(":", 1)
        tg_id = int(tg_id)

    if not tg_id:
        log.warning("CryptoPay invoice %s: no tg_id", invoice.get("invoice_id"))
        return

    paid_until = None
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(tg_id=tg_id, tariff=tariff)
            session.add(user)
            await session.flush()
        else:
            user.tariff = tariff
        from datetime import datetime, timedelta, timezone

        paid_until = datetime.now(timezone.utc) + timedelta(days=30)
        user.paid_until = paid_until
        session.add(
            Subscription(
                user_id=user.id,
                tariff=tariff,
                paid_until=paid_until,
                payment_id=f"cryptopay:{invoice.get('invoice_id')}",
            )
        )
        await session.commit()

    log.info("CryptoPay: activated %s for tg %s", tariff, tg_id)
    # Уведомим пользователя
    try:
        from bot.handlers.main import bot

        await bot.send_message(
            tg_id,
            f"🎉 <b>Подписка {TARIFFS[tariff]['name']} активирована!</b>\n\n"
            f"Действует до {paid_until.strftime('%d.%m.%Y')}.\n"
            f"Приятного использования MarketSignal! 📈",
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("notify failed: %s", exc)


@app.post("/crypto-pay")
async def crypto_pay_webhook(request: Request) -> dict:
    data = await request.json()
    if data.get("update_type") == "invoice_paid":
        invoice = data.get("payload") or {}
        log.info("invoice_paid: %s", invoice)
        await activate_by_cryptopay(invoice)
    return {"ok": True}
