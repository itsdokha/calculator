"""Импорт справочников из data/reference/*.json в БД (C3: первый импорт с якорной датой)."""
from __future__ import annotations

import datetime as dt
import json
import os

from flask import current_app

from app.extensions import db
from app.models import Warehouse, WarehouseCoefficient, Commission, BaseTariff

REFERENCE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "reference")


def _anchor() -> dt.date:
    return dt.date.fromisoformat(current_app.config["TARIFF_ANCHOR_DATE"])


def seed_warehouses() -> int:
    path = os.path.join(REFERENCE_DIR, "warehouses.json")
    data = json.load(open(path, encoding="utf-8"))
    anchor = _anchor()
    n = 0
    for w in data:
        wh = db.session.get(Warehouse, w["id"]) or Warehouse(id=w["id"])
        wh.name = w["name"]
        wh.active = w.get("active", True)
        db.session.add(wh)
        for dtype, co in w.get("coefficients", {}).items():
            if co.get("logistics") is None or co.get("storage") is None:
                continue
            db.session.add(WarehouseCoefficient(
                warehouse_id=w["id"], delivery_type=dtype,
                logistics_coef=co["logistics"], storage_coef=co["storage"],
                effective_from=anchor, effective_to=None,
            ))
            n += 1
    db.session.commit()
    return n


def seed_commissions() -> int:
    path = os.path.join(REFERENCE_DIR, "commissions.json")
    data = json.load(open(path, encoding="utf-8"))
    anchor = _anchor()
    n = 0
    for c in data:
        com = c["commission"]
        db.session.add(Commission(
            category=c["category"], subject=c["subject"],
            fbw=com["FBW"], fbs=com["FBS"], dbs=com["DBS"],
            edbs=com["EDBS"], cc=com["C&C"],
            effective_from=anchor, effective_to=None,
        ))
        n += 1
    db.session.commit()
    return n


def seed_base_tariffs() -> int:
    """Базовые тарифы из base-tariffs.json (доставка/обратная/хранение)."""
    path = os.path.join(REFERENCE_DIR, "base-tariffs.json")
    data = json.load(open(path, encoding="utf-8"))
    anchor = _anchor()

    d2c = data["deliveryToCustomer"]
    bands = [[b["fromL"], b["toL"], b["rubPerLiter"]]
             for b in d2c["lessThanOrEqual1L"]["perLiterBands"]]
    db.session.add(BaseTariff(
        delivery_base_1l=d2c["moreThan1L"]["base"],
        delivery_per_extra_liter=d2c["moreThan1L"]["perExtraLiter"],
        reverse_base_1l=data["reverseLogistics"]["base"],
        reverse_per_extra_liter=data["reverseLogistics"]["perExtraLiter"],
        storage_rub_per_liter_day=data["storage"]["box"]["rubPerLiterPerDay"],
        per_liter_bands=bands,
        effective_from=anchor, effective_to=None,
    ))
    db.session.commit()
    return 1


def seed_all() -> dict:
    return {
        "warehouseCoefficients": seed_warehouses(),
        "commissions": seed_commissions(),
        "baseTariffs": seed_base_tariffs(),
    }
