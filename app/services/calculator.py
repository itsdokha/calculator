"""Ядро калькулятора прибыли WB — алгоритм из ТЗ (8 шагов) + приёмка (C9) + безубыточность (C4).

Намеренно чистый Python без зависимостей от БД/Flask, чтобы покрывать unit-тестами
на эталонных цифрах. Тарифы/коэффициенты/комиссия передаются уже разрешёнными
(их подбирает services/tariffs.py по дате и складу).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Тарифы доставки до покупателя для товара <= 1 л (из comments.md): (от_л, до_л, ₽/литр)
PER_LITER_BANDS = [
    (0.001, 0.200, 23.0),
    (0.201, 0.400, 26.0),
    (0.401, 0.600, 29.0),
    (0.601, 0.800, 30.0),
    (0.801, 1.000, 32.0),
]

# Базовые тарифы доставки/обратной логистики для товара > 1 л
DELIVERY_BASE_1L = 46.0          # ₽ за 1-й литр
DELIVERY_PER_EXTRA_LITER = 14.0  # ₽ за каждый доп. литр
STORAGE_RUB_PER_LITER_DAY = 0.08  # ₽/л/день, базовая ставка хранения (короб и монопаллета, C5)


@dataclass
class BaseTariffs:
    """Базовые тарифы WB (версионируются в БД, ТЗ §5). Дефолт = значения из comments.md."""
    per_liter_bands: list = field(default_factory=lambda: list(PER_LITER_BANDS))
    delivery_base_1l: float = DELIVERY_BASE_1L
    delivery_per_extra_liter: float = DELIVERY_PER_EXTRA_LITER
    reverse_base_1l: float = DELIVERY_BASE_1L
    reverse_per_extra_liter: float = DELIVERY_PER_EXTRA_LITER
    storage_rub_per_liter_day: float = STORAGE_RUB_PER_LITER_DAY


DEFAULT_BASE_TARIFFS = BaseTariffs()

TAX_USN_INCOME = "usn_income"
TAX_USN_INCOME_MINUS_EXPENSES = "usn_income_minus_expenses"
TAX_OTHER = "other"
TAX_NONE = "none"


@dataclass
class CalcConfig:
    """Конфиг-константы и точки калибровки (зеркалит app/config.py)."""
    localization_index: float = 1.0      # ИЛ (C8)
    buyer_location_index: float = 0.0    # ИРП (C8)
    acquiring_pct: float = 1.5           # эквайринг
    heavy_goods_coef: float = 1.0        # >25 кг (C2)
    acceptance_rub: float = 0.0          # приёмка за единицу (C9)
    heavy_threshold_kg: float = 25.0


@dataclass
class WarehouseTariff:
    """Разрешённые коэффициенты конкретного склада под выбранный тип упаковки."""
    warehouse_name: str
    logistics_coef: float
    storage_coef: float


@dataclass
class CalcInput:
    price: float
    cost_price: float
    length_cm: float
    width_cm: float
    height_cm: float
    commission_pct: float            # из справочника по модели продаж
    turnover_days: float
    buyout_percent: float            # 1..100
    weight_kg: Optional[float] = None
    promo_percent: float = 0.0
    other_expenses_per_unit: float = 0.0
    tax_system: str = TAX_USN_INCOME
    tax_rate: float = 0.0            # обязателен при tax_system == other


# ---------------------------------------------------------------------------
# Шаг 3 — объём и вспомогательные тарифы
# ---------------------------------------------------------------------------
def volume_liters(inp: CalcInput) -> float:
    return inp.length_cm * inp.width_cm * inp.height_cm / 1000.0


def per_liter_rate(volume: float, base: BaseTariffs = DEFAULT_BASE_TARIFFS) -> float:
    """Ставка ₽/литр по диапазону объёма (для товара <= 1 л)."""
    for lo, hi, rate in base.per_liter_bands:
        if volume <= hi:
            return rate
    return base.per_liter_bands[-1][2]


def _delivery_base(volume: float, base: BaseTariffs) -> float:
    if volume <= 1.0:
        return volume * per_liter_rate(volume, base)
    return base.delivery_base_1l + base.delivery_per_extra_liter * (volume - 1.0)


def _reverse_base(volume: float, base: BaseTariffs) -> float:
    # Обратная логистика: 46 ₽ за 1 л + 14 ₽ за доп. литр
    return base.reverse_base_1l + base.reverse_per_extra_liter * max(0.0, volume - 1.0)


def is_heavy(inp: CalcInput, cfg: CalcConfig) -> bool:
    return inp.weight_kg is not None and inp.weight_kg > cfg.heavy_threshold_kg


# ---------------------------------------------------------------------------
# Шаг 4 — удержания WB (для одной цены, фиксированные входные параметры)
# ---------------------------------------------------------------------------
def wb_costs(price: float, inp: CalcInput, wh: WarehouseTariff, cfg: CalcConfig, volume: float,
            base: BaseTariffs = DEFAULT_BASE_TARIFFS) -> dict:
    heavy = cfg.heavy_goods_coef if is_heavy(inp, cfg) else 1.0
    buyout = inp.buyout_percent / 100.0

    commission = price * inp.commission_pct / 100.0
    acquiring = price * cfg.acquiring_pct / 100.0

    delivery = (
        _delivery_base(volume, base) * wh.logistics_coef * cfg.localization_index * heavy
        + price * cfg.buyer_location_index
    )
    # C9: обратная логистика — БЕЗ коэффициента склада (в comments.md, в отличие от
    # доставки, множитель «× Коэффициент склада» не указан).
    reverse = _reverse_base(volume, base)
    # Логистика на 1 продажу: чем ниже выкуп — тем дороже на единицу продажи
    logistics = (delivery + reverse * (1.0 - buyout)) / buyout if buyout > 0 else 0.0

    storage = base.storage_rub_per_liter_day * wh.storage_coef * volume * inp.turnover_days
    acceptance = cfg.acceptance_rub  # C9

    total = commission + acquiring + logistics + storage + acceptance
    return {
        "commission": commission,
        "acquiring": acquiring,
        "logistics": logistics,
        "storage": storage,
        "acceptance": acceptance,
        "total": total,
    }


# ---------------------------------------------------------------------------
# Шаг 6 — налог
# C10 (находка из эталона): налоговая база УСН «Доходы» = ВЫРУЧКА (цена), а НЕ
# «К перечислению», как ошибочно указано в ТЗ. Эталон: 6% × 400 = 24 ₽ (а не
# 6% × 220 = 13.2 ₽). «Доходы−расходы» = доход − все расходы (экономически верно).
# ---------------------------------------------------------------------------
def compute_tax(system: str, rate: float, price: float, expenses_ex_tax: float) -> float:
    """expenses_ex_tax — все расходы кроме налога (WB + себестоимость + продвижение + прочие)."""
    t = rate / 100.0
    if system == TAX_USN_INCOME or system == TAX_OTHER:
        return price * t                       # база = выручка (цена)
    if system == TAX_USN_INCOME_MINUS_EXPENSES:
        base = price - expenses_ex_tax         # доходы − расходы
        return base * t if base > 0 else 0.0
    if system == TAX_NONE:
        return 0.0
    raise ValueError(f"Неизвестная система налогообложения: {system}")


# ---------------------------------------------------------------------------
# Прибыль при заданной цене (используется и для итога, и для безубыточности)
# ---------------------------------------------------------------------------
def profit_at(price: float, inp: CalcInput, wh: WarehouseTariff, cfg: CalcConfig, volume: float,
              base: BaseTariffs = DEFAULT_BASE_TARIFFS) -> float:
    wb = wb_costs(price, inp, wh, cfg, volume, base)
    promo = price * inp.promo_percent / 100.0
    expenses_ex_tax = wb["total"] + inp.cost_price + promo + inp.other_expenses_per_unit
    tax = compute_tax(inp.tax_system, inp.tax_rate, price, expenses_ex_tax)
    return price - (expenses_ex_tax + tax)


# ---------------------------------------------------------------------------
# Шаг 8 — цена безубыточности (C4, бисекция — робастно к излому УСН «Д−Р»)
# ---------------------------------------------------------------------------
def breakeven_price(inp: CalcInput, wh: WarehouseTariff, cfg: CalcConfig, volume: float,
                    base: BaseTariffs = DEFAULT_BASE_TARIFFS) -> Optional[float]:
    lo, hi = 0.0, 1e7
    # если даже при максимальной цене прибыль < 0 — безубыточности нет
    if profit_at(hi, inp, wh, cfg, volume, base) < 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if profit_at(mid, inp, wh, cfg, volume, base) >= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2.0


# ---------------------------------------------------------------------------
# Полный расчёт по одному складу (Шаги 4–8)
# ---------------------------------------------------------------------------
def compute_for_warehouse(inp: CalcInput, wh: WarehouseTariff, cfg: CalcConfig,
                          base: BaseTariffs = DEFAULT_BASE_TARIFFS) -> dict:
    price = inp.price
    volume = volume_liters(inp)

    wb = wb_costs(price, inp, wh, cfg, volume, base)
    transfer = price - wb["total"]
    promo = price * inp.promo_percent / 100.0
    expenses_ex_tax = wb["total"] + inp.cost_price + promo + inp.other_expenses_per_unit
    tax = compute_tax(inp.tax_system, inp.tax_rate, price, expenses_ex_tax)
    total_expenses = expenses_ex_tax + tax
    profit = price - total_expenses
    marginality = (profit / price * 100.0) if price else 0.0
    roi = (profit / inp.cost_price * 100.0) if inp.cost_price > 0 else None  # null при себест.=0
    breakeven = breakeven_price(inp, wh, cfg, volume, base)

    def pct(v: float) -> Optional[float]:
        return round(v / price * 100.0, 2) if price else None

    return {
        "warehouseName": wh.warehouse_name,
        "volumeLiters": round(volume, 4),
        "priceRub": {"rub": round(price, 2), "pct": 100.0},
        "wbCosts": {
            "commission": {"rub": round(wb["commission"], 2), "pct": pct(wb["commission"])},
            "acquiring": {"rub": round(wb["acquiring"], 2), "pct": pct(wb["acquiring"])},
            "logistics": {"rub": round(wb["logistics"], 2), "pct": pct(wb["logistics"])},
            "storage": {"rub": round(wb["storage"], 2), "pct": pct(wb["storage"])},
            "acceptance": {"rub": round(wb["acceptance"], 2), "pct": pct(wb["acceptance"])},
            "total": {"rub": round(wb["total"], 2), "pct": pct(wb["total"])},
        },
        "transferToSeller": {"rub": round(transfer, 2), "pct": pct(transfer)},
        "taxes": {"rub": round(tax, 2), "pct": pct(tax)},
        "costPrice": {"rub": round(inp.cost_price, 2), "pct": pct(inp.cost_price)},
        "promotion": {"rub": round(promo, 2), "pct": pct(promo)},
        "otherExpenses": {"rub": round(inp.other_expenses_per_unit, 2), "pct": pct(inp.other_expenses_per_unit)},
        "totalExpenses": {"rub": round(total_expenses, 2), "pct": pct(total_expenses)},
        "profit": {"rub": round(profit, 2), "pct": pct(profit)},
        "marginality": round(marginality, 2),
        "roi": round(roi, 2) if roi is not None else None,
        "breakevenPrice": round(breakeven, 2) if breakeven is not None else None,
    }
