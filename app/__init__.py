"""Flask app factory."""
from __future__ import annotations

import click
from flask import Flask, jsonify, render_template

from app.config import Config
from app.extensions import db, migrate, init_redis


def create_app(config_object: type = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    migrate.init_app(app, db)
    init_redis(app.config["REDIS_URL"])

    # модели должны быть импортированы до миграций
    from app import models  # noqa: F401

    from app.errors import register_error_handlers
    register_error_handlers(app)

    from app.blueprints.calculations import bp as calculations_bp
    from app.blueprints.references import bp as references_bp
    from app.blueprints.admin import bp as admin_bp
    app.register_blueprint(calculations_bp)
    app.register_blueprint(references_bp)
    app.register_blueprint(admin_bp)

    @app.get("/")
    def index():
        """Демо-страница калькулятора (дёргает тот же REST API)."""
        return render_template("index.html")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.cli.command("seed")
    def seed_command():
        """Импорт справочников из data/reference/*.json в БД."""
        from app.seed import seed_all
        result = seed_all()
        click.echo(f"Импортировано: {result}")

    return app
