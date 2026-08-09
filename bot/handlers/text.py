"""Единый обработчик текстовых сообщений: pending-действия + добавление артикула.

Все роутеры кладут «ожидания» в PENDING (bot/services), а этот хендлер
распределяет ввод по нужным действиям. Это исключает конфликты нескольких
F.text-хендлеров в разных роутерах.
"""

from aiogram import F, Router
from aiogram.dispatcher.event.bases import SkipHandler
from aiogram.types import Message
from sqlalchemy import select

from bot.services import PENDING
from core.db import SessionLocal
from core.margin import calculate_margin, parse_margin_input
from core.models import Item, PriceAlert
from core.pricing import nice_price

router = Router()


@router.message(F.text)
async def dispatch_text(message: Message) -> None:
    text = message.text.strip()
    if text.startswith("/"):
        # Команды обрабатываются в своих роутерах — пропускаем дальше.
        raise SkipHandler

    uid = message.from_user.id
    pending = PENDING.pop(uid, None)
    if pending is not None:
        action, payload = pending
        if action == "alert":
            await _set_alert(message, payload)
        elif action == "note":
            await _set_note(message, payload)
        elif action == "margin":
            await _calc_margin(message)
        elif action == "search":
            await _search(message)
        return

    await _add_item(message, text)


# ─────────────────────────── АРТИКУЛ ───────────────────────────

async def _add_item(message: Message, text: str) -> None:
    from bot.handlers.items import add_item_by_sku, parse_sku

    marketplace, sku = parse_sku(text)
    if not sku:
        await message.answer("Не понял артикул. Пришлите число (WB) или текст (Ozon).")
        return
    await add_item_by_sku(message, message.from_user.id, message.from_user.username, marketplace, sku)


# ─────────────────────────── ЦЕЛЕВАЯ ЦЕНА ───────────────────────────

async def _set_alert(message: Message, item_id: int | None) -> None:
    if item_id is None:
        return
    try:
        value = float(message.text.replace(",", ".").replace(" ", ""))
    except ValueError:
        await message.answer("Это не число. Пришлите цену цифрами, например <code>1500</code>.")
        return
    if value <= 0:
        await message.answer("Цена должна быть больше нуля.")
        return
    async with SessionLocal() as session:
        old_result = await session.execute(
            select(PriceAlert).where(PriceAlert.item_id == item_id, PriceAlert.active.is_(True))
        )
        old = old_result.scalar_one_or_none()
        if old:
            old.active = False
        session.add(PriceAlert(item_id=item_id, target_price=value))
        await session.commit()
    await message.answer(f"✅ Цель установлена: <b>{nice_price(value)}</b>. Уведомлю при падении цены.")
    from bot.handlers.items import show_card

    await show_card(message, message.from_user.id, item_id)


# ─────────────────────────── ЗАМЕТКА ───────────────────────────

async def _set_note(message: Message, item_id: int | None) -> None:
    if item_id is None:
        return
    text = message.text.strip()
    if text in ("-", "—", "удалить"):
        text = None
    elif len(text) > 200:
        await message.answer("Слишком длинная заметка (максимум 200 символов).")
        return
    async with SessionLocal() as session:
        result = await session.execute(select(Item).where(Item.id == item_id))
        item = result.scalar_one_or_none()
        if item is None:
            await message.answer("Товар не найден.")
            return
        item.note = text
        await session.commit()
    await message.answer("🗒 Заметка сохранена." if text else "🗒 Заметка удалена.")
    from bot.handlers.items import show_card

    await show_card(message, message.from_user.id, item_id)


# ─────────────────────────── КАЛЬКУЛЯТОР МАРЖИ ───────────────────────────

async def _calc_margin(message: Message) -> None:
    values, error = parse_margin_input(message.text)
    if error:
        await message.answer(error)
        return
    result = calculate_margin(values[0], values[1], values[2], values[3],
                              values[4] if len(values) > 4 else 0.0)
    verdict = ""
    if result.margin_pct >= 25:
        verdict = "🟢 <b>Отличная маржа!</b>"
    elif result.margin_pct >= 10:
        verdict = "🟡 Нормальная маржа."
    elif result.profit < 0:
        verdict = "🔴 Вы работаете в минус."
    else:
        verdict = "🟠 Низкая маржа — присмотритесь к цене."
    await message.answer("\n".join(result.parts) + "\n\n" + verdict)


# ─────────────────────────── ПОИСК ПО WB ───────────────────────────

async def _search(message: Message) -> None:
    query = message.text.strip()[:60]
    if not query:
        return
    from bot.services import wbc

    await message.answer(f"🔎 Ищу «{query}»…")
    cards = await wbc.get_catalog(query, limit=10)
    if not cards:
        await message.answer("Не удалось получить каталог (возможно, гео-блок WB).")
        return
    rows = []
    for c in cards[:5]:
        rows.append([{"text": f"{c.title[:40]} · {nice_price(c.price)}", "callback_data": f"search_add:{c.sku}"}])
    rows.append([{"text": "◀ Назад", "callback_data": "menu"}])
    await message.answer(
        "Нажмите на товар, чтобы добавить его в отслеживание:",
        reply_markup={"inline_keyboard": rows},
    )
