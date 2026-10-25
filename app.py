"""Exoplanet Hunter JSON API. Run locally with: python app.py."""

import math
from pathlib import Path

import pandas as pd
from flask import Flask, jsonify, make_response, render_template, request
from werkzeug.exceptions import BadRequest, HTTPException

from backend import APIError, Catalog, DATASET_SOURCE, FEATURES, LABELS, Predictor, SCORE_NOTE
from frontend import frontend

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "models" / "exoplanet_rf.joblib"
DATA_PATH = BASE_DIR / "data" / "kepler_raw.csv"


def create_app(config=None):
    app = Flask(__name__)
    app.register_blueprint(frontend)
    app.config.from_mapping(MODEL_PATH=MODEL_PATH, DATA_PATH=DATA_PATH, MAX_CONTENT_LENGTH=16 * 1024)
    if config:
        app.config.update(config)
    # Load once per application initialization. Resource failures leave health
    # accessible and return 503 on dependent routes; details stay in server logs.
    for name, loader, path in (
        ("predictor", Predictor, app.config["MODEL_PATH"]),
        ("catalog", Catalog, app.config["DATA_PATH"]),
    ):
        try:
            app.extensions[name] = loader(path)
        except Exception:
            app.logger.exception("Could not initialize %s", name)
            app.extensions[name] = None

    def resource(name):
        value = app.extensions[name]
        if value is None:
            raise APIError("resource_unavailable", f"The {name} is unavailable. Check the local server logs.", 503)
        return value

    @app.errorhandler(APIError)
    def api_error(error):
        body = {"code": error.code, "message": str(error)}
        if error.details is not None:
            body["details"] = error.details
        return jsonify(success=False, error=body), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        response = error.get_response()  # Preserve protocol headers such as Allow.
        response.data = app.json.dumps({"success": False, "error": {
            "code": error.name.lower().replace(" ", "_"), "message": error.description,
        }})
        response.content_type = "application/json"
        return response

    @app.errorhandler(Exception)
    def unexpected_error(error):
        app.logger.exception("Unhandled API error")
        return jsonify(success=False, error={
            "code": "internal_error", "message": "The request could not be completed. Check the local server logs.",
        }), 500

    @app.get("/")
    def home():
        # Browsers receive the homepage. Preserve the original JSON contract for
        # API clients without an HTML preference, including the existing tests.
        if request.accept_mimetypes.best_match(["application/json", "text/html"]) == "text/html":
            response = make_response(render_template("home.html"))
        else:
            response = api_home()
        response.vary.add("Accept")
        return response

    @app.get("/api")
    def api_home():
        return jsonify(project="Exoplanet Hunter", message="Welcome to the Exoplanet Hunter API!")

    @app.get("/api/health")
    def health():
        model_loaded = app.extensions["predictor"] is not None
        dataset_loaded = app.extensions["catalog"] is not None
        ready = model_loaded and dataset_loaded
        return jsonify(
            status="success" if ready else "degraded",
            message="Exoplanet Hunter API is running", model="Random Forest",
            model_loaded=model_loaded, dataset_loaded=dataset_loaded,
        ), 200 if ready else 503

    @app.post("/api/predict")
    def predict():
        if not request.is_json:
            raise APIError("invalid_json", "Use Content-Type: application/json with a JSON object.")
        try:
            payload = request.get_json()
        except BadRequest:
            raise APIError("invalid_json", "The request body is not valid JSON.") from None
        return jsonify(resource("predictor").predict(payload))

    def positive_integer(name, default, maximum=None):
        raw = request.args.get(name, str(default))
        if len(request.args.getlist(name)) > 1 or not raw.isascii() or not raw.isdecimal() or len(raw) > 10:
            raise APIError("invalid_pagination", f"{name} must be a positive integer.")
        value = int(raw)
        if value < 1 or (maximum is not None and value > maximum):
            message = f"{name} must be between 1 and {maximum}." if maximum else f"{name} must be positive."
            raise APIError("invalid_pagination", message)
        return value

    @app.get("/api/objects")
    def objects():
        page = positive_integer("page", 1)
        per_page = positive_integer("per_page", 20, 100)
        query = request.args.get("q", "").strip()
        if len(query) > 200 or len(request.args.getlist("q")) > 1:
            raise APIError("invalid_search", "Provide one search query of at most 200 characters.")
        catalog = resource("catalog")
        matches = catalog.search(query)
        total = len(matches)
        start = (page - 1) * per_page
        return jsonify(
            success=True, objects=[catalog.record(row) for _, row in matches.iloc[start:start + per_page].iterrows()],
            pagination={"page": page, "per_page": per_page, "total": total,
                        "total_pages": math.ceil(total / per_page),
                        "has_next": start + per_page < total, "has_previous": page > 1 and total > 0},
        )

    @app.get("/api/objects/<object_id>")
    def object_detail(object_id):
        catalog = resource("catalog")
        return jsonify(success=True, object=catalog.record(catalog.lookup(object_id), full=True))

    @app.get("/api/objects/<object_id>/predict")
    def object_prediction(object_id):
        catalog = resource("catalog")
        row = catalog.lookup(object_id)
        record = catalog.record(row, full=True)
        # Only genuinely missing values become null; infinities/text must fail validation.
        payload = {name: None if pd.isna(row[name]) else row[name] for name in FEATURES}
        try:
            result = resource("predictor").predict(payload)
        except APIError as error:
            if error.status != 400:
                raise
            raise APIError(
                "observation_not_evaluable", "The catalog observation contains unavailable or invalid measurements.",
                422, {"reason": str(error), "validation": error.details},
            ) from None
        return jsonify(success=True, object=record, model_prediction=result)

    @app.get("/api/stats")
    def stats():
        return jsonify(success=True, **resource("catalog").statistics())

    @app.get("/api/model/info")
    def model_info():
        predictor = app.extensions["predictor"]
        return jsonify(
            success=True, algorithm="Random Forest", model_loaded=predictor is not None,
            input_features=FEATURES, classification_labels={str(k): v for k, v in LABELS.items()},
            supports_partial_nulls=bool(predictor and predictor.supports_nulls),
            historical_evaluation={
                "test_accuracy": 0.8165, "test_roc_auc": 0.9024,
                "test_weighted_f1": 0.82, "validation_accuracy": 0.8358,
                "source": "Previously recorded project experiments; approximate values supplied in the project brief.",
                "calculated_by_api": False,
            },
            dataset_source=DATASET_SOURCE,
            description="Saved median-imputation and Random Forest pipeline; class 1 combines confirmed and candidate observations.",
            limitations=[SCORE_NOTE, "Historical evaluation results do not guarantee performance on new observations.",
                         "Missing measurements use training-set medians from the saved imputer."],
        )

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)

