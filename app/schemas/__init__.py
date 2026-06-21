"""Pydantic v2 схемы — валидация входных данных (ТЗ Шаг 1) и формы запросов."""
from __future__ import annotations

from typing import Optional, Literal
from pydantic import BaseModel, Field, field_validator, model_validator

SalesModel = Literal["FBS", "FBW", "DBS", "EDBS", "C&C"]
DeliveryType = Literal["box", "monopallet"]
TaxSystem = Literal["usn_income", "usn_income_minus_expenses", "other", "none"]


class CalculationPatch(BaseModel):
    """Частичное обновление параметров расчёта (автосохранение). Все поля опциональны."""
    name: Optional[str] = None
    category_subject: Optional[str] = None
    price: Optional[float] = None
    cost_price: Optional[float] = None
    length_cm: Optional[float] = None
    width_cm: Optional[float] = None
    height_cm: Optional[float] = None
    weight_kg: Optional[float] = None
    sales_model: Optional[SalesModel] = None
    delivery_type: Optional[DeliveryType] = None
    warehouse_ids: Optional[list[str]] = None
    turnover_days: Optional[float] = None
    buyout_percent: Optional[float] = None
    promo_percent: Optional[float] = None
    other_expenses_per_unit: Optional[float] = None
    tax_system: Optional[TaxSystem] = None
    tax_rate: Optional[float] = None


class CalculationParams(BaseModel):
    """Полная валидация перед расчётом (ТЗ Шаг 1). Невалидные поля → ошибка с указанием полей."""
    price: float = Field(..., gt=0, description="Цена товара > 0")
    cost_price: float = Field(..., ge=0, description="Себестоимость >= 0")
    length_cm: float = Field(..., gt=0)
    width_cm: float = Field(..., gt=0)
    height_cm: float = Field(..., gt=0)
    weight_kg: Optional[float] = Field(None, ge=0)
    commission_pct: float = Field(..., ge=0)
    sales_model: SalesModel
    delivery_type: Optional[DeliveryType] = None
    warehouse_ids: list[str] = Field(..., min_length=1, max_length=5)
    turnover_days: float = Field(..., ge=0)
    buyout_percent: float = Field(..., ge=1, le=100, description="Доля выкупа 1..100")
    promo_percent: float = Field(0, ge=0, le=100)
    other_expenses_per_unit: float = Field(0, ge=0)
    tax_system: TaxSystem = "usn_income"
    tax_rate: float = 0

    @field_validator("delivery_type")
    @classmethod
    def _box_only_for_fbw(cls, v, info):
        return v  # связь FBW↔delivery_type проверяется на уровне модели/блюпринта

    @model_validator(mode="after")
    def _tax_rate_required_for_other(self):
        if self.tax_system == "other" and (self.tax_rate is None or self.tax_rate <= 0):
            raise ValueError("Налоговая ставка обязательна для системы «Другая»")
        if self.sales_model == "FBW" and self.delivery_type is None:
            raise ValueError("Тип поставки (Короб/Монопаллета) обязателен для FBW")
        return self


class ReorderRequest(BaseModel):
    """Новый порядок вкладок — список ID расчётов в нужном порядке."""
    ordered_ids: list[int] = Field(..., min_length=1)


# --- Админ-схемы справочников (ТЗ §5) ---
class WarehouseCreate(BaseModel):
    id: str = Field(..., min_length=1, max_length=120)
    name: str = Field(..., min_length=1, max_length=255)
    active: bool = True


class WarehousePatch(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    active: Optional[bool] = None


class CoefficientUpsert(BaseModel):
    delivery_type: DeliveryType
    logistics: float = Field(..., gt=0)
    storage: float = Field(..., gt=0)


class CommissionUpsert(BaseModel):
    category: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1)
    fbw: float = Field(..., ge=0)
    fbs: float = Field(..., ge=0)
    dbs: float = Field(..., ge=0)
    edbs: float = Field(..., ge=0)
    cc: float = Field(..., ge=0)


class BaseTariffUpsert(BaseModel):
    delivery_base_1l: float = Field(..., gt=0)
    delivery_per_extra_liter: float = Field(..., ge=0)
    reverse_base_1l: float = Field(..., gt=0)
    reverse_per_extra_liter: float = Field(..., ge=0)
    storage_rub_per_liter_day: float = Field(..., gt=0)
    per_liter_bands: list[list[float]] = Field(..., min_length=1)
