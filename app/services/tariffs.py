"""Подбор актуальных тарифов/комиссий по дате (ТЗ Шаг 2, версионность — C3).

Выбор: запись действует, если effective_from <= :date AND (effective_to IS NULL OR effective_to > :date).
При нескольких — берём с максимальной effective_from (самую свежую).
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from sqlalchemy import select, and_, or_

from app.extensions import db
from app.models import Commission, WarehouseCoefficient, Warehouse, BaseTariff
from app.services.calculator import BaseTariffs, DEFAULT_BASE_TARIFFS


class TariffNotFound(Exception):
    """Тариф/комиссия не найдены для комбинации — ошибка на уровне колонки склада (ТЗ Ограничения)."""


def _active_on(column_to, on_date: dt.date):
    return or_(column_to.is_(None), column_to > on_date)


def get_commission_pct(subject: str, sales_model: str, on_date: dt.date) -> float:
    stmt = (
        select(Commission)
        .where(
            and_(
                Commission.subject == subject,
                Commission.effective_from <= on_date,
                _active_on(Commission.effective_to, on_date),
            )
        )
        .order_by(Commission.effective_from.desc())
        .limit(1)
    )
    row = db.session.execute(stmt).scalar_one_or_none()
    if row is None:
        raise TariffNotFound(f"Комиссия не найдена для предмета «{subject}»")
    return row.commission_for(sales_model)


def get_warehouse_coef(warehouse_id: str, delivery_type: str, on_date: dt.date) -> tuple[float, float]:
    stmt = (
        select(WarehouseCoefficient)
        .where(
            and_(
                WarehouseCoefficient.warehouse_id == warehouse_id,
                WarehouseCoefficient.delivery_type == delivery_type,
                WarehouseCoefficient.effective_from <= on_date,
                _active_on(WarehouseCoefficient.effective_to, on_date),
            )
        )
        .order_by(WarehouseCoefficient.effective_from.desc())
        .limit(1)
    )
    row = db.session.execute(stmt).scalar_one_or_none()
    if row is None:
        raise TariffNotFound(
            f"Тариф не найден: склад «{warehouse_id}» + упаковка «{delivery_type}»"
        )
    return row.logistics_coef, row.storage_coef


def warehouse_name(warehouse_id: str) -> str:
    wh = db.session.get(Warehouse, warehouse_id)
    return wh.name if wh else warehouse_id


def get_base_tariffs(on_date: dt.date) -> BaseTariffs:
    """Актуальные базовые тарифы на дату. Если в БД ничего — дефолт из comments.md."""
    stmt = (
        select(BaseTariff)
        .where(
            and_(
                BaseTariff.effective_from <= on_date,
                _active_on(BaseTariff.effective_to, on_date),
            )
        )
        .order_by(BaseTariff.effective_from.desc())
        .limit(1)
    )
    row = db.session.execute(stmt).scalar_one_or_none()
    if row is None:
        return DEFAULT_BASE_TARIFFS
    return BaseTariffs(
        per_liter_bands=[tuple(b) for b in row.per_liter_bands],
        delivery_base_1l=row.delivery_base_1l,
        delivery_per_extra_liter=row.delivery_per_extra_liter,
        reverse_base_1l=row.reverse_base_1l,
        reverse_per_extra_liter=row.reverse_per_extra_liter,
        storage_rub_per_liter_day=row.storage_rub_per_liter_day,
    )
