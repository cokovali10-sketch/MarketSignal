"""Инструменты: калькулятор маржи, дайджест цен, поиск по каталогу, статистика."""

import logging
from datetime import datetime, timedelta, timezone

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select

from bot.services import PENDING, back_kbd, ensure_user, menu_kbd, tools_kbd
from config.settings import settings
from core.db import SessionLocal
from core.models import Item, PricePoint, Subscription, User
from core.pricing import TARIFFS, nice_price
from core.tracker import get_history

log = logging.getLogger(__name__)
router = Router()


# ─────────────────────────── МЕНЮ ИНСТРУМЕНТОВ ───────────────────────────

@router.callback_query(F.data == "tools")
async def cb_tools(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer(
        "🛠 <b>Инструменты</b>\n\n"
        "• 💰 <b>Калькулятор маржи</b> — сколько реально заработаете с продажи\n"
        "• 📊 <b>Дайджест цен</b> — сводка по всем вашим товарам\n\n"
        "Доступно для всех тарифов.",
        reply_markup=tools_kbd(),
    )


# ─────────────────────────── КАЛЬКУЛЯТОР МАРЖИ ───────────────────────────

@router.callback_query(F.data == "calc_margin")
async def cb_calc_margin(call: CallbackQuery) -> None:
    await call.answer()
    PENDING[call.from_user.id] = ("margin", None)
    await call.message.answer(
        "💰 <b>Калькулятор маржи</b>\n\n"
        "Пришлите через пробел:\n"
        "<code>цена_продажи себестоимость комиссия_% логистика</code>\n\n"
        "Пример: <code>1500 800 15 50</code>\n"
        "означает: продажа 1500 ₽, закупка 800 ₽, комиссия WB 15%, логистика 50 ₽.\n\n"
        "Можно добавить 5-е число — прочие расходы (упаковка, реклама).",
        reply_markup=back_kbd("tools"),
    )


# ─────────────────────────── ДАЙДЖЕСТ ЦЕН ───────────────────────────

@router.callback_query(F.data == "digest")
async def cb_digest(call: CallbackQuery) -> None:
    await call.answer("Считаю сводку…")
    await show_digest(call.message, call.from_user.id)


@router.message(Command("digest"))
async def cmd_digest(message: Message) -> None:
    await show_digest(message, message.from_user.id)


async def show_digest(target, tg_id: int) -> None:
    async with SessionLocal() as session:
        user = await ensure_user(tg_id, getattr(target, "from_user", None) and target.from_user.username)
        result = await session.execute(
            select(Item).where(Item.user_id == user.id).order_by(Item.id)
        )
        items = list(result.scalars().all())
        if not items:
            await target.answer("Сначала добавьте товары.", reply_markup=menu_kbd())
            return
        lines = ["📊 <b>Дайджест цен</b>\n"]
        since = datetime.now(timezone.utc) - timedelta(days=7)
        for it in items:
            points = await get_history(session, it.id, limit=50)
            current = points[-1] if points else None
            price = nice_price(current.price) if current and current.price else "—"
            week_points = [p for p in points if p.ts >= since and p.price is not None]
            delta = ""
            if len(week_points) >= 2:
                first, last = week_points[0].price, week_points[-1].price
                if first and last:
                    diff = last - first
                    if abs(diff) >= 1:
                        arrow = "📉" if diff < 0 else "📈"
                        delta = f" {arrow} {diff:+,.0f} ₽".replace(",", " ")
            mp = "WB" if it.marketplace == "wb" else "OZ"
            title = (it.title or it.sku)[:35]
            lines.append(f"• <b>{title}</b>\n  {mp} {it.sku} · {price}{delta}")
        await target.answer("\n\n".join(lines), reply_markup=back_kbd("tools"))


# ─────────────────────────── ПОИСК ПО КАТАЛОГУ WB ───────────────────────────

@router.callback_query(F.data == "search")
async def cb_search(call: CallbackQuery) -> None:
    await call.answer()
    PENDING[call.from_user.id] = ("search", None)
    await call.message.answer(
        "🔍 <b>Поиск по каталогу Wildberries</b>\n\n"
        "Пришлите название товара — покажу топ-5 позиций, которые можно добавить.",
        reply_markup=back_kbd(),
    )


@router.callback_query(F.data.startswith("search_add:"))
async def cb_search_add(call: CallbackQuery) -> None:
    sku = call.data.split(":", 1)[1]
    from bot.handlers.items import add_item_by_sku

    await call.answer()
    await add_item_by_sku(call.message, call.from_user.id, call.from_user.username, "wb", sku)


# ─────────────────────────── СТАТИСТИКА (АДМИН) ───────────────────────────

@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    if message.from_user.id not in settings.admins:
        await message.answer("⛔ Нет прав администратора.")
        return
    async with SessionLocal() as session:
        users_count = (await session.execute(select(func.count()).select_from(User))).scalar_one()
        items_count = (await session.execute(select(func.count()).select_from(Item))).scalar_one()
        points_count = (await session.execute(select(func.count()).select_from(PricePoint))).scalar_one()
        subs = (await session.execute(select(Subscription))).scalars().all()
        active_subs = 0
        revenue = 0.0
        now = datetime.now(timezone.utc)
        for s in subs:
            if s.paid_until > now:
                active_subs += 1
            revenue += TARIFFS.get(s.tariff, {}).get("price", 0)
        await message.answer(
            f"📊 <b>Статистика MarketSignal</b>\n\n"
            f"Пользователей: <b>{users_count}</b>\n"
            f"Активных подписок: <b>{active_subs}</b>\n"
            f"Всего товаров: <b>{items_count}</b>\n"
            f"Точек цен: <b>{points_count}</b>\n"
            f"Начислено по подпискам: <b>{revenue:,.0f} ₽</b>".replace(",", " "),
        )
