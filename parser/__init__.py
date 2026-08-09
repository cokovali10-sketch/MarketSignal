"""Пакет парсеров маркетплейсов."""

from parser.ozon.client import OzonClient
from parser.wb.client import WbClient

__all__ = ["WbClient", "OzonClient"]
