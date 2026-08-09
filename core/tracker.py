"""Логика отслеживания цен и формирования уведомлений."""

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.models import Item, PricePoint
from core.pricing import CardData, PriceChange

log = logging.getLogger(__name__)


async def record_price(session: AsyncSession, item: Item, data: CardData) -> PriceChange | None:
    """Записать точку цены, сравнить с предыдущей и вернуть изменение."""
    prev_result = await session.execute(
        select(PricePoint)
        .where(PricePoint.item_id == item.id)
        .order_by(PricePoint.ts.desc())
        .limit(1)
    )
    prev: PricePoint | None = prev_result.scalar_one_or_none()

    point = PricePoint(
        item_id=item.id,
        price=data.price,
        old_price=data.old_price,
        stock=data.stock,
        seller_id=data.seller_id,
    )
    session.add(point)
    await session.flush()

    if prev is None or prev.price is None or data.price is None:
        return None

    delta = data.price - prev.price
    if abs(delta) < 0.01:
        return None

    direction = "упала" if delta < 0 else "выросла"
    change = PriceChange(
        item_id=item.id,
        sku=item.sku,
        marketplace=item.marketplace,
        old_price=prev.price,
        new_price=data.price,
        delta=delta,
        message=(
            f"📉 Цена на товар {item.sku} ({item.title or item.sku}) {direction}: "
            f"{prev.price:,.0f} ₽ → {data.price:,.0f} ₽"
        ),
    )
    log.info(change.message)
    return change


async def get_history(session: AsyncSession, item_id: int, limit: int = 30) -> list[PricePoint]:
    result = await session.execute(
        select(PricePoint)
        .where(PricePoint.item_id == item_id)
        .order_by(PricePoint.ts.desc())
        .limit(limit)
    )
    return list(reversed(result.scalars().all()))


def render_history(points: list[PricePoint]) -> str:
    """Отформатировать историю цен текстом."""
    if not points:
        return "История пуста."
    lines = ["📈 *История цены:*"]
    for p in points:
        ts = p.ts.strftime("%d.%m %H:%M")
        price = f"{p.price:,.0f} ₽" if p.price is not None else "—"
        stock = f"остатки {p.stock}" if p.stock is not None else ""
        lines.append(f"{ts} · {price} {stock}".rstrip())
    return "\n".join(lines)


def is_expired(dt: datetime | None) -> bool:
    if dt is None:
        return True
    return dt <= datetime.now(timezone.utc)
