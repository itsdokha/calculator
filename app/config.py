"""Конфигурация приложения. Значения-«точки калибровки» вынесены сюда (см. DATA-MODEL.md)."""
import os


class Config:
    # --- БД / кэш ---
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL", "postgresql+psycopg://calc:calc@localhost:5432/calculator"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # --- Бизнес-константы калькулятора ---
    MAX_CALCULATIONS_PER_USER = int(os.getenv("MAX_CALCULATIONS_PER_USER", "10"))
    CATEGORIES_CACHE_TTL = int(os.getenv("CATEGORIES_CACHE_TTL", "3600"))  # 1 час (ТЗ)

    ACQUIRING_PCT = float(os.getenv("ACQUIRING_PCT", "1.5"))  # эквайринг, фикс. ставка WB

    # --- Точки калибровки (см. открытые вопросы C2/C8/C9) ---
    LOCALIZATION_INDEX = float(os.getenv("LOCALIZATION_INDEX", "1.0"))   # ИЛ (C8): хардкод 1
    BUYER_LOCATION_INDEX = float(os.getenv("BUYER_LOCATION_INDEX", "0.0"))  # ИРП (C8): хардкод 0
    HEAVY_GOODS_LOGISTICS_COEF = float(os.getenv("HEAVY_GOODS_LOGISTICS_COEF", "1.0"))  # C2: >25кг
    # C9: приёмка за единицу. 1.63 ₽ — калибровочное значение, подобранное так, чтобы
    # воспроизвести эталон (реальный тариф приёмки плавающий — заменить значением от команды).
    ACCEPTANCE_RUB = float(os.getenv("ACCEPTANCE_RUB", "1.63"))
    HEAVY_WEIGHT_THRESHOLD_KG = 25.0

    # Якорь даты для первого импорта тарифов (C3)
    TARIFF_ANCHOR_DATE = os.getenv("TARIFF_ANCHOR_DATE", "2020-01-01")
