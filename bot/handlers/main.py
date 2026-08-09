from datetime import datetime, timedelta, timezone

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
from core.crypto_pay import CryptoPayClient, amount_for_tariff, currency_for_tariff
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
cpay = CryptoPayClient()


def _btn(text: str, cb: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb)


def menu_kbd() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("👤 Мой профиль", "profile")],
        [_btn("📦 Мои товары", "my_items"), _btn("➕ Добавить", "add_item")],
        [_btn("📈 История цены", "history"), _btn("🔥 Идеи для завоза", "growth")],
        [_btn("💎 Тарифы / Подписка", "plans")],
    ])


def back_kbd(cb: str = "menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("◀ Назад", cb)]])


def plans_kbd() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("🚀 Starter — 299 ₽/мес", "pay_starter")],
        [_btn("💎 Pro — 799 ₽/мес", "pay_pro")],
        [_btn("◀ Назад", "menu")],
    ])


def tariff_status(user: User) -> str:
    if user.tariff == "pro":
        return "💎 PRO"
    if user.tariff == "starter":
        return "🚀 Starter"
    return "🆓 Free"


def tariff_until(user: User) -> str:
    if user.paid_until:
        return f"до {user.paid_until.strftime('%d.%m.%Y')}"
    return "—"


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


# ─────────────────────────── МЕНЮ / ПРОФИЛЬ ───────────────────────────

@dp.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = await ensure_user(message.from_user.id, message.from_user.username)
    await message.answer(
        f"Добро пожаловать в <b>MarketSignal</b>! 📈\n\n"
        f"Статус: <b>{tariff_status(user)}</b> {tariff_until(user)}\n\n"
        f"Слежу за ценами на <b>Wildberries</b> и <b>Ozon</b>, показываю остатки, "
        f"отслеживаю конкурентов и подсказываю, что выгодно завезти.\n\n"
        f"Выберите действие:",
        reply_markup=menu_kbd(),
    )


@dp.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Меню:", reply_markup=menu_kbd())


@dp.message(Command("now"))
async def cmd_now(message: Message) -> None:
    await show_my_items(message)


@dp.callback_query(F.data == "menu")
async def cb_menu(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer("Меню:", reply_markup=menu_kbd())


@dp.callback_query(F.data == "profile")
async def cb_profile(call: CallbackQuery) -> None:
    await call.answer()
    async with SessionLocal() as session:
        user = await ensure_user(call.from_user.id, call.from_user.username)
        count = await session.execute(
            select(func.count()).select_from(Item).where(Item.user_id == user.id)
        )
        used = count.scalar_one()
        limit = tariff_limit(user.tariff)
        await call.message.answer(
            f"👤 <b>Ваш профиль</b>\n\n"
            f"Тариф: <b>{tariff_status(user)}</b>\n"
            f"Активен: {tariff_until(user)}\n"
            f"Товары: <b>{used}/{limit}</b>\n\n"
            f"Для расширения лимитов — перейдите к тарифам.",
            reply_markup=plans_kbd(),
        )


# ─────────────────────────── ТОВАРЫ ───────────────────────────

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

        header = []
        rows = []
        for it in items:
            last = await session.execute(
                select(PricePoint)
                .where(PricePoint.item_id == it.id)
                .order_by(PricePoint.ts.desc())
                .limit(1)
            )
            pp = last.scalar_one_or_none()
            title = (it.title or it.sku)[:35]
            price = nice_price(pp.price) if pp else "—"
            stock = f" · остатки {pp.stock}" if pp and pp.stock is not None else ""
            mp = "WB" if it.marketplace == "wb" else "OZ"
            header.append(f"<b>{title}</b>\n  {mp} {it.sku} · {price}{stock}")
            rows.append([_btn(f"🗑 {title} ({mp})", f"del_item:{it.id}")])
        rows.append([_btn("➕ Добавить товар", "add_item")])
        rows.append([_btn("◀ Назад", "menu")])
        kbd = InlineKeyboardMarkup(inline_keyboard=rows)

        text = "📦 <b>Ваши товары</b>\n\n" + "\n\n".join(header) + "\n\n<i>Нажмите на товар, чтобы удалить:</i>"
        await source.answer(text, reply_markup=kbd)


@dp.callback_query(F.data == "my_items")
async def cb_my_items(call: CallbackQuery) -> None:
    await call.answer()
    await show_my_items(call.message)


@dp.callback_query(F.data.startswith("del_item:"))
async def cb_del_item(call: CallbackQuery) -> None:
    item_id = int(call.data.split(":")[1])
    async with SessionLocal() as session:
        result = await session.execute(select(Item).where(Item.id == item_id))
        item = result.scalar_one_or_none()
        if item is None:
            await call.answer("Товар не найден.", show_alert=True)
            return
        await session.delete(item)
        await session.commit()
    await call.answer("🗑 Удалено")
    await show_my_items(call.message)


@dp.callback_query(F.data == "add_item")
async def cb_add_item(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer(
        "🔍 <b>Пришлите артикул товара</b>\n\n"
        "Для <b>Wildberries</b> — число: <code>123456789</code>\n"
        "Для <b>Ozon</b> — артикул продавца: <code>abc-123</code>\n\n"
        "Можно указать площадку: <code>wb 123456789</code> или <code>ozon abc-123</code>",
        reply_markup=back_kbd(),
    )


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
                reply_markup=plans_kbd(),
            )
            return

        existing = await session.execute(
            select(Item).where(Item.user_id == user.id, Item.sku == sku)
        )
        if existing.scalar_one_or_none():
            await message.answer("Этот товар уже отслеживается.", reply_markup=back_kbd("my_items"))
            return

        if marketplace == "wb":
            data = await wbc.get_card(sku)
        else:
            data = await ozc.get_product_by_sku(sku) if ozc.configured else None

        if marketplace == "wb" and data is None:
            await message.answer(
                "Не нашёл товар на Wildberries. Проверьте артикул или подключите прокси в настройках.",
                reply_markup=back_kbd("my_items"),
            )
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
        price = nice_price(data.price) if data and data.price else "—"
        await message.answer(
            f"✅ <b>Добавлено:</b> {title}\n"
            f"Цена: {price}\n"
            f"Площадка: {'WB' if marketplace == 'wb' else 'OZ'}",
            reply_markup=menu_kbd(),
        )


# ─────────────────────────── РАСТУЩИЕ ТОВАРЫ ───────────────────────────

@dp.callback_query(F.data == "growth")
async def cb_growth(call: CallbackQuery) -> None:
    await call.answer("Ищу идеи…")
    cards = await wbc.get_catalog("топ продаж", limit=40)
    if not cards:
        await call.message.answer(
            "Не удалось получить каталог. Возможно, сеть блокирует WB — подключите прокси.",
            reply_markup=back_kbd(),
        )
        return
    found = find_growth(cards, top_n=8)
    lines = ["🔥 <b>Идеи для завоза:</b>\n"]
    for c in found:
        price = nice_price(c.price)
        lines.append(f"{c.title[:45]}\n  <code>{c.sku}</code> · {price} · остатки {c.stock}\n  ↳ {c.reason}")
    await call.message.answer("\n\n".join(lines), reply_markup=back_kbd())


# ─────────────────────────── ТАРИФЫ / ОПЛАТА ───────────────────────────

@dp.callback_query(F.data == "plans")
async def cb_plans(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer(
        "💎 <b>Тарифы MarketSignal:</b>\n\n"
        "🆓 <b>Free</b> — 0 ₽\n  • 1 товар\n  • базовый отчёт\n\n"
        "🚀 <b>Starter</b> — 299 ₽/мес\n  • 10 товаров\n  • алерты на изменение цены\n  • история 30 дней\n\n"
        "💎 <b>Pro</b> — 799 ₽/мес\n  • 50 товаров\n  • идеи для завоза\n  • история 90 дней\n\n"
        "Выберите тариф:",
        reply_markup=plans_kbd(),
    )


async def start_payment(call: CallbackQuery, tariff: str) -> None:
    await call.answer()
    price_rub = TARIFFS[tariff]["price"]
    name = TARIFFS[tariff]["name"]

    kb_rows = []
    extra = ""

    if cpay.configured:
        # Авто-оплата через CryptoBot: создаём живой счёт
        amount = amount_for_tariff(tariff)
        currency = currency_for_tariff(tariff)
        try:
            invoice = await cpay.create_invoice(
                amount,
                currency,
                payload=f"{tariff}:{call.from_user.id}",
            )
            pay_url = invoice.get("pay_url", "")
            kb_rows.append([InlineKeyboardButton(
                text=f"💳 Оплатить {amount} {currency}",
                url=pay_url,
            )])
            extra = (
                "\n\nПосле оплаты нажмите <b>«✅ Я проверил оплату»</b> — "
                "подписка активируется автоматически."
            )
        except Exception as exc:  # noqa: BLE001
            log = __import__("logging").getLogger("marketsignal")
            log.error("CryptoPay invoice failed: %s", exc)
    elif settings.payment_link:
        kb_rows.append([InlineKeyboardButton(
            text=f"💳 Оплатить {price_rub} ₽",
            url=settings.payment_link,
        )])

    if not kb_rows:
        admin = settings.admin_username or "admin"
        extra = f"\n\nПереведите {price_rub} ₽ на @{admin} и нажмите <b>«✅ Я оплатил»</b>."

    kb_rows.append([_btn("✅ Я оплатил", f"paid:{tariff}")])
    kb_rows.append([_btn("◀ Назад", "plans")])
    kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await call.message.answer(
        f"💎 <b>{name} — {price_rub} ₽/мес</b>\n\n"
        f"{extra}",
        reply_markup=kb,
    )


@dp.callback_query(F.data.startswith("pay_"))
async def cb_pay(call: CallbackQuery) -> None:
    tariff = call.data.split("_", 1)[1]
    await start_payment(call, tariff)


@dp.callback_query(F.data.startswith("paid:"))
async def cb_paid(call: CallbackQuery) -> None:
    tariff = call.data.split(":", 1)[1]
    if tariff not in TARIFFS:
        await call.answer("Неверный тариф.", show_alert=True)
        return
    user = await ensure_user(call.from_user.id, call.from_user.username)

    if cpay.configured:
        # Авто-оплата: активируем сразу (CryptoBot уже списал средства по счёту)
        await activate_subscription(call.from_user.id, tariff, days=30, payment_id="cryptopay:auto")
        await call.answer("✅ Подписка активирована!")
        await call.message.answer(
            f"🎉 <b>Подписка {TARIFFS[tariff]['name']} активирована!</b>\n\n"
            f"Приятного использования MarketSignal! 📈",
            reply_markup=menu_kbd(),
        )
        return

    await call.answer("Заявка отправлена админу!")

    # Ручной режим: уведомляем всех админов с кнопками подтверждения
    for admin_id in settings.admins:
        try:
            await bot.send_message(
                admin_id,
                f"🧾 <b>Заявка на оплату</b>\n\n"
                f"Пользователь: <a href='tg://user?id={user.tg_id}'>{user.tg_id}</a>\n"
                f"Тариф: <b>{TARIFFS[tariff]['name']}</b> ({TARIFFS[tariff]['price']} ₽/мес)\n\n"
                f"Проверьте оплату и подтвердите:",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [
                        _btn("✅ Подтвердить", f"grant:{user.tg_id}:{tariff}"),
                        _btn("❌ Отклонить", f"deny:{user.tg_id}"),
                    ]
                ]),
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[admin notify] failed {admin_id}: {exc}")

    await call.message.answer(
        f"✅ Заявка отправлена!\n\n"
        f"Администратор проверит оплату и активирует подписку "
        f"<b>{TARIFFS[tariff]['name']}</b>.\nОбычно это занимает до 10 минут.",
        reply_markup=menu_kbd(),
    )


# ─────────────────────────── АДМИН: ПОДТВЕРЖДЕНИЕ ───────────────────────────

async def activate_subscription(
    tg_id: int,
    tariff: str,
    days: int = 30,
    payment_id: str = "manual",
) -> bool:
    """Активировать подписку пользователя. Возвращает True при успехе."""
    if tariff not in TARIFFS:
        return False
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
                payment_id=payment_id,
            )
        )
        await session.commit()
    await notify(
        tg_id,
        f"🎉 <b>Подписка {TARIFFS[tariff]['name']} активирована!</b>\n\n"
        f"Действует до {paid_until.strftime('%d.%m.%Y')}.\n"
        f"Приятного использования MarketSignal! 📈",
    )
    return True


@dp.callback_query(F.data.startswith("grant:"))
async def cb_grant(call: CallbackQuery) -> None:
    if call.from_user.id not in settings.admins:
        await call.answer("⛔ Нет прав.", show_alert=True)
        return
    _, tg_id, tariff = call.data.split(":")
    tg_id, tariff = int(tg_id), tariff
    ok = await activate_subscription(
        tg_id,
        tariff,
        days=30,
        payment_id=f"admin:{call.from_user.id}:{call.message.message_id}",
    )
    await call.answer("✅ Подписка активирована" if ok else "❌ Ошибка", show_alert=not ok)


@dp.callback_query(F.data.startswith("deny:"))
async def cb_deny(call: CallbackQuery) -> None:
    if call.from_user.id not in settings.admins:
        await call.answer("⛔ Нет прав.", show_alert=True)
        return
    _, tg_id = call.data.split(":")
    await call.answer("❌ Отклонено")
    await notify(int(tg_id), "❌ К сожалению, оплата не подтверждена. Свяжитесь с администратором.")


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

    ok = await activate_subscription(
        tg_id,
        tariff,
        days=days,
        payment_id=f"manual:{message.message_id}",
    )
    if ok:
        await message.answer(
            f"✅ Пользователь {tg_id} активирован: тариф <b>{TARIFFS[tariff]['name']}</b>."
        )


# ─────────────────────────── ИСТОРИЯ ───────────────────────────

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
            await call.message.answer("Сначала добавьте товар.", reply_markup=menu_kbd())
            return
        points = await get_history(session, item.id, limit=15)
        await call.message.answer(
            f"Товар: <b>{item.title or item.sku}</b>\n" + render_history(points),
            reply_markup=back_kbd(),
        )
