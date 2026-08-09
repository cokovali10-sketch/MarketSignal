"""Товары: список, карточка, история, график, целевая цена, заметки, экспорт, удаление."""

import csv
import io
import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy import func, select

from bot.services import (
    PENDING,
    back_kbd,
    ensure_user,
    menu_kbd,
    ozc,
    plans_kbd,
    wbc,
)
from core.chart import render_chart
from core.db import SessionLocal
from core.models import Item, PriceAlert, PricePoint
from core.pricing import TARIFFS, nice_price, tariff_limit
from core.tracker import get_history, record_price

log = logging.getLogger(__name__)
router = Router()


# ─────────────────────────── ВСПОМОГАТЕЛЬНЫЕ ───────────────────────────

async def _load_item(user_id: int, item_id: int) -> Item | None:
    async with SessionLocal() as session:
        result = await session.execute(
            select(Item).where(Item.id == item_id, Item.user_id == user_id)
        )
        return result.scalar_one_or_none()


async def _last_point(session, item_id: int) -> PricePoint | None:
    result = await session.execute(
        select(PricePoint)
        .where(PricePoint.item_id == item_id)
        .order_by(PricePoint.ts.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _render_item_card(item: Item, pp: PricePoint | None, alert: PriceAlert | None) -> str:
    price = nice_price(pp.price) if pp else "—"
    stock = f" · остатки <b>{pp.stock}</b>" if pp and pp.stock is not None else ""
    discount = ""
    if pp and pp.price and pp.old_price and pp.old_price > pp.price:
        pct = int((pp.old_price - pp.price) / pp.old_price * 100)
        discount = f" 🔥 −{pct}%"
    alert_line = ""
    if alert and alert.active:
        alert_line = f"\n🔔 Цель: <b>{nice_price(alert.target_price)}</b>"
    note_line = f"\n🗒 Заметка: {item.note}" if item.note else ""
    mp = "WB" if item.marketplace == "wb" else "Ozon"
    url = (
        f"https://www.wildberries.ru/catalog/{item.sku}/detail.aspx"
        if item.marketplace == "wb"
        else f"https://www.ozon.ru/product/{item.sku}"
    )
    return (
        f"📦 <b>{item.title or item.sku}</b>\n"
        f"Площадка: {mp} · Артикул: <code>{item.sku}</code>\n"
        f"Цена: <b>{price}</b>{stock}{discount}\n"
        f"Ссылка: {url}{alert_line}{note_line}"
    )


def _card_kbd(item_id: int) -> dict:
    return {
        "inline_keyboard": [
            [
                {"text": "📈 График", "callback_data": f"chart:{item_id}"},
                {"text": "🔔 Цель", "callback_data": f"alert_menu:{item_id}"},
            ],
            [
                {"text": "🗒 Заметка", "callback_data": f"note:{item_id}"},
                {"text": "📄 CSV", "callback_data": f"export:{item_id}"},
            ],
            [
                {"text": "🔄 Обновить", "callback_data": f"refresh:{item_id}"},
                {"text": "🗑 Удалить", "callback_data": f"del_item:{item_id}"},
            ],
            [{"text": "◀ Назад", "callback_data": "items"}],
        ]
    }


async def show_card(target, tg_id: int, item_id: int) -> None:
    item = await _load_item(tg_id, item_id)
    if item is None:
        await target.answer("Товар не найден.", reply_markup=menu_kbd())
        return
    async with SessionLocal() as session:
        pp = await _last_point(session, item.id)
        alert_result = await session.execute(
            select(PriceAlert).where(PriceAlert.item_id == item.id, PriceAlert.active.is_(True))
        )
        alert = alert_result.scalar_one_or_none()
    await target.answer(
        _render_item_card(item, pp, alert),
        reply_markup=_card_kbd(item.id),
        disable_web_page_preview=True,
    )


# ─────────────────────────── СПИСОК / ДОБАВЛЕНИЕ ───────────────────────────

@router.message(Command("now"))
async def cmd_now(message: Message) -> None:
    await show_my_items(message)


@router.callback_query(F.data == "items")
async def cb_my_items(call: CallbackQuery) -> None:
    await call.answer()
    await show_my_items(call.message)


async def show_my_items(source: Message) -> None:
    async with SessionLocal() as session:
        user = await ensure_user(source.from_user.id, source.from_user.username)
        result = await session.execute(
            select(Item).where(Item.user_id == user.id).order_by(Item.id)
        )
        items = list(result.scalars().all())

        if not items:
            await source.answer(
                "У вас пока нет отслеживаемых товаров.\n"
                "Нажмите «➕ Добавить» и пришлите артикул.",
                reply_markup=back_kbd(),
            )
            return

        rows = []
        for it in items:
            pp = await _last_point(session, it.id)
            title = (it.title or it.sku)[:30]
            price = nice_price(pp.price) if pp else "—"
            mp = "WB" if it.marketplace == "wb" else "OZ"
            rows.append([
                {"text": f"📦 {title} ({mp}) · {price}", "callback_data": f"card:{it.id}"}
            ])
        rows.append([{"text": "➕ Добавить товар", "callback_data": "add_item"}])
        rows.append([{"text": "◀ Назад", "callback_data": "menu"}])

        text = f"📦 <b>Ваши товары</b> ({len(items)})\n\n<i>Нажмите на товар, чтобы открыть карточку:</i>"
        await source.answer(text, reply_markup={"inline_keyboard": rows})


@router.callback_query(F.data.startswith("card:"))
async def cb_card(call: CallbackQuery) -> None:
    await call.answer()
    item_id = int(call.data.split(":", 1)[1])
    await show_card(call.message, call.from_user.id, item_id)


@router.callback_query(F.data == "add_item")
async def cb_add_item(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer(
        "🔍 <b>Пришлите артикул товара</b>\n\n"
        "Для <b>Wildberries</b> — число: <code>123456789</code>\n"
        "Для <b>Ozon</b> — артикул продавца: <code>abc-123</code>\n\n"
        "Можно указать площадку: <code>wb 123456789</code> или <code>ozon abc-123</code>\n\n"
        "Или пришлите <b>ссылку на товар</b> — артикул определится сам.",
        reply_markup=back_kbd(),
    )


def parse_sku(text: str) -> tuple[str, str]:
    """Определить площадку и артикул из текста или ссылки."""
    import re

    text = text.strip()
    if "wildberries.ru" in text or "wb.ru" in text:
        m = re.search(r"catalog/(\d+)/", text)
        if m:
            return "wb", m.group(1)
    if "ozon.ru" in text or "ozon.kz" in text:
        return "ozon", text.split("/")[-1].split("?")[0]
    parts = text.split(maxsplit=1)
    if len(parts) == 2 and parts[0].lower() in ("wb", "ozon", "oz", "wildberries"):
        marketplace = "wb" if parts[0].lower() in ("wb", "wildberries") else "ozon"
        return marketplace, parts[1].strip()
    marketplace = "wb" if text.isdigit() else "ozon"
    return marketplace, text


async def add_item_by_sku(target, tg_id: int, username: str | None, marketplace: str, sku: str) -> None:
    """Добавить товар в отслеживание и показать карточку."""
    async with SessionLocal() as session:
        user = await ensure_user(tg_id, username)

        count = await session.execute(
            select(func.count()).select_from(Item).where(Item.user_id == user.id)
        )
        current = count.scalar_one()
        limit = tariff_limit(user.tariff)
        if current >= limit:
            await target.answer(
                f"Лимит тарифа <b>{TARIFFS[user.tariff]['name']}</b> — {limit} товаров.\n"
                "Оформите подписку, чтобы добавить больше.",
                reply_markup=plans_kbd(),
            )
            return

        existing = await session.execute(
            select(Item).where(Item.user_id == user.id, Item.sku == sku)
        )
        if existing.scalar_one_or_none():
            await target.answer("Этот товар уже отслеживается.", reply_markup=back_kbd("items"))
            return

        if marketplace == "wb":
            data = await wbc.get_card(sku)
        else:
            data = await ozc.get_product_by_sku(sku) if ozc.configured else None

        if marketplace == "wb" and data is None:
            await target.answer(
                "Не нашёл товар на Wildberries. Проверьте артикул или сеть "
                "(WB гео-блокирует запросы из-за рубежа — нужен RU-прокси).",
                reply_markup=back_kbd("items"),
            )
            return

        item = Item(user_id=user.id, marketplace=marketplace, sku=sku)
        if data:
            item.title = data.title
            session.add(item)
            await session.flush()
            await record_price(session, item, data)
        else:
            session.add(item)

        await session.commit()
        await target.answer(
            f"✅ <b>Добавлено:</b> {item.title or item.sku}",
            reply_markup=menu_kbd(),
        )
        await show_card(target, user.tg_id, item.id)


# ─────────────────────────── ИСТОРИЯ / ГРАФИК ───────────────────────────

@router.callback_query(F.data == "history")
async def cb_history(call: CallbackQuery) -> None:
    await call.answer()
    user = await ensure_user(call.from_user.id, call.from_user.username)
    async with SessionLocal() as session:
        result = await session.execute(
            select(Item).where(Item.user_id == user.id).order_by(Item.id).limit(1)
        )
        item = result.scalar_one_or_none()
        if item is None:
            await call.message.answer("Сначала добавьте товар.", reply_markup=menu_kbd())
            return
    await show_card(call.message, user.tg_id, item.id)


@router.callback_query(F.data.startswith("chart:"))
async def cb_chart(call: CallbackQuery) -> None:
    await call.answer("Рисую график…")
    item_id = int(call.data.split(":", 1)[1])
    async with SessionLocal() as session:
        result = await session.execute(
            select(Item).where(Item.id == item_id, Item.user_id == call.from_user.id)
        )
        item = result.scalar_one_or_none()
        if item is None:
            await call.message.answer("Товар не найден.")
            return
        points = await get_history(session, item.id, limit=30)
        if len(points) < 2:
            await call.message.answer("Пока мало данных для графика (нужно минимум 2 точки).")
            return
        try:
            png = render_chart(points)
        except Exception as exc:  # noqa: BLE001
            log.exception("chart failed")
            await call.message.answer(f"Не удалось построить график: {exc}")
            return
        await call.message.answer_photo(
            BufferedInputFile(png, filename="history.png"),
            caption=f"📈 <b>{item.title or item.sku}</b> — история цены",
            reply_markup=back_kbd(f"card:{item.id}"),
        )


@router.callback_query(F.data.startswith("refresh:"))
async def cb_refresh(call: CallbackQuery) -> None:
    await call.answer("Обновляю…")
    item_id = int(call.data.split(":", 1)[1])
    item = await _load_item(call.from_user.id, item_id)
    if item is None:
        await call.message.answer("Товар не найден.")
        return
    if item.marketplace == "wb":
        data = await wbc.get_card(item.sku)
    else:
        data = await ozc.get_product_by_sku(item.sku) if ozc.configured else None
    if data:
        async with SessionLocal() as session:
            result = await session.execute(select(Item).where(Item.id == item.id))
            item = result.scalar_one()
            await record_price(session, item, data)
            await session.commit()
        await call.message.answer("✅ Данные обновлены.")
    else:
        await call.message.answer("Не удалось получить данные (возможно, гео-блок WB).")
    await show_card(call.message, call.from_user.id, item_id)


# ─────────────────────────── ЦЕЛЕВАЯ ЦЕНА (АЛЕРТ) ───────────────────────────

@router.callback_query(F.data.startswith("alert_menu:"))
async def cb_alert_menu(call: CallbackQuery) -> None:
    await call.answer()
    item_id = int(call.data.split(":", 1)[1])
    item = await _load_item(call.from_user.id, item_id)
    if item is None:
        await call.message.answer("Товар не найден.")
        return
    async with SessionLocal() as session:
        result = await session.execute(
            select(PriceAlert).where(PriceAlert.item_id == item.id, PriceAlert.active.is_(True))
        )
        alert = result.scalar_one_or_none()
    rows = []
    if alert:
        rows.append([
            {"text": f"🔔 Текущая цель: {nice_price(alert.target_price)}",
             "callback_data": f"alert_del:{item.id}"}
        ])
    rows.append([{"text": "➕ Установить цель", "callback_data": f"alert_set:{item.id}"}])
    rows.append([{"text": "◀ Назад", "callback_data": f"card:{item.id}"}])
    await call.message.answer(
        "🔔 <b>Целевая цена</b>\n\n"
        "Когда цена опустится до цели и ниже — я пришлю уведомление.\n"
        "Отправьте цену числом (например <code>1500</code>).",
        reply_markup={"inline_keyboard": rows},
    )


@router.callback_query(F.data.startswith("alert_set:"))
async def cb_alert_set(call: CallbackQuery) -> None:
    await call.answer()
    item_id = int(call.data.split(":", 1)[1])
    PENDING[call.from_user.id] = ("alert", item_id)
    await call.message.answer("Пришлите целевую цену числом, например: <code>1500</code>")


@router.callback_query(F.data.startswith("alert_del:"))
async def cb_alert_del(call: CallbackQuery) -> None:
    item_id = int(call.data.split(":", 1)[1])
    item = await _load_item(call.from_user.id, item_id)
    if item is None:
        await call.answer("Товар не найден.", show_alert=True)
        return
    async with SessionLocal() as session:
        result = await session.execute(
            select(PriceAlert).where(PriceAlert.item_id == item.id, PriceAlert.active.is_(True))
        )
        alert = result.scalar_one_or_none()
        if alert:
            alert.active = False
            await session.commit()
    await call.answer("🔔 Цель удалена")
    await cb_alert_menu(call)


# ─────────────────────────── ЗАМЕТКА / ЭКСПОРТ / УДАЛЕНИЕ ───────────────────────────

@router.callback_query(F.data.startswith("note:"))
async def cb_note(call: CallbackQuery) -> None:
    await call.answer()
    item_id = int(call.data.split(":", 1)[1])
    PENDING[call.from_user.id] = ("note", item_id)
    await call.message.answer("Пришлите текст заметки (до 200 символов), или «-» чтобы удалить:")


@router.callback_query(F.data.startswith("export:"))
async def cb_export(call: CallbackQuery) -> None:
    await call.answer()
    item_id = int(call.data.split(":", 1)[1])
    item = await _load_item(call.from_user.id, item_id)
    if item is None:
        await call.message.answer("Товар не найден.")
        return
    async with SessionLocal() as session:
        points = await get_history(session, item.id, limit=500)
    if not points:
        await call.message.answer("Нет данных для экспорта.")
        return
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Дата", "Цена, руб", "Старая цена, руб", "Остатки"])
    for p in points:
        writer.writerow([
            p.ts.strftime("%Y-%m-%d %H:%M:%S"),
            p.price if p.price is not None else "",
            p.old_price if p.old_price is not None else "",
            p.stock if p.stock is not None else "",
        ])
    data = buf.getvalue().encode("utf-8-sig")
    await call.message.answer_document(
        BufferedInputFile(data, filename=f"history_{item.sku}.csv"),
        caption=f"📄 История цены: {item.title or item.sku}",
    )


@router.callback_query(F.data.startswith("del_item:"))
async def cb_del_item(call: CallbackQuery) -> None:
    item_id = int(call.data.split(":", 1)[1])
    item = await _load_item(call.from_user.id, item_id)
    if item is None:
        await call.answer("Товар не найден.", show_alert=True)
        return
    async with SessionLocal() as session:
        result = await session.execute(select(Item).where(Item.id == item.id))
        item = result.scalar_one()
        await session.delete(item)
        await session.commit()
    await call.answer("🗑 Удалено")
    await show_my_items(call.message)
