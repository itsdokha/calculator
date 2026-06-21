"""CRUD расчётов + дублирование + изменение порядка вкладок. Автосохранение + пересчёт."""
from __future__ import annotations

from flask import Blueprint, jsonify, request, current_app
from sqlalchemy import select, func

from app.extensions import db
from app.errors import NotFound, Conflict
from app.models import User, Calculation
from app.schemas import CalculationPatch, ReorderRequest
from app.services.runner import run_calculation

bp = Blueprint("calculations", __name__, url_prefix="/calculations")

# Поля, копируемые при дублировании (все параметры, кроме id/name/position/user)
_PARAM_FIELDS = [
    "category_subject", "price", "cost_price", "length_cm", "width_cm", "height_cm",
    "weight_kg", "sales_model", "delivery_type", "warehouse_ids", "turnover_days",
    "buyout_percent", "promo_percent", "other_expenses_per_unit", "tax_system", "tax_rate",
]


def _current_user() -> User:
    """MVP без авторизации: пользователь из заголовка X-User-Id (по умолчанию 1)."""
    uid = int(request.headers.get("X-User-Id", 1))
    user = db.session.get(User, uid)
    if user is None:
        user = User(id=uid)
        db.session.add(user)
        db.session.commit()
    return user


def _serialize(calc: Calculation) -> dict:
    return {
        "id": calc.id, "name": calc.name, "position": calc.position,
        **{f: getattr(calc, f) for f in _PARAM_FIELDS},
    }


def _next_position(user: User) -> int:
    mx = db.session.execute(
        select(func.max(Calculation.position)).where(Calculation.user_id == user.id)
    ).scalar()
    return (mx + 1) if mx is not None else 0


def _count(user: User) -> int:
    return db.session.execute(
        select(func.count(Calculation.id)).where(Calculation.user_id == user.id)
    ).scalar() or 0


@bp.get("")
def list_calculations():
    user = _current_user()
    calcs = db.session.execute(
        select(Calculation).where(Calculation.user_id == user.id).order_by(Calculation.position)
    ).scalars().all()
    return jsonify({"items": [_serialize(c) for c in calcs]})


@bp.post("")
def create_calculation():
    user = _current_user()
    limit = current_app.config["MAX_CALCULATIONS_PER_USER"]
    if _count(user) >= limit:
        raise Conflict(f"Не более {limit} расчётов", {"error": "limit"})

    pos = _next_position(user)
    calc = Calculation(user_id=user.id, name=f"Расчёт {pos + 1}", position=pos, warehouse_ids=[])
    db.session.add(calc)
    db.session.commit()
    return jsonify(_serialize(calc)), 201


@bp.post("/<int:calc_id>/duplicate")
def duplicate_calculation(calc_id: int):
    user = _current_user()
    limit = current_app.config["MAX_CALCULATIONS_PER_USER"]
    if _count(user) >= limit:
        raise Conflict(f"Не более {limit} расчётов", {"error": "limit"})

    src = db.session.get(Calculation, calc_id)
    if src is None or src.user_id != user.id:
        raise NotFound("Расчёт не найден")

    pos = _next_position(user)
    copy = Calculation(
        user_id=user.id, name=f"{src.name} — копия", position=pos,
        **{f: getattr(src, f) for f in _PARAM_FIELDS},
    )
    db.session.add(copy)
    db.session.commit()
    return jsonify(_serialize(copy)), 201


@bp.patch("/<int:calc_id>")
def patch_calculation(calc_id: int):
    user = _current_user()
    calc = db.session.get(Calculation, calc_id)
    if calc is None or calc.user_id != user.id:
        raise NotFound("Расчёт не найден")

    patch = CalculationPatch(**(request.get_json(silent=True) or {}))
    for field, value in patch.model_dump(exclude_unset=True).items():
        setattr(calc, field, value)
    db.session.commit()  # автосохранение

    # Пересчёт при каждом изменении (история не хранится — перезапись)
    computed = run_calculation(calc)
    return jsonify({"calculation": _serialize(calc), **computed})


@bp.delete("/<int:calc_id>")
def delete_calculation(calc_id: int):
    user = _current_user()
    calc = db.session.get(Calculation, calc_id)
    if calc is None or calc.user_id != user.id:
        raise NotFound("Расчёт не найден")

    db.session.delete(calc)
    db.session.flush()
    # Пересчёт позиций оставшихся по порядку
    rest = db.session.execute(
        select(Calculation).where(Calculation.user_id == user.id).order_by(Calculation.position)
    ).scalars().all()
    for i, c in enumerate(rest):
        c.position = i
    db.session.commit()
    return jsonify({"ok": True})


@bp.put("/reorder")
def reorder():
    user = _current_user()
    req = ReorderRequest(**(request.get_json(silent=True) or {}))
    calcs = {
        c.id: c for c in db.session.execute(
            select(Calculation).where(Calculation.user_id == user.id)
        ).scalars().all()
    }
    for i, cid in enumerate(req.ordered_ids):
        if cid in calcs:
            calcs[cid].position = i
    db.session.commit()
    return jsonify({"ok": True})
