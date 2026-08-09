"""Middleware проверки подписки для защищённых команд."""

import logging
from collections.abc import Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy import select

from core.db import SessionLocal
from core.models import User

log = logging.getLogger(__name__)


class SubscriptionMiddleware(BaseMiddleware):
    """Проверяет, что пользователь подписан, для команд за пределами лимита Free."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict], Awaitable[object]],
        event: TelegramObject,
        data: dict,
    ) -> object:
        user = None
        if isinstance(event, (Message, CallbackQuery)):
            tg_id = event.from_user.id if event.from_user else None
            if tg_id:
                async with SessionLocal() as session:
                    result = await session.execute(select(User).where(User.tg_id == tg_id))
                    user = result.scalar_one_or_none()
        data["db_user"] = user
        return await handler(event, data)
