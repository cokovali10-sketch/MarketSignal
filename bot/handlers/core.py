"""Основные обработчики: старт, меню, профиль, идеи для завоза."""

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select

from bot.services import (
    back_kbd,
    ensure_user,
    menu_kbd,
    plans_kbd,
    tariff_status,
    tariff_until,
    wbc,
)
from config.settings import settings
from core.db import SessionLocal
from core.growth import find_growth
from core.models import Item, User
from core.pricing import nice_price, tariff_limit

router = Router()

START_TEXT = (
    "Добро пожаловать в <b>MarketSignal</b>! 📈\n\n"
    "Статус: <b>{status}</b> {until}\n\n"
    "Слежу за ценами на <b>Wildberries</b> и <b>Ozon</b>: показываю остатки, "
    "строю графики, ловлю момент выгодной цены и подсказываю, что завезти.\n\n"
    "<b>Что умею:</b>\n"
    "📦 следить за товарами по артикулу\n"
    "🔔 алерты «цена упала до N ₽»\n"
    "📈 график истории цены\n"
    "🔥 идеи для завоза из каталога\n"
    "💰 калькулятор маржи\n"
    "🤝 бонусы за приглашённых друзей\n\n"
    "Выберите действие:"
)


@router.message(CommandStart(deep_link=True))
async def cmd_start_deep(message: Message) -> None:
    args = message.get_args()
    user = await ensure_user(message.from_user.id, message.from_user.username)
    if args.startswith("ref_"):
        code = args[4:].upper()
        if code != user.ref_code:
            async with SessionLocal() as session:
                result = await session.execute(
                    select(User).where(User.ref_code == code, User.tg_id != user.tg_id)
                )
                referrer = result.scalar_one_or_none()
                if referrer and user.referred_by is None:
                    user.referred_by = referrer.id
                    await session.merge(user)
                    await session.commit()
                    await message.answer(
                        "🎁 Вы пришли по ссылке друга!\n\n"
                        "Когда вы оплатите подписку — ваш друг получит бонусные дни.",
                    )
    await message.answer(
        START_TEXT.format(status=tariff_status(user), until=tariff_until(user)),
        reply_markup=menu_kbd(),
    )


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    user = await ensure_user(message.from_user.id, message.from_user.username)
    await message.answer(
        START_TEXT.format(status=tariff_status(user), until=tariff_until(user)),
        reply_markup=menu_kbd(),
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message) -> None:
    await message.answer("Меню:", reply_markup=menu_kbd())


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "🆘 <b>Помощь</b>\n\n"
        "• <b>/start</b> — главное меню\n"
        "• <b>/now</b> — мои товары\n"
        "• <b>➕ Добавить</b> — пришлите артикул WB (число) или Ozon (текст)\n"
        "• <b>🔔 Целевая цена</b> — карточка товара → Цель\n"
        "• <b>💰 Маржа</b> — меню «Инструменты»\n"
        "• <b>🤝 Рефералка</b> — приглашайте друзей и получайте бонусные дни\n\n"
        "Есть вопросы? Напишите админу: @{admin}".format(
            admin=settings.admin_username or "admin"
        ),
        reply_markup=menu_kbd(),
    )


@router.callback_query(F.data == "menu")
async def cb_menu(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer("Меню:", reply_markup=menu_kbd())


@router.callback_query(F.data == "profile")
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
            f"Товары: <b>{used}/{limit}</b>\n"
            f"Ваша ссылка: t.me/{settings.bot_username}?start=ref_{user.ref_code}\n\n"
            f"Приглашайте друзей — получайте бонусные дни к подписке.\n"
            f"Для расширения лимитов — перейдите к тарифам.",
            reply_markup=plans_kbd(),
        )


@router.callback_query(F.data == "growth")
async def cb_growth(call: CallbackQuery) -> None:
    await call.answer("Ищу идеи…")
    cards = await wbc.get_catalog("топ продаж", limit=40)
    if not cards:
        await call.message.answer(
            "Не удалось получить каталог. Скорее всего WB гео-блокирует сеть "
            "(403/429). Запустите бота на российском VPS или настройте HTTP_PROXY.",
            reply_markup=back_kbd(),
        )
        return
    found = find_growth(cards, top_n=8)
    lines = ["🔥 <b>Идеи для завоза:</b>\n"]
    for c in found:
        price = nice_price(c.price)
        lines.append(f"{c.title[:45]}\n  <code>{c.sku}</code> · {price} · остатки {c.stock}\n  ↳ {c.reason}")
    await call.message.answer("\n\n".join(lines), reply_markup=back_kbd())
