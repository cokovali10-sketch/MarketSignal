import os
import sys
from pathlib import Path

# Изолируем тестовую БД от продакшн-данных ДО импорта core.db
TEST_DB = Path(__file__).parent.parent / "data" / "test_marketsignal.db"
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///data/test_marketsignal.db"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
