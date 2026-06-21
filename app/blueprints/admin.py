"""Админ-управление справочниками (ТЗ §5). Тарифы не удаляются — версионируются:
обновление = закрыть текущую запись (effective_to = сегодня) + открыть новую (effective_from = сегодня).
Полуоткрытые интервалы [from, to) — C3.
"""
from __future__ import annotations

import datetime as dt

from flask import Blueprint, jsonify, request
from sqlalchemy import select, and_

from app.extensions import db
from app.errors import NotFound, Conflict
from app.models import Warehouse, WarehouseCoefficient, Commission, BaseTariff
from app.schemas import (
    WarehouseCreate, WarehousePatch, CoefficientUpsert, CommissionUpsert, BaseTariffUpsert,
)

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _today() -> dt.date:
    return dt.date.today()


def _close_open(open_rows, new_row) -> None:
    """Закрыть открытые версии (effective_to=сегодня) и добавить новую (effective_from=сегодня)."""
    today = _today()
    for row in open_rows:
        if row.effective_to is None:
            row.effective_to = today
    new_row.effective_from = today
    new_row.effective_to = None
    db.session.add(new_row)
    db.session.commit()


def _body() -> dict:
    return request.get_json(silent=True) or {}


# --- Склады ---
@bp.get("/warehouses")
def list_warehouses():
    whs = db.session.execute(select(Warehouse).order_by(Warehouse.name)).scalars().all()
    return jsonify({"items": [
        {"id": w.id, "name": w.name, "active": w.active} for w in whs
    ]})


@bp.post("/warehouses")
def create_warehouse():
    data = WarehouseCreate(**_body())
    if db.session.get(Warehouse, data.id) is not None:
        raise Conflict(f"Склад «{data.id}» уже существует")
    wh = Warehouse(id=data.id, name=data.name, active=data.active)
    db.session.add(wh)
    db.session.commit()
    return jsonify({"id": wh.id, "name": wh.name, "active": wh.active}), 201


@bp.patch("/warehouses/<warehouse_id>")
def patch_warehouse(warehouse_id: str):
    wh = db.session.get(Warehouse, warehouse_id)
    if wh is None:
        raise NotFound("Склад не найден")
    data = WarehousePatch(**_body())
    if data.name is not None:
        wh.name = data.name
    if data.active is not None:
        wh.active = data.active  # неактивные не показываем, но расчёты не ломаем
    db.session.commit()
    return jsonify({"id": wh.id, "name": wh.name, "active": wh.active})


@bp.put("/warehouses/<warehouse_id>/coefficients")
def upsert_coefficient(warehouse_id: str):
    if db.session.get(Warehouse, warehouse_id) is None:
        raise NotFound("Склад не найден")
    data = CoefficientUpsert(**_body())
    open_rows = db.session.execute(
        select(WarehouseCoefficient).where(and_(
            WarehouseCoefficient.warehouse_id == warehouse_id,
            WarehouseCoefficient.delivery_type == data.delivery_type,
            WarehouseCoefficient.effective_to.is_(None),
        ))
    ).scalars().all()
    new = WarehouseCoefficient(
        warehouse_id=warehouse_id, delivery_type=data.delivery_type,
        logistics_coef=data.logistics, storage_coef=data.storage,
    )
    _close_open(open_rows, new)
    return jsonify({"ok": True, "effective_from": new.effective_from.isoformat()}), 201


# --- Комиссии ---
@bp.put("/commissions")
def upsert_commission():
    data = CommissionUpsert(**_body())
    open_rows = db.session.execute(
        select(Commission).where(and_(
            Commission.subject == data.subject,
            Commission.effective_to.is_(None),
        ))
    ).scalars().all()
    new = Commission(
        category=data.category, subject=data.subject,
        fbw=data.fbw, fbs=data.fbs, dbs=data.dbs, edbs=data.edbs, cc=data.cc,
    )
    _close_open(open_rows, new)
    return jsonify({"ok": True, "subject": data.subject,
                    "effective_from": new.effective_from.isoformat()}), 201


# --- Базовые тарифы ---
@bp.put("/base-tariffs")
def upsert_base_tariffs():
    data = BaseTariffUpsert(**_body())
    open_rows = db.session.execute(
        select(BaseTariff).where(BaseTariff.effective_to.is_(None))
    ).scalars().all()
    new = BaseTariff(
        delivery_base_1l=data.delivery_base_1l,
        delivery_per_extra_liter=data.delivery_per_extra_liter,
        reverse_base_1l=data.reverse_base_1l,
        reverse_per_extra_liter=data.reverse_per_extra_liter,
        storage_rub_per_liter_day=data.storage_rub_per_liter_day,
        per_liter_bands=data.per_liter_bands,
    )
    _close_open(open_rows, new)
    return jsonify({"ok": True, "effective_from": new.effective_from.isoformat()}), 201
