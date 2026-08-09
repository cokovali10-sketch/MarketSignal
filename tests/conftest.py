import os
import sys

# Изолируем тестовую БД от продакшн-данных ДО импорта core.db
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///data/test_marketsignal.db"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
