from __future__ import annotations

from flask import Flask, jsonify, request

from .region_tree_service import RegionTreeService
from .service import AddressExtractionService, PROJECT_NAME


service = AddressExtractionService()
region_tree_service = RegionTreeService()


def _success(payload: dict, status_code: int = 200) -> tuple:
    """Unified response: always wraps payload under 'data' key (issue #11)."""
    return jsonify({"code": status_code, "data": payload}), status_code


def _error(message: str, status_code: int = 400) -> tuple:
    return jsonify({"code": status_code, "error": message}), status_code


def _clean_query_value(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip().strip("\"'`").strip()
    return cleaned or None


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health() -> tuple:
        return _success({"status": "ok", "project": PROJECT_NAME})

    @app.post("/api/v1/parse")
    def parse() -> tuple:
        payload = request.get_json(silent=True) or {}
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return _error("`text` must be a non-empty string")
        return _success(service.parse_text(text))

    @app.get("/api/v1/regions/tree")
    def region_tree() -> tuple:
        province = _clean_query_value(request.args.get("province", type=str))
        city = _clean_query_value(request.args.get("city", type=str))
        county = _clean_query_value(request.args.get("county", type=str))
        try:
            result = region_tree_service.build_tree(province=province, city=city, county=county)
        except ValueError as exc:
            return _error(str(exc), 400)
        except LookupError as exc:
            return _error(str(exc), 400)
        return _success(result)

    return app


app = create_app()
