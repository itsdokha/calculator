"""Оркестратор расчёта: валидация (Шаг 1) → подбор тарифов (Шаг 2) → движок (Шаги 3–8).

Результат формируется отдельно для каждого склада (колонки таблицы). Если тариф для
склада не найден — ошибка только в его колонке, остальные считаются (ТЗ «Ограничения»).
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from flask import current_app
from pydantic import ValidationError

from app.models import Calculation
from app.schemas import CalculationParams
from app.services import tariffs
from app.services.calculator import (
    CalcConfig, CalcInput, WarehouseTariff, compute_for_warehouse,
)


def _config() -> CalcConfig:
    c = current_app.config
    return CalcConfig(
        localization_index=c["LOCALIZATION_INDEX"],
        buyer_location_index=c["BUYER_LOCATION_INDEX"],
        acquiring_pct=c["ACQUIRING_PCT"],
        heavy_goods_coef=c["HEAVY_GOODS_LOGISTICS_COEF"],
        acceptance_rub=c["ACCEPTANCE_RUB"],
        heavy_threshold_kg=c["HEAVY_WEIGHT_THRESHOLD_KG"],
    )


def run_calculation(calc: Calculation, on_date: Optional[dt.date] = None) -> dict:
    on_date = on_date or dt.date.today()  # C3: дата выбора тарифа = «сегодня»
    cfg = _config()
    base = tariffs.get_base_tariffs(on_date)

    # Комиссия одна на расчёт (зависит от предмета + модели продаж)
    commission_error: Optional[str] = None
    commission_pct = 0.0
    try:
        if not calc.category_subject or not calc.sales_model:
            raise tariffs.TariffNotFound("Не выбраны категория или модель продаж")
        commission_pct = tariffs.get_commission_pct(calc.category_subject, calc.sales_model, on_date)
    except tariffs.TariffNotFound as e:
        commission_error = str(e)

    # Валидация входных данных (Шаг 1)
    try:
        params = CalculationParams(
            price=calc.price, cost_price=calc.cost_price,
            length_cm=calc.length_cm, width_cm=calc.width_cm, height_cm=calc.height_cm,
            weight_kg=calc.weight_kg, commission_pct=commission_pct,
            sales_model=calc.sales_model, delivery_type=calc.delivery_type,
            warehouse_ids=calc.warehouse_ids or [],
            turnover_days=calc.turnover_days, buyout_percent=calc.buyout_percent,
            promo_percent=calc.promo_percent or 0,
            other_expenses_per_unit=calc.other_expenses_per_unit or 0,
            tax_system=calc.tax_system or "usn_income", tax_rate=calc.tax_rate or 0,
        )
    except ValidationError as e:
        return {"error": "validation", "fields": [
            {"field": ".".join(str(x) for x in err["loc"]), "message": err["msg"]}
            for err in e.errors()
        ]}

    by_warehouse = []
    for wid in params.warehouse_ids:
        name = tariffs.warehouse_name(wid)
        if commission_error:
            by_warehouse.append({"warehouseId": wid, "warehouseName": name, "error": commission_error})
            continue
        try:
            log_coef, stor_coef = tariffs.get_warehouse_coef(wid, params.delivery_type or "box", on_date)
        except tariffs.TariffNotFound as e:
            by_warehouse.append({"warehouseId": wid, "warehouseName": name, "error": str(e)})
            continue

        inp = CalcInput(
            price=params.price, cost_price=params.cost_price,
            length_cm=params.length_cm, width_cm=params.width_cm, height_cm=params.height_cm,
            weight_kg=params.weight_kg, commission_pct=params.commission_pct,
            turnover_days=params.turnover_days, buyout_percent=params.buyout_percent,
            promo_percent=params.promo_percent,
            other_expenses_per_unit=params.other_expenses_per_unit,
            tax_system=params.tax_system, tax_rate=params.tax_rate,
        )
        wh = WarehouseTariff(warehouse_name=name, logistics_coef=log_coef, storage_coef=stor_coef)
        result = compute_for_warehouse(inp, wh, cfg, base)
        result["warehouseId"] = wid
        by_warehouse.append(result)

    return {"result": {"byWarehouse": by_warehouse}}
