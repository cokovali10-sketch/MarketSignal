"""Общие объекты и хелперы бота: бот, диспетчер, БД, клавиатуры."""

import random
from datetime import datetime, timedelta, timezone

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from config.settings import settings
from core.db import SessionLocal
from core.models import Referral, Subscription, User
from core.pricing import TARIFFS
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

# Центральный реестр «ожиданий ввода»: user_id -> (action, payload)
# action: "alert" | "note" | "margin" | "search"
PENDING: dict[int, tuple[str, int | None]] = {}

_REF_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _btn(text: str, cb: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=cb)


def gen_ref_code() -> str:
    return "".join(random.choice(_REF_ALPHABET) for _ in range(6))


def menu_kbd() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("👤 Мой профиль", "profile")],
        [_btn("📦 Мои товары", "items"), _btn("➕ Добавить", "add_item")],
        [_btn("🔍 Поиск на WB", "search"), _btn("🔥 Идеи для завоза", "growth")],
        [_btn("💎 Тарифы / Подписка", "plans"), _btn("🤝 Пригласить друга", "ref")],
        [_btn("🛠 Инструменты", "tools")],
    ])


def back_kbd(cb: str = "menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[_btn("◀ Назад", cb)]])


def plans_kbd() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("🚀 Starter — 299 ₽/мес", "pay_starter")],
        [_btn("💎 Pro — 799 ₽/мес", "pay_pro")],
        [_btn("◀ Назад", "menu")],
    ])


def tools_kbd() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [_btn("💰 Калькулятор маржи", "calc_margin")],
        [_btn("📊 Дайджест цен", "digest")],
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
            user = User(tg_id=tg_id, username=username, tariff="free", ref_code=gen_ref_code())
            session.add(user)
            await session.commit()
            await session.refresh(user)
        else:
            changed = False
            if username and user.username != username:
                user.username = username
                changed = True
            if not user.ref_code:
                user.ref_code = gen_ref_code()
                changed = True
            if changed:
                await session.commit()
        return user


async def notify(tg_id: int, text: str) -> None:
    try:
        await bot.send_message(tg_id, text)
    except Exception as exc:  # noqa: BLE001
        print(f"[notify] failed to {tg_id}: {exc}")


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
    reward_msg = ""
    async with SessionLocal() as session:
        result = await session.execute(select(User).where(User.tg_id == tg_id))
        user = result.scalar_one_or_none()
        if user is None:
            user = User(tg_id=tg_id, tariff=tariff, ref_code=gen_ref_code())
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

        # Бонус рефереру за оплатившего друга (один раз)
        if user.referred_by:
            ref_result = await session.execute(
                select(Referral).where(
                    Referral.referred_id == user.id, Referral.rewarded.is_(False)
                )
            )
            ref = ref_result.scalar_one_or_none()
            if ref:
                ref_result2 = await session.execute(
                    select(User).where(User.id == ref.referrer_id)
                )
                referrer = ref_result2.scalar_one_or_none()
                if referrer:
                    bonus = settings.ref_bonus_days
                    if referrer.paid_until and referrer.paid_until > datetime.now(timezone.utc):
                        referrer.paid_until += timedelta(days=bonus)
                    else:
                        referrer.paid_until = datetime.now(timezone.utc) + timedelta(days=bonus)
                    ref.rewarded = True
                    reward_msg = (
                        f"\n\n🎁 Вы получили +{bonus} дн. к подписке за друга!"
                    )
                    try:
                        await bot.send_message(
                            referrer.tg_id,
                            f"🎁 Ваш друг оплатил подписку! Бонус +{bonus} дн. "
                            f"добавлен. Ваша подписка действует до "
                            f"{referrer.paid_until.strftime('%d.%m.%Y')}.",
                        )
                    except Exception as exc:  # noqa: BLE001
                        print(f"[ref notify] failed {referrer.tg_id}: {exc}")
        await session.commit()

    await notify(
        tg_id,
        f"🎉 <b>Подписка {TARIFFS[tariff]['name']} активирована!</b>\n\n"
        f"Действует до {paid_until.strftime('%d.%m.%Y')}."
        f"{reward_msg}\nПриятного использования MarketSignal! 📈",
    )
    return True
