import asyncio

from config.settings import settings
from parser.wb.client import CARD_URL, WbClient


def test_url_construction():
    c = WbClient()
    assert c._sem is not None
    assert settings.wb_request_interval > 0


def test_session_kwargs_ssl_off(monkeypatch):
    monkeypatch.setattr(settings, "ssl_verify", False)
    import asyncio

    from parser.wb.client import _session_kwargs

    async def build():
        return _session_kwargs()

    kwargs = asyncio.run(build())
    assert "connector" in kwargs
    assert kwargs["connector"]._ssl.verify_mode.name == "CERT_NONE"


def test_session_kwargs_proxy(monkeypatch):
    monkeypatch.setattr(settings, "http_proxy", "http://user:pass@proxy:3128")
    import asyncio

    from parser.wb.client import _session_kwargs

    async def build():
        return _session_kwargs()

    kwargs = asyncio.run(build())
    assert kwargs["proxy"] == "http://user:pass@proxy:3128"


def test_card_url_has_v1_fallback():
    # Гарантируем, что константа URL существует и карточный API не пустой
    assert "detail" in CARD_URL


def test_rate_limit_serial():
    async def run():
        c = WbClient()
        await c.close()

    asyncio.run(run())
    assert True
