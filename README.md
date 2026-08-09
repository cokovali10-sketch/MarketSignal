# MarketSignal 📈

**Аналитика маркетплейсов для продавцов Wildberries / Ozon.**

Telegram-бот, который следит за ценами на товары, показывает остатки, отслеживает
конкурентов, подсказывает «растущие» товары и продаёт подписки. Готов к запуску
и монетизации.

---

## Возможности

- 📦 **Отслеживание товаров** — добавить артикул WB/Ozon одной командой
- 💰 **Мониторинг цен** — авто-проверка по расписанию, алерт «цена изменилась»
- 📊 **История цены** — точки цены по времени, отчёт в Telegram
- 🔥 **Растущие товары** — эвристика «что выгодно завезти» по каталогу WB
- 💎 **Подписки** — Free / Starter (299 ₽/мес) / Pro (799 ₽/мес) с лимитами
- 🐳 **Docker** — деплой одной командой

---

## Быстрый старт (локально)

```bash
cd D:\PortfolioProjects\MarketSignal
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"

copy config\.env.example config\.env   # заполните BOT_TOKEN
```

Запуск:

```bash
python main.py
```

Бот поднимется и начнёт опрос Telegram + фоновый планировщик проверки цен.

### Docker (VPS / продакшн)

```bash
copy config\.env.example config\.env   # заполните
docker compose up -d --build
```

---

## Настройка (config/.env)

| Переменная | Обязательно | Описание |
|---|---|---|
| `BOT_TOKEN` | ✅ | Токен от @BotFather |
| `ADMIN_IDS` | ✅ | Ваш Telegram ID (узнать: @userinfobot) — для ручной выдачи подписок |
| `DATABASE_URL` | — | По умолчанию `sqlite+aiosqlite:///data/marketsignal.db` |
| `TRACK_INTERVAL_MIN` | — | Интервал проверки цен (мин), по умолчанию 30 |
| `WB_REQUEST_INTERVAL` | — | Пауза между запросами к WB (сек), по умолчанию 1.0 |
| `OZON_CLIENT_ID` / `OZON_API_KEY` | для Ozon | Ключи API продавца Ozon |
| `WB_API_KEY` | опционально | API продавца WB (для будущих фич) |
| `SSL_VERIFY` | — | `false` если WB отдаёт ошибку сертификата |
| `HTTP_PROXY` | — | Прокси для обхода гео-блокировки: `http://login:pass@host:port` |
| `HTTP_RETRIES` | — | Попытки запроса при 429/5xx, по умолчанию 3 |

> Без ключей Ozon бот работает только с Wildberries — этого достаточно для MVP.

### ⚠️ Гео-блокировка Wildberries

WB часто закрывает доступ с **не-российских IP** и дата-центров: API отдаёт
`403/404/429/498`. Если парсер не получает данные, а код ошибок такой — запустите
бот на **российском VPS** или через российский прокси (`HTTP_PROXY`). Это нормальное
поведение WB, парсер написан по рабочему контракту API.

---

## Структура проекта

```
MarketSignal/
├── main.py                # точка входа: бот + планировщик
├── config/
│   ├── settings.py        # настройки (pydantic-settings)
│   └── .env.example       # шаблон переменных
├── bot/
│   ├── handlers/main.py   # команды, кнопки, обработка артикулов
│   └── middlewares/       # проверка подписки
├── parser/
│   ├── wb/client.py       # WB: card + catalog/search
│   ├── ozon/client.py     # Ozon: API продавца
│   └── scheduler.py       # APScheduler + рассылка изменений
├── core/
│   ├── models.py          # User, Item, PricePoint, Subscription
│   ├── db.py              # SQLAlchemy async
│   ├── tracker.py         # запись цен, история, алерты
│   ├── pricing.py         # тарифы, форматирование
│   └── growth.py          # эвристика растущих товаров
├── tests/                 # pytest
├── Dockerfile
└── docker-compose.yml
```

---

## Модель данных

```
User          tg_id, username, tariff (free|starter|pro), paid_until
Item          user_id, marketplace (wb|ozon), sku, title
PricePoint    item_id, ts, price, old_price, stock, seller_id
Subscription  user_id, tariff, paid_until, payment_id
```

---

## Тарифы и монетизация

| Тариф | Цена | Макс. товаров | Что даёт |
|---|---|---|---|
| Free | 0 ₽ | 1 | базовый отчёт |
| Starter | 299 ₽/мес | 10 | алерты на изменение цены |
| Pro | 799 ₽/мес | 50 | растущие товары, история 90 дней |

**Как принимать оплату (режим `PAYMENT_MODE=manual`):**
1. Пользователь жмёт «Тарифы» → видит цены и юзернейм админа
2. Переводит деньги и шлёт скрин
3. Вы (админ) активируете подписку командой:
   ```
   /grant <user_id> <tariff> <days>
   ```
4. Пользователь получает доступ до `paid_until`

---

## Тесты

```bash
python -m pytest tests -v
```

---

## Что дальше (дорожная карта)

- [ ] `PAYMENT_MODE=auto` — автоактивация через платёжный API (ЮKassa/Cryptomus)
- [ ] График цены картинкой (matplotlib)
- [ ] Мониторинг конкурентов по категории
- [ ] История 90 дней для Pro
- [ ] Web-дашборд (FastAPI)
- [ ] Мультиязычность

---

## Лицензия

MIT.
