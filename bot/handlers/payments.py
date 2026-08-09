"""Оплата подписок через Telegram Stars (⭐)."""

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, LabeledPrice, Message, PreCheckoutQuery

from bot.services import activate_subscription, bot, menu_kbd, plans_kbd
from config.settings import settings
from core.pricing import TARIFFS

log = logging.getLogger(__name__)
router = Router()


def stars_for_tariff(tariff: str) -> int:
    """Количество ⭐ за тариф (из .env)."""
    if tariff == "starter":
        return settings.stars_starter
    if tariff == "pro":
        return settings.stars_pro
    return 0


@router.callback_query(F.data == "plans")
async def cb_plans(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer(
        "💎 <b>Тарифы MarketSignal:</b>\n\n"
        "🆓 <b>Free</b> — 0 ₽\n  • 1 товар\n  • базовый отчёт\n\n"
        f"🚀 <b>Starter</b> — 299 ₽/мес · {stars_for_tariff('starter')} ⭐\n"
        "  • 10 товаров\n  • алерты на изменение цены и целевую цену\n  • график истории\n\n"
        f"💎 <b>Pro</b> — 799 ₽/мес · {stars_for_tariff('pro')} ⭐\n"
        "  • 50 товаров\n  • идеи для завоза\n  • калькулятор маржи\n  • экспорт CSV\n\n"
        "Оплата в одну кнопку через <b>Telegram Stars</b> ⭐ — "
        "без карт и сторонних сервисов, подписка включится мгновенно.\n\n"
        "Выберите тариф:",
        reply_markup=plans_kbd(),
    )


@router.callback_query(F.data.startswith("pay_"))
async def cb_pay(call: CallbackQuery) -> None:
    tariff = call.data.split("_", 1)[1]
    if tariff not in TARIFFS:
        await call.answer("Неверный тариф.", show_alert=True)
        return
    await call.answer()
    stars = stars_for_tariff(tariff)
    await bot.send_invoice(
        chat_id=call.from_user.id,
        title=f"MarketSignal · {TARIFFS[tariff]['name']}",
        description=f"Подписка {TARIFFS[tariff]['name']} на 30 дней.",
        payload=f"sub:{tariff}",
        provider_token="",
        currency="XTR",
        prices=[LabeledPrice(label=TARIFFS[tariff]["name"], amount=stars)],
        protect_content=False,
    )


@router.pre_checkout_query()
async def on_pre_checkout(query: PreCheckoutQuery) -> None:
    await query.answer(ok=True)


@router.message(F.successful_payment)
async def on_successful_payment(message: Message) -> None:
    payment = message.successful_payment
    payload = payment.invoice_payload or ""
    tariff = payload.split(":", 1)[1] if ":" in payload else "starter"
    if tariff not in TARIFFS:
        tariff = "starter"
    payment_id = f"stars:{payment.telegram_payment_charge_id}"
    ok = await activate_subscription(
        message.from_user.id, tariff, days=30, payment_id=payment_id
    )
    if ok:
        await message.answer(
            f"✅ Оплата получена!\n\n"
            f"Тариф <b>{TARIFFS[tariff]['name']}</b> активирован на 30 дней.",
            reply_markup=menu_kbd(),
        )


@router.callback_query(F.data == "ref")
async def cb_ref(call: CallbackQuery) -> None:
    await call.answer()
    from bot.services import ensure_user

    user = await ensure_user(call.from_user.id, call.from_user.username)
    link = f"https://t.me/{settings.bot_username}?start=ref_{user.ref_code}"
    await call.message.answer(
        "🤝 <b>Пригласите друга — получите бонусные дни!</b>\n\n"
        f"Ваша ссылка:\n<code>{link}</code>\n\n"
        "За каждого друга, который оплатит подписку по вашей ссылке, "
        f"вы получите <b>+{settings.ref_bonus_days} дня</b> к подписке.\n\n"
        "Друзья, пришедшие по вашей ссылке, получают скидку на первый месяц.",
    )


# ─────────────────────────── АДМИН: ПОДТВЕРЖДЕНИЕ ───────────────────────────

@router.callback_query(F.data.startswith("grant:"))
async def cb_grant(call: CallbackQuery) -> None:
    if call.from_user.id not in settings_admins():
        await call.answer("⛔ Нет прав.", show_alert=True)
        return
    _, tg_id, tariff = call.data.split(":")
    ok = await activate_subscription(
        int(tg_id),
        tariff,
        days=30,
        payment_id=f"admin:{call.from_user.id}:{call.message.message_id}",
    )
    await call.answer("✅ Подписка активирована" if ok else "❌ Ошибка", show_alert=not ok)


@router.callback_query(F.data.startswith("deny:"))
async def cb_deny(call: CallbackQuery) -> None:
    if call.from_user.id not in settings_admins():
        await call.answer("⛔ Нет прав.", show_alert=True)
        return
    _, tg_id = call.data.split(":")
    await call.answer("❌ Отклонено")
    from bot.services import notify

    await notify(int(tg_id), "❌ К сожалению, оплата не подтверждена. Свяжитесь с администратором.")


@router.message(F.text.startswith("/grant"))
async def cmd_grant(message: Message) -> None:
    if message.from_user.id not in settings_admins():
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


def settings_admins() -> list[int]:
    from config.settings import settings

    return settings.admins
