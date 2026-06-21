"""Расширения Flask, инициализируемые в app factory."""
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import redis

db = SQLAlchemy()
migrate = Migrate()

# Redis-клиент инициализируется в create_app (нужен URL из конфига)
redis_client: "redis.Redis | None" = None


def init_redis(url: str) -> None:
    global redis_client
    redis_client = redis.Redis.from_url(url, decode_responses=True)
