"""Интеграционный тест: БД + tracker + тарифы."""


from sqlalchemy import select

from core.db import SessionLocal, engine, init_db
from core.models import Item, PricePoint, User
from core.pricing import CardData
from core.tracker import record_price


async def _setup():
    await init_db()
    async with SessionLocal() as session:
        u = User(tg_id=999, username="tester", tariff="starter")
        session.add(u)
        await session.flush()
        it = Item(user_id=u.id, marketplace="wb", sku="111222", title="Тест")
        session.add(it)
        await session.commit()
        return u.id, it.id


async def test_full_flow():
    user_id, item_id = await _setup()
    card = CardData(
        marketplace="wb", sku="111222", title="Тест", price=500.0, old_price=800.0, stock=4
    )

    async with SessionLocal() as session:
        result = await session.execute(select(Item).where(Item.id == item_id))
        item = result.scalar_one()
        change1 = await record_price(session, item, card)
        await session.commit()
        assert change1 is None  # первая запись — нет предыдущей

    card2 = CardData(marketplace="wb", sku="111222", price=450.0, stock=3)
    async with SessionLocal() as session:
        result = await session.execute(select(Item).where(Item.id == item_id))
        item = result.scalar_one()
        change2 = await record_price(session, item, card2)
        await session.commit()
        assert change2 is not None
        assert change2.delta == -50.0
        assert "упала" in change2.message

        result = await session.execute(
            select(PricePoint).where(PricePoint.item_id == item_id)
        )
        points = result.scalars().all()
        assert len(points) == 2
        assert points[1].price == 450.0

    await engine.dispose()
