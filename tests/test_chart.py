from datetime import datetime, timezone

from core.chart import render_chart
from core.models import PricePoint


def _p(ts, price):
    return PricePoint(ts=datetime.now(timezone.utc), price=price, old_price=None, stock=5)


def test_render_chart_returns_png():
    points = [_p(0, 100.0), _p(1, 150.0), _p(2, 120.0)]
    data = render_chart(points)
    assert data.startswith(b"\x89PNG")
    assert len(data) > 500


def test_render_chart_empty_raises():
    import pytest

    with pytest.raises(ValueError):
        render_chart([])
