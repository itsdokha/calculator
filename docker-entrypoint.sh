#!/usr/bin/env bash
set -e

# Ждём Postgres
echo "Ожидание Postgres..."
until pg_isready -h "${PGHOST:-db}" -p "${PGPORT:-5432}" -U "${PGUSER:-calc}" >/dev/null 2>&1; do
  sleep 1
done
echo "Postgres готов."

# Применяем миграции (создаст схему, если миграции есть)
flask db upgrade || echo "Миграции не применены (нет папки migrations?) — пропускаю."

# Сид справочников, если БД пустая
python - <<'PY'
from app import create_app
from app.extensions import db
from app.models import Commission
app = create_app()
with app.app_context():
    try:
        empty = db.session.query(Commission).count() == 0
    except Exception:
        empty = False
    if empty:
        from app.seed import seed_all
        print("Импорт справочников:", seed_all())
    else:
        print("Справочники уже загружены — пропускаю сид.")
PY

exec "$@"
