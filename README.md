# Калькулятор прибыли WB — бэкенд

Серверный калькулятор юнит-экономики для продавцов Wildberries (KingStats/MPulse).
По параметрам товара считает затраты, налоги и прибыль **отдельно по каждому складу**.

Стек: **Flask + PostgreSQL + SQLAlchemy/psycopg + Redis + Pydantic v2**.

## Структура

```
app/
  config.py            конфиг + точки калибровки (ИЛ, ИРП, приёмка, >25кг, лимиты)
  extensions.py        db, migrate, redis
  models/              User, Calculation, Warehouse, WarehouseCoefficient, Commission
  schemas/             Pydantic-валидация (ТЗ Шаг 1)
  services/
    calculator.py      ЯДРО: 8 шагов + приёмка (C9) + безубыточность (C4)
    tariffs.py         подбор тарифов/комиссий по дате (версионность C3)
    runner.py          оркестратор: валидация → тарифы → движок, ошибки по колонкам
  blueprints/          calculations (CRUD), references (категории+склады)
  seed.py              импорт data/reference/*.json в БД
data/reference/        оцифрованные справочники + DATA-MODEL.md (модель + открытые вопросы)
tests/                 unit (движок на эталоне) + integration (весь стек на SQLite)
```

## Запуск через Docker (рекомендуется)

```bash
make up        # поднимет app + postgres + redis, применит миграции и засидит справочники
# v1 compose:  make up DC=docker-compose
curl localhost:8000/health
make logs      # логи приложения
make down      # остановить
```

`docker-entrypoint.sh` ждёт Postgres → `flask db upgrade` → сид (если БД пустая) → gunicorn.

## Запуск (локально, без Docker)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # отредактировать DATABASE_URL / REDIS_URL

export FLASK_APP=wsgi.py
flask db upgrade              # миграции уже в репозитории (migrations/)
flask seed                    # импорт справочников из data/reference/
flask run
```

## Тесты

```bash
pytest -q
```

`test_calculator.py` — ядро на эталонных цифрах со скриншота (Цена 400 → Прибыль 98.29 ₽).
`test_integration.py` — сквозной прогон через БД на SQLite.

## API

| Метод | Путь | Назначение |
|---|---|---|
| POST | `/calculations` | создать (имя «Расчёт N», поля пустые) |
| POST | `/calculations/<id>/duplicate` | дублировать («— копия», в конец) |
| PATCH | `/calculations/<id>` | автосохранение + пересчёт → `result.byWarehouse[]` |
| DELETE | `/calculations/<id>` | удалить + пересчёт позиций |
| PUT | `/calculations/reorder` | новый порядок вкладок |
| GET | `/references/categories` | дерево категория→предмет (кэш Redis 1 ч) |
| GET | `/references/warehouses` | активные склады + типы упаковки |
| GET | `/admin/warehouses` | все склады (вкл. неактивные) |
| POST/PATCH | `/admin/warehouses[/<id>]` | создать / изменить (имя, активность) |
| PUT | `/admin/warehouses/<id>/coefficients` | обновить коэф. (версионно: закрыть+открыть) |
| PUT | `/admin/commissions` | обновить комиссию предмета (версионно) |
| PUT | `/admin/base-tariffs` | обновить базовые тарифы (версионно) |

Пользователь в MVP — через заголовок `X-User-Id` (без авторизации).
Админ-обновления справочников не удаляют старое — закрывают `effective_to` и открывают новую версию (ТЗ §5).

Ошибки: `422` валидация (с полем `fields`), `404` не найдено, `409` лимит/конфликт.

## Решения и открытые вопросы

Полный перечень всех принятых решений, допущений и находок (B1–C10) — в
**`data/reference/DECISIONS.md`** (что добавили/выбрали сами и почему).
Модель данных и формулы — в **`data/reference/DATA-MODEL.md`**.

Остаточные 🟡, требующие данных от команды:

- **C9** — тариф «приёмки» коробов (`ACCEPTANCE_RUB`, дефолт 0) + точная формула
  обратной логистики. Остаточный зазор с эталоном ~0.8 ₽.
- **C6** — паритет имён складов xlsx ↔ реальный UI (адресация уже по `id`).
- **C8** — ИЛ/ИРП захардкожены (1 / 0) до источника из API WB.

Все вынесены в конфиг — правятся без изменения кода.

## Важные находки (в процессе анализа ТЗ и эталона)

- **C10**: налог УСН «Доходы» считается от **выручки (цены)**, а не от «К перечислению»,
  как ошибочно сказано в ТЗ. Эталон: 6%×400 = 24 ₽ (а не 6%×220). Исправлено.
- **C9**: WB удерживает отдельную **«Приёмку»** (видно в `screencast.mp4`), которой
  нет в формулах ТЗ — добавлена как компонент `wbCosts.acceptance`.
