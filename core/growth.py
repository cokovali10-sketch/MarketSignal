"""Эвристики «растущих товаров» по данным каталога."""

import logging
from dataclasses import dataclass

from core.pricing import CardData
# --- константы вынесены FORGE refactor ---
CONST_5 = 5
CONST_20 = 20
CONST_500 = 500
CONST_10000 = 10000


log = logging.getLogger(__name__)


@dataclass
class GrowthCandidate:
    sku: str
    title: str
    price: float | None
    stock: int
    score: float
    reason: str


def score_candidate(data: CardData) -> float:
    """Оценка привлекательности товара 0..100.

    Критерии: низкая конкуренция (малые остатки у продавца), высокий спрос
    (наличие скидки от прежней цены), доступная цена.
    """
    score = 50.0
    if data.stock is not None:
        if data.stock <= CONST_5:
            score += CONST_20  # мало остатков → товар расходится
        elif data.stock > 100:
            score -= 15  # много остатков → возможно залежалый
    if data.old_price and data.price:
        discount = (data.old_price - data.price) / data.old_price
        score += min(CONST_20, discount * 100)  # скидка → спрос
    if data.price is not None:
        if data.price < CONST_500:
            score += CONST_5  # импульсный ценовой сегмент
        elif data.price > CONST_10000:
            score -= 10  # дорогой товар продаётся дольше
    return max(0.0, min(100.0, score))


def find_growth(data_list: list[CardData], top_n: int = 10) -> list[GrowthCandidate]:
    """Отобрать лучшие кандидаты для завоза."""
    candidates: list[GrowthCandidate] = []
    for data in data_list:
        score = score_candidate(data)
        reason = _describe(data, score)
        candidates.append(
            GrowthCandidate(
                sku=data.sku,
                title=data.title or data.sku,
                price=data.price,
                stock=data.stock or 0,
                score=score,
                reason=reason,
            )
        )
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates[:top_n]


def _describe(data: CardData, score: float) -> str:
    reasons = []
    if data.old_price and data.price and data.old_price > data.price:
        discount = int((data.old_price - data.price) / data.old_price * 100)
        reasons.append(f"скидка {discount}%")
    if data.stock is not None and data.stock <= CONST_5:
        reasons.append("мало остатков (спрос)")
    elif data.stock is not None and data.stock > 100:
        reasons.append("много остатков")
    if data.price is not None and data.price < CONST_500:
        reasons.append("импульсный ценник")
    if data.price is not None and data.price > CONST_10000:
        reasons.append("дорогой сегмент")
    return "; ".join(reasons) if reasons else f"оценка {score:.0f}/100"
