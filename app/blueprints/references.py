"""Справочники: категории (дерево, кэш 1 час) и склады (только активные)."""
from __future__ import annotations

import json

from flask import Blueprint, jsonify, current_app
from sqlalchemy import select

from app.extensions import db, redis_client
from app.models import Commission, Warehouse, WarehouseCoefficient

bp = Blueprint("references", __name__, url_prefix="/references")

_CATEGORIES_CACHE_KEY = "ref:categories:v1"


def _cache_get(key: str):
    """Чтение из Redis с graceful degradation — недоступность кэша не ломает эндпоинт."""
    if redis_client is None:
        return None
    try:
        return redis_client.get(key)
    except Exception:
        return None


def _cache_set(key: str, value: str, ttl: int) -> None:
    if redis_client is None:
        return
    try:
        redis_client.set(key, value, ex=ttl)
    except Exception:
        pass


@bp.get("/categories")
def categories():
    """Дерево категория→предмет плоским списком с путём. Кэш в Redis на 1 час (ТЗ)."""
    cached = _cache_get(_CATEGORIES_CACHE_KEY)
    if cached:
        return current_app.response_class(cached, mimetype="application/json")

    rows = db.session.execute(
        select(Commission.category, Commission.subject)
        .where(Commission.effective_to.is_(None))
        .order_by(Commission.category, Commission.subject)
    ).all()

    items = [
        {"category": cat, "subject": subj, "path": f"{cat} / {subj}"}
        for cat, subj in rows
    ]
    payload = json.dumps({"items": items}, ensure_ascii=False)
    _cache_set(_CATEGORIES_CACHE_KEY, payload, current_app.config["CATEGORIES_CACHE_TTL"])
    return current_app.response_class(payload, mimetype="application/json")


@bp.get("/warehouses")
def warehouses():
    """Активные склады с поддерживаемыми типами упаковки (неактивные не показываем)."""
    whs = db.session.execute(
        select(Warehouse).where(Warehouse.active.is_(True)).order_by(Warehouse.name)
    ).scalars().all()

    result = []
    for w in whs:
        types = sorted({
            c.delivery_type for c in w.coefficients if c.effective_to is None
        })
        result.append({"id": w.id, "name": w.name, "supportedTypes": types})
    return jsonify({"items": result})
