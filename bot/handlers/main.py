from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import func, select

from config.settings import settings
from core.db import SessionLocal
from core.growth import find_growth
from core.models import Item, PricePoint, Subscription, User
from core.pricing import TARIFFS, nice_price, tariff_limit
from core.tracker import get_history, render_history
from parser.ozon.client import OzonClient
from parser.scheduler import Tracker
from parser.wb.client import WbClient

bot = Bot(
    token=settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()
tracker = Tracker()
wbc = WbClient()
ozc = OzonClient()

BACK = InlineKeyboardButton(text="◀ Назад", callback_data="menu")
MENU_KBD = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="📦 Мои товары", callback_data="my_items")],
    [InlineKeyboardButton(text="➕ Добавить товар", callback_data="add_item")],
    [InlineKeyboardButton(text="🔥 Растущие товары", callback_data="growth")],
    [InlineKeyboardButton(text="💎 Тарифы / Подписка", callback_data="plans")],
    [InlineKeyboardButton(text="📈 История цены", callback_data="history")],
])


async def ensure_user(tg_id: int, username: str | None = None) -> User:
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(tg_id=tg_id, username=username, tariff="free")
            session.add(user)
            await session.commit()
            await session.refresh(user)
        elif username and user.username != username:
            user.username = username
            await session.commit()
        return user


async def notify(tg_id: int, text: str) -> None:
    try:
        await bot.send_message(tg_id, text)
    except Exception as exc:  # noqa: BLE001
        print(f"[notify] failed to {tg_id}: {exc}")


@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = await ensure_user(message.from_user.id, message.from_user.username)
    status = "💎 PRO" if user.tariff == "pro" else ("🚀 Starter" if user.tariff == "starter" else "Бесплатный")
    await message.answer(
        f"Добро пожаловать в <b>MarketSignal</b>!\n\n"
        f"Статус: {status}\n\n"
        f"Я слежу за ценами на Wildberries и Ozon, показываю остатки, "
        f"отслеживаю конкурентов и подсказываю, что сейчас выгодно завезти.\n\n"
        f"Выберите действие:",
        reply_markup=MENU_KBD,
    )


@dp.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Меню:", reply_markup=MENU_KBD)


@dp.message(Command("now"))
async def cmd_now(message: Message) -> None:
    await show_my_items(message)


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
                "Нажмите «➕ Добавить товар» и пришлите артикул.",
                reply_markup=MENU_KBD,
            )
            return

        lines = []
        for it in items:
            last = await session.execute(
                select(PricePoint)
                .where(PricePoint.item_id == it.id)
                .order_by(PricePoint.ts.desc())
                .limit(1)
            )
            pp = last.scalar_one_or_none()
            title = (it.title or it.sku)[:40]
            price = nice_price(pp.price) if pp else "—"
            stock = f", остатки {pp.stock}" if pp and pp.stock is not None else ""
            mp = "WB" if it.marketplace == "wb" else "OZ"
            lines.append(f"<b>{title}</b>\n  {mp} {it.sku} · {price}{stock}")

        await source.answer("📦 <b>Ваши товары:</b>\n\n" + "\n\n".join(lines), reply_markup=MENU_KBD)


@dp.callback_query(F.data == "my_items")
async def cb_my_items(call: CallbackQuery) -> None:
    await call.answer()
    await show_my_items(call.message)


@dp.callback_query(F.data == "add_item")
async def cb_add_item(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer(
        "Пришлите артикул товара.\n\n"
        "Для <b>Wildberries</b> — артикул (nm): <code>123456789</code>\n"
        "Для <b>Ozon</b> — артикул продавца (offer_id): <code>abc-123</code>\n\n"
        "Можно указать площадку: <code>wb 123456789</code> или <code>ozon abc-123</code>"
    )


@dp.message(Command("grant"))
async def cmd_grant(message: Message) -> None:
    if message.from_user.id not in settings.admins:
        await message.answer("⛔ Нет прав администратора.")
        return
    parts = message.text.split()
    if len(parts) != 4:
        await message.answer("Использование: /grant <user_id> <free|starter|pro> <days>")
        return
    try:
        tg_id, tariff, days = int(parts[1]), parts[2].lower(), int(parts[3])
    except ValueError:
        await message.answer("Неверные аргументы. Пример: /grant 123456789 starter 30")
        return
    if tariff not in TARIFFS:
        await message.answer("Тариф должен быть: free, starter или pro.")
        return

    from datetime import datetime, timedelta, timezone

    paid_until = datetime.now(timezone.utc) + timedelta(days=days)
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(tg_id=tg_id, tariff=tariff)
            session.add(user)
            await session.flush()
        else:
            user.tariff = tariff
        user.paid_until = paid_until
        session.add(
            Subscription(
                user_id=user.id,
                tariff=tariff,
                paid_until=paid_until,
                payment_id=f"manual:{message.message_id}",
            )
        )
        await session.commit()
    await message.answer(
        f"✅ Пользователь {tg_id} активирован: тариф <b>{TARIFFS[tariff]['name']}</b> "
        f"до {paid_until.strftime('%d.%m.%Y')}."
    )
    await notify(tg_id, f"🎉 Ваша подписка <b>{TARIFFS[tariff]['name']}</b> активирована до {paid_until.strftime('%d.%m.%Y')}!")


@dp.message(F.text)
async def handle_text(message: Message) -> None:
    text = message.text.strip()
    if text.startswith("/"):
        return

    async with SessionLocal() as session:
        user = await ensure_user(message.from_user.id, message.from_user.username)

        parts = text.split(maxsplit=1)
        if len(parts) == 2 and parts[0].lower() in ("wb", "ozon", "oz", "wildberries"):
            marketplace = "wb" if parts[0].lower() in ("wb", "wildberries") else "ozon"
            sku = parts[1].strip()
        else:
            marketplace = "wb" if text.isdigit() else "ozon"
            sku = text

        if not sku:
            await message.answer("Не понял артикул. Пришлите число (WB) или текст (Ozon).")
            return

        count = await session.execute(
            select(func.count()).select_from(Item).where(Item.user_id == user.id)
        )
        current = count.scalar_one()
        limit = tariff_limit(user.tariff)
        if current >= limit:
            await message.answer(
                f"Лимит тарифа <b>{TARIFFS[user.tariff]['name']}</b> — {limit} товаров.\n"
                "Оформите подписку, чтобы добавить больше.",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton("💎 К тарифам", callback_data="plans")]
                ]),
            )
            return

        existing = await session.execute(
            select(Item).where(Item.user_id == user.id, Item.sku == sku)
        )
        if existing.scalar_one_or_none():
            await message.answer("Этот товар уже отслеживается.")
            return

        if marketplace == "wb":
            data = await wbc.get_card(sku)
        else:
            data = await ozc.get_product_by_sku(sku) if ozc.configured else None
            if data is None:
                # Нет ключа Ozon — всё равно сохраняем, цена появится после настройки ключа
                data = None

        if marketplace == "wb" and data is None:
            await message.answer("Не нашёл товар на Wildberries. Проверьте артикул.")
            return

        item = Item(user_id=user.id, marketplace=marketplace, sku=sku)
        if data:
            item.title = data.title
            session.add(item)
            await session.flush()
            from core.tracker import record_price
            await record_price(session, item, data)
        else:
            session.add(item)

        await session.commit()
        title = (item.title or item.sku)[:40]
        await message.answer(f"✅ Добавлено: <b>{title}</b> ({'WB' if marketplace=='wb' else 'OZ'})", reply_markup=MENU_KBD)


@dp.callback_query(F.data == "growth")
async def cb_growth(call: CallbackQuery) -> None:
    await call.answer("Ищу растущие товары…")
    cards = await wbc.get_catalog("топ продаж", limit=40)
    if not cards:
        await call.message.answer("Не удалось получить каталог. Попробуйте позже.")
        return
    found = find_growth(cards, top_n=8)
    lines = ["🔥 <b>Растущие товары:</b>\n"]
    for c in found:
        price = nice_price(c.price)
        lines.append(f"{c.title[:45]}\n  <code>{c.sku}</code> · {price} · остатки {c.stock}\n  ↳ {c.reason}")
    await call.message.answer("\n\n".join(lines), reply_markup=MENU_KBD)


@dp.callback_query(F.data == "plans")
async def cb_plans(call: CallbackQuery) -> None:
    await call.answer()
    text = (
        "💎 <b>Тарифы MarketSignal:</b>\n\n"
        "🆓 <b>Free</b> — 0 ₽\n  1 товар, 1 отчёт в день\n\n"
        "🚀 <b>Starter</b> — 299 ₽/мес\n  10 товаров, алерты на изменение цены, история 30 дней\n\n"
        "💎 <b>Pro</b> — 799 ₽/мес\n  50 товаров, растущие товары, история 90 дней\n\n"
        "Оплата: напишите администратору @your_admin и пришлите скрин оплаты — "
        "доступ активируем вручную в течение 10 минут."
    )
    await call.message.answer(text, reply_markup=MENU_KBD)


@dp.callback_query(F.data == "history")
async def cb_history(call: CallbackQuery) -> None:
    await call.answer()
    async with SessionLocal() as session:
        user = await ensure_user(call.from_user.id, call.from_user.username)
        result = await session.execute(
            select(Item).where(Item.user_id == user.id).order_by(Item.id).limit(1)
        )
        item = result.scalar_one_or_none()
        if item is None:
            await call.message.answer("Сначала добавьте товар.", reply_markup=MENU_KBD)
            return
        points = await get_history(session, item.id, limit=15)
        await call.message.answer(
            f"Товар: <b>{item.title or item.sku}</b>\n" + render_history(points),
            reply_markup=MENU_KBD,
        )
