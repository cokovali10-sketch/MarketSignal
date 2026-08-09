from pydantic import BaseModel


class CardData(BaseModel):
    """Нормализованные данные о товаре с маркетплейса."""

    marketplace: str
    sku: str
    title: str | None = None
    price: float | None = None
    old_price: float | None = None
    stock: int | None = None
    seller_id: str | None = None


class PriceChange(BaseModel):
    """Результат сравнения текущей и предыдущей точки цены."""

    item_id: int
    sku: str
    marketplace: str
    old_price: float | None = None
    new_price: float | None = None
    delta: float = 0.0
    message: str = ""


TARIFFS = {
    "free": {"price": 0, "max_items": 1, "name": "Free"},
    "starter": {"price": 299, "max_items": 10, "name": "Starter"},
    "pro": {"price": 799, "max_items": 50, "name": "Pro"},
}


def tariff_limit(tariff: str) -> int:
    return TARIFFS.get(tariff, TARIFFS["free"])["max_items"]


def tariff_price(tariff: str) -> int:
    return TARIFFS.get(tariff, TARIFFS["free"])["price"]


def nice_price(price: float | None) -> str:
    if price is None:
        return "—"
    if price >= 1000:
        return f"{price:,.0f} ₽".replace(",", " ")
    return f"{price:.2f} ₽"
