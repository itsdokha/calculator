"""Единый HTTP-слой ошибок: согласованные JSON-ответы и коды статусов."""
from __future__ import annotations

from flask import Flask, jsonify
from pydantic import ValidationError


class ApiError(Exception):
    """Прикладная ошибка с HTTP-статусом и машиночитаемым кодом."""
    def __init__(self, status: int, code: str, message: str, extra: dict | None = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.extra = extra or {}

    def to_response(self):
        body = {"error": self.code, "message": self.message, **self.extra}
        return jsonify(body), self.status


class NotFound(ApiError):
    def __init__(self, message: str = "Не найдено"):
        super().__init__(404, "not_found", message)


class Conflict(ApiError):
    def __init__(self, message: str, extra: dict | None = None):
        super().__init__(409, "conflict", message, extra)


def _validation_fields(exc: ValidationError) -> list[dict]:
    return [
        {"field": ".".join(str(x) for x in err["loc"]), "message": err["msg"]}
        for err in exc.errors()
    ]


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api_error(e: ApiError):
        return e.to_response()

    @app.errorhandler(ValidationError)
    def _pydantic_error(e: ValidationError):
        return jsonify({"error": "validation", "fields": _validation_fields(e)}), 422
