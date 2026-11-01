<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0f172a,50:38bdf8,100:a78bfa&height=160&section=header&text=MarketSignal&fontSize=48&fontColor=ffffff&fontAlignY=38&animation=fadeIn" alt="header" />

</div>

<div align="center">

# MarketSignal

### Marketplace Analytics for Wildberries / Ozon Sellers

[![CI](https://img.shields.io/badge/CI-GitHub%20Actions-2088FF?logo=githubactions&logoColor=white)](#)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-20+-green.svg)](#testing)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](#docker)

A Telegram bot that tracks product prices, shows stock levels, builds charts, catches the best moment to buy, and suggests restocking ideas — monetized through **Telegram Stars** with zero external payment providers.

</div>

---

## Features

| Feature | Description |
|---------|-------------|
| **Product Tracking** | Add by WB/Ozon article, direct link, or WB catalog search |
| **Product Card** | Price, stock levels, discount %, link, notes, action buttons |
| **Price Alerts** | "Notify when price drops below 1,500 ₽" — push notifications |
| **Price Chart** | matplotlib PNG chart rendered directly in chat |
| **Price History** | Timestamped data points + **CSV export** |
| **Product Notes** | Attach custom notes to any tracked item |
| **Restock Ideas** | Heuristic suggestions from WB catalog analysis |
| **Margin Calculator** | Commissions, logistics, net profit, % |
| **Price Digest** | Weekly summary across all tracked products |
| **Referral Program** | +3 days subscription per paying referral |
| **User Profile** | Subscription tier, limits, referral link |
| **Auto-Check** | Background scheduler every 30 min + manual "Refresh" |
| **Admin Panel** | `/stats`, `/grant` for manual subscription management |

---

## Quick Start

### Local Development

```bash
git clone https://github.com/yourname/MarketSignal.git
cd MarketSignal

python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate    # Linux/macOS

pip install -e ".[dev]"
cp config/.env.example config/.env   # fill in BOT_TOKEN
python main.py
```

### Docker (Production)

```bash
cp config/.env.example config/.env
docker compose up -d --build
```

---

## Configuration

| Variable | Required | Description |
|----------|----------|-------------|
| `BOT_TOKEN` | **Yes** | Telegram bot token from @BotFather |
| `BOT_USERNAME` | **Yes** | Bot username (for referral links) |
| `ADMIN_IDS` | **Yes** | Your Telegram ID (find via @userinfobot) |
| `DATABASE_URL` | No | Default: `sqlite+aiosqlite:///data/marketsignal.db` |
| `TRACK_INTERVAL_MIN` | No | Check interval in minutes (default: 30) |
| `STARS_STARTER` / `STARS_PRO` | No | Tier price in Telegram Stars (default: 85/222) |
| `REF_BONUS_DAYS` | No | Referral bonus days (default: 3) |
| `SSL_VERIFY` | No | `false` if WB returns certificate errors |
| `HTTP_PROXY` | No | Proxy for WB geo-block bypass |
| `HTTP_RETRIES` | No | Retries on 429/5xx (default: 3) |

> **⚠️ Geo-blocking:** Wildberries blocks non-Russian IPs with `403/404/429/498`. For production, deploy on a Russian VPS or configure `HTTP_PROXY`.

---

## Payment (Telegram Stars)

Payments happen entirely inside Telegram — no cards, no webhooks, no external payment providers:

1. User taps "💎 Tariffs" → selects Starter/Pro
2. Telegram opens star payment — one tap to pay
3. Bot activates subscription automatically (`successful_payment`)
4. Stars accumulate in your bot balance → withdraw via Fragment (TON) or use for Telegram ads

| Tier | Price | Max Products | Features |
|------|-------|-------------|----------|
| **Free** | 0 ₽ | 1 | Basic report, chart |
| **Starter** | 299 ₽/mo | 10 | Price alerts, target price, notes |
| **Pro** | 799 ₽/mo | 50 | Restock ideas, margin calculator, CSV |

**Withdrawal:** Stars convert to TON via Fragment (~3.6 ₽ per ⭐). No KYC required.

---

## Project Structure

```
MarketSignal/
├── main.py                  # Entry point: bot + scheduler
├── config/
│   ├── settings.py          # Pydantic-settings configuration
│   └── .env.example
├── bot/
│   ├── services.py          # Bot, dispatcher, keyboards, subscription activation
│   └── handlers/
│       ├── text.py          # Unified text input dispatcher
│       ├── core.py          # Start, menu, profile, ideas
│       ├── items.py         # Products, cards, charts, alerts, CSV
│       ├── payments.py      # Stars payment, referrals, admin confirmation
│       └── tools.py         # Margin calculator, digest, search, /stats
├── parser/
│   ├── wb/client.py         # Wildberries: card + search
│   ├── ozon/client.py       # Ozon: seller API
│   └── scheduler.py         # Background scheduler + alert checker
├── core/
│   ├── models.py            # User, Item, PricePoint, Subscription, PriceAlert, Referral
│   ├── chart.py             # Price chart (matplotlib)
│   ├── margin.py            # Margin calculator
│   ├── tracker.py           # Price recording, history
│   ├── pricing.py           # Tiers, formatting
│   └── growth.py            # Growing product heuristic
├── assets/avatar.png        # Bot avatar
├── marketing/promo.md       # Ready-made promotional materials
└── tests/                   # pytest (20 tests)
```

---

## Testing

```bash
python -m pytest tests -v
python -m ruff check .
```

---

## License

MIT
