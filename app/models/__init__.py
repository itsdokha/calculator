"""SQLAlchemy-модели. Справочные таблицы версионируются датами (C3)."""
from __future__ import annotations

import datetime as dt
from sqlalchemy import (
    String, Integer, Float, Boolean, Date, ForeignKey, JSON, Numeric, Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.extensions import db

# Типы упаковки и модели продаж
DELIVERY_TYPES = ("box", "monopallet")
SALES_MODELS = ("FBS", "FBW", "DBS", "EDBS", "C&C")


# ---------------------------------------------------------------------------
# Пользователь и расчёты
# ---------------------------------------------------------------------------
class User(db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str | None] = mapped_column(String(255), unique=True)
    calculations: Mapped[list["Calculation"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="Calculation.position"
    )


class Calculation(db.Model):
    __tablename__ = "calculations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    position: Mapped[int] = mapped_column(Integer)  # порядок вкладки

    # Параметры товара
    category_subject: Mapped[str | None] = mapped_column(String(255))  # предмет (лист дерева)
    price: Mapped[float | None] = mapped_column(Float)
    cost_price: Mapped[float | None] = mapped_column(Float)
    length_cm: Mapped[float | None] = mapped_column(Float)
    width_cm: Mapped[float | None] = mapped_column(Float)
    height_cm: Mapped[float | None] = mapped_column(Float)
    weight_kg: Mapped[float | None] = mapped_column(Float)

    # Модель продаж / поставка / склады
    sales_model: Mapped[str | None] = mapped_column(String(8))
    delivery_type: Mapped[str | None] = mapped_column(String(16))  # только для FBW
    warehouse_ids: Mapped[list | None] = mapped_column(JSON, default=list)  # 1..5

    # Статистика
    turnover_days: Mapped[float | None] = mapped_column(Float)
    buyout_percent: Mapped[float | None] = mapped_column(Float)

    # Расходы
    promo_percent: Mapped[float | None] = mapped_column(Float, default=0)
    other_expenses_per_unit: Mapped[float | None] = mapped_column(Float, default=0)

    # Налогообложение
    tax_system: Mapped[str | None] = mapped_column(String(40))
    tax_rate: Mapped[float | None] = mapped_column(Float)

    user: Mapped["User"] = relationship(back_populates="calculations")


# ---------------------------------------------------------------------------
# Справочники
# ---------------------------------------------------------------------------
class Warehouse(db.Model):
    __tablename__ = "warehouses"
    id: Mapped[str] = mapped_column(String(120), primary_key=True)  # стабильный slug-id (C6)
    name: Mapped[str] = mapped_column(String(255))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    coefficients: Mapped[list["WarehouseCoefficient"]] = relationship(
        back_populates="warehouse", cascade="all, delete-orphan"
    )


class WarehouseCoefficient(db.Model):
    """Коэффициенты логистики/хранения склада под тип упаковки. Версионируется (C3)."""
    __tablename__ = "warehouse_coefficients"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    warehouse_id: Mapped[str] = mapped_column(ForeignKey("warehouses.id", ondelete="CASCADE"), index=True)
    delivery_type: Mapped[str] = mapped_column(String(16))  # box | monopallet
    logistics_coef: Mapped[float] = mapped_column(Float)
    storage_coef: Mapped[float] = mapped_column(Float)
    effective_from: Mapped[dt.date] = mapped_column(Date, index=True)
    effective_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)  # NULL = действует

    warehouse: Mapped["Warehouse"] = relationship(back_populates="coefficients")


class Commission(db.Model):
    """Комиссия по предмету и модели продаж. Дерево: category → subject. Версионируется."""
    __tablename__ = "commissions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category: Mapped[str] = mapped_column(String(255), index=True)
    subject: Mapped[str] = mapped_column(String(255), index=True)
    fbw: Mapped[float] = mapped_column(Float)
    fbs: Mapped[float] = mapped_column(Float)
    dbs: Mapped[float] = mapped_column(Float)
    edbs: Mapped[float] = mapped_column(Float)
    cc: Mapped[float] = mapped_column(Float)  # C&C (самовывоз)
    effective_from: Mapped[dt.date] = mapped_column(Date, index=True)
    effective_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    def commission_for(self, sales_model: str) -> float:
        return {
            "FBW": self.fbw, "FBS": self.fbs, "DBS": self.dbs,
            "EDBS": self.edbs, "C&C": self.cc,
        }[sales_model]


class BaseTariff(db.Model):
    """Базовые тарифы WB (₽): доставка, обратная логистика, хранение. Версионируется (ТЗ §5)."""
    __tablename__ = "base_tariffs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    delivery_base_1l: Mapped[float] = mapped_column(Float)
    delivery_per_extra_liter: Mapped[float] = mapped_column(Float)
    reverse_base_1l: Mapped[float] = mapped_column(Float)
    reverse_per_extra_liter: Mapped[float] = mapped_column(Float)
    storage_rub_per_liter_day: Mapped[float] = mapped_column(Float)
    # диапазоны ₽/литр для товара <= 1 л: [[from_l, to_l, rub_per_liter], ...]
    per_liter_bands: Mapped[list] = mapped_column(JSON)
    effective_from: Mapped[dt.date] = mapped_column(Date, index=True)
    effective_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
