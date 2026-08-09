from core.growth import find_growth, score_candidate
from core.pricing import TARIFFS, CardData, nice_price, tariff_limit


def _card(sku, price, old=None, stock=10, title="Товар"):
    return CardData(
        marketplace="wb", sku=sku, title=title, price=price, old_price=old, stock=stock
    )


def test_tariff_limits():
    assert tariff_limit("free") == 1
    assert tariff_limit("starter") == 10
    assert tariff_limit("pro") == 50
    assert TARIFFS["starter"]["price"] == 299
    assert TARIFFS["pro"]["price"] == 799


def test_nice_price():
    assert nice_price(None) == "—"
    assert nice_price(1500.0) == "1 500 ₽"
    assert nice_price(99.5) == "99.50 ₽"


def test_score_discount_boost():
    cheap_discounted = _card("1", 400, old=800, stock=3)
    expensive_stock = _card("2", 20000, old=20000, stock=500)
    assert score_candidate(cheap_discounted) > score_candidate(expensive_stock)


def test_growth_ranking():
    cards = [
        _card("1", 300, old=600, stock=2, title="Хит"),
        _card("2", 9000, old=9000, stock=400, title="Дорогой залежавшийся"),
    ]
    found = find_growth(cards, top_n=1)
    assert found
    assert found[0].sku == "1"


def test_card_serialization():
    c = _card("123", 1999.0)
    assert c.marketplace == "wb"
    assert c.sku == "123"
    assert c.price == 1999.0
