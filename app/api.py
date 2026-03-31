from __future__ import annotations

from flask import Flask, jsonify, request

from .service import AddressExtractionService, PROJECT_NAME


service = AddressExtractionService()


def create_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health() -> tuple:
        return jsonify({"status": "ok", "project": PROJECT_NAME}), 200

    @app.post("/api/v1/parse")
    def parse() -> tuple:
        payload = request.get_json(silent=True) or {}
        text = payload.get("text")
        if not isinstance(text, str) or not text.strip():
            return jsonify({"error": "`text` must be a non-empty string"}), 400
        return jsonify(service.parse_text(text)), 200

    return app


app = create_app()
