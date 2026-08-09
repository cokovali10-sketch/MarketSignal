"""Регистрация всех роутеров бота."""

from bot.handlers import core, items, payments, text, tools
from bot.services import dp

# text — первым, т.к. это единственный F.text-хендлер (диспетчер ввода)
for r in (text.router, core.router, items.router, payments.router, tools.router):
    dp.include_router(r)
