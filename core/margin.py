"""Калькулятор маржи для Wildberries/Ozon.

Считает выручку, комиссию, логистику, чистую прибыль и маржинальность.
Комиссия WB зависит от категории (задаётся вручную), логистика — от склада/габаритов.
"""

from dataclasses import dataclass


@dataclass
class MarginResult:
    selling_price: float
    cost_price: float
    commission_pct: float
    logistics: float
    extra_costs: float
    commission_amount: float
    revenue: float
    costs_total: float
    profit: float
    margin_pct: float

    @property
    def parts(self) -> list[str]:
        return [
            "💰 <b>Расчёт маржи</b>",
            f"Цена продажи: <b>{self.selling_price:,.0f} ₽</b>",
            f"Себестоимость: {self.cost_price:,.0f} ₽",
            f"Комиссия ({self.commission_pct:.0f}%): −{self.commission_amount:,.0f} ₽",
            f"Логистика: −{self.logistics:,.0f} ₽",
            f"Прочие расходы: −{self.extra_costs:,.0f} ₽",
            f"Выручка на руках: {self.revenue:,.0f} ₽",
            "────────────",
            f"Прибыль: <b>{self.profit:,.0f} ₽</b>",
            f"Маржинальность: <b>{self.margin_pct:.1f}%</b>",
        ]


def calculate_margin(
    selling_price: float,
    cost_price: float,
    commission_pct: float,
    logistics: float,
    extra_costs: float = 0.0,
) -> MarginResult:
    commission_amount = selling_price * commission_pct / 100
    revenue = selling_price - commission_amount - logistics - extra_costs
    profit = revenue - cost_price
    margin_pct = profit / selling_price * 100 if selling_price else 0.0
    return MarginResult(
        selling_price=selling_price,
        cost_price=cost_price,
        commission_pct=commission_pct,
        logistics=logistics,
        extra_costs=extra_costs,
        commission_amount=commission_amount,
        revenue=revenue,
        costs_total=commission_amount + logistics + extra_costs + cost_price,
        profit=profit,
        margin_pct=margin_pct,
    )


def parse_margin_input(text: str) -> tuple[list[float], str | None]:
    """Разобрать ввод пользователя: цена, себестоимость, комиссия %, логистика, [прочее].

    Возвращает (числа, None) или ([], сообщение_об_ошибке).
    """
    parts = text.replace(",", ".").split()
    try:
        values = [float(p) for p in parts]
    except ValueError:
        return [], "Не понял числа. Пример: <code>1500 800 15 50</code>"
    if len(values) < 4:
        return [], "Нужно минимум 4 числа: цена, себестоимость, комиссия %, логистика ₽. Пример: <code>1500 800 15 50</code>"
    if len(values) > 5:
        return [], "Слишком много чисел. Пример: <code>1500 800 15 50 10</code>"
    if any(v < 0 for v in values):
        return [], "Числа не могут быть отрицательными."
    return values, None
