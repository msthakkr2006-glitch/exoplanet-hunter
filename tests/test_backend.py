"""Integration tests using the trusted saved model and real local NASA records."""

import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def protected_hashes():
    return {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for folder in ("data", "models", "notebooks")
            for path in (ROOT / folder).rglob("*") if path.is_file()}


BEFORE_IMPORT = protected_hashes()
from app import app, create_app  # noqa: E402
from backend import FEATURES, LABELS, Predictor, observation_frame  # noqa: E402


class BackendTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        app.config["TESTING"] = True
        cls.app = app
        cls.client = app.test_client()
        cls.raw = pd.read_csv(ROOT / "data" / "kepler_raw.csv", comment="#")
        cls.direct_model = joblib.load(ROOT / "models" / "exoplanet_rf.joblib")
        cls.payload = cls.raw.loc[0, FEATURES].astype(float).to_dict()

    @classmethod
    def tearDownClass(cls):
        if protected_hashes() != BEFORE_IMPORT:
            raise AssertionError("Protected files changed during backend tests.")

    def assert_json(self, response, status=200):
        self.assertEqual(response.status_code, status, response.get_data(as_text=True))
        self.assertEqual(response.mimetype, "application/json")
        def reject_nonfinite(token):
            raise AssertionError(f"Non-standard JSON constant: {token}")
        return json.loads(response.get_data(as_text=True), parse_constant=reject_nonfinite)

    def assert_matches_model(self, response, frame):
        prediction = int(self.direct_model.predict(frame)[0])
        index = list(self.direct_model.classes_).index(1)
        score = float(self.direct_model.predict_proba(frame)[0, index])
        self.assertEqual(response["prediction"], prediction)
        self.assertEqual(response["classification"], LABELS[prediction])
        self.assertAlmostEqual(response["planet_like_score"], score, places=12)
        self.assertIn("not a scientifically verified probability", response["score_note"])

    def test_home_and_health_preserved(self):
        self.assertEqual(self.assert_json(self.client.get("/"))["project"], "Exoplanet Hunter")
        health = self.assert_json(self.client.get("/api/health"))
        self.assertEqual(health["status"], "success")
        self.assertTrue(health["model_loaded"])
        self.assertTrue(health["dataset_loaded"])
        self.assertFalse(self.app.debug)

    def test_saved_pipeline_loaded_once(self):
        self.assertIsInstance(self.app.extensions["predictor"], Predictor)
        self.assertEqual(list(self.direct_model.feature_names_in_), FEATURES)
        with patch("backend.joblib.load", side_effect=AssertionError("Reloaded during request")):
            for _ in range(2):
                self.assert_json(self.client.post("/api/predict", json=self.payload))

    def test_real_records_match_direct_pipeline_and_both_classes(self):
        sample = self.raw.groupby("koi_disposition", sort=True).head(3)
        observed = set()
        for _, row in sample.iterrows():
            payload = {name: None if pd.isna(row[name]) else float(row[name]) for name in FEATURES}
            body = self.assert_json(self.client.post("/api/predict", json=payload))
            self.assert_matches_model(body, pd.DataFrame([payload], columns=FEATURES, dtype=float))
            observed.add(body["prediction"])
        self.assertEqual(observed, {0, 1})

    def test_feature_order_reaches_pipeline(self):
        predictor = self.app.extensions["predictor"]
        reversed_payload = dict(reversed(list(self.payload.items())))
        with patch.object(predictor.model, "predict", wraps=predictor.model.predict) as predict:
            body = self.assert_json(self.client.post("/api/predict", json=reversed_payload))
            actual_frame = predict.call_args.args[0]
            self.assertEqual(list(actual_frame.columns), FEATURES)
            self.assertEqual(actual_frame.iloc[0].tolist(), [self.payload[name] for name in FEATURES])
        self.assert_matches_model(body, pd.DataFrame([self.payload], columns=FEATURES))

    def test_class_one_score_uses_class_mapping(self):
        predictor = self.app.extensions["predictor"]
        with patch.object(predictor, "classes", [1, 0]), \
             patch.object(predictor.model, "predict", return_value=np.array([1])), \
             patch.object(predictor.model, "predict_proba", return_value=np.array([[0.8, 0.2]])):
            body = self.assert_json(self.client.post("/api/predict", json=self.payload))
        self.assertEqual(body["planet_like_score"], 0.8)

    def test_partial_null_uses_saved_imputer(self):
        payload = {**self.payload, "koi_depth": None}
        body = self.assert_json(self.client.post("/api/predict", json=payload))
        self.assertEqual(body["imputed_features"], ["koi_depth"])
        self.assert_matches_model(body, pd.DataFrame([payload], columns=FEATURES, dtype=float))

    def test_missing_extra_and_all_null_features(self):
        for payload in ({}, {**self.payload, "unexpected": 1}, {name: None for name in FEATURES}):
            with self.subTest(payload=payload):
                self.assertFalse(self.assert_json(self.client.post("/api/predict", json=payload), 400)["success"])

    def test_invalid_json_and_body_shapes(self):
        for raw in ("", "{", "null", "[]", "42", '"text"', "true"):
            with self.subTest(raw=raw):
                self.assert_json(self.client.post("/api/predict", data=raw, content_type="application/json"), 400)
        self.assert_json(self.client.post("/api/predict", data=json.dumps(self.payload)), 400)

    def test_invalid_numbers(self):
        for value in (True, False, "12.5", "bad", [], {}, float("nan"), float("inf"),
                      -float("inf"), -1, 0, 1e100, 10 ** 400):
            with self.subTest(value=str(value)[:30]):
                body = self.assert_json(self.client.post("/api/predict", json={**self.payload, "koi_period": value}), 400)
                self.assertIn("koi_period", body["error"]["details"])

    def test_nonnegative_fields_and_real_catalog_extremes(self):
        for name in ("koi_depth", "koi_insol", "koi_impact", "koi_model_snr"):
            self.assert_json(self.client.post("/api/predict", json={**self.payload, name: 0}))
            self.assert_json(self.client.post("/api/predict", json={**self.payload, name: -1}), 400)
        for name in FEATURES:
            row = self.raw.loc[self.raw[name].idxmax()]
            payload = {f: None if pd.isna(row[f]) else float(row[f]) for f in FEATURES}
            self.assert_json(self.client.post("/api/predict", json=payload))

    def test_all_catalog_rows_pass_measurement_validation(self):
        # No inference/training: ensure conservative bounds accept the actual catalog.
        for row in self.raw[FEATURES].itertuples(index=False, name=None):
            payload = {name: None if pd.isna(value) else value for name, value in zip(FEATURES, row)}
            observation_frame(payload)

    def test_pagination_and_empty_pages(self):
        first = self.assert_json(self.client.get("/api/objects"))
        self.assertEqual(len(first["objects"]), 20)
        self.assertEqual(first["pagination"]["total"], len(self.raw))
        self.assertEqual(first["pagination"]["total_pages"], math.ceil(len(self.raw) / 20))
        second = self.assert_json(self.client.get("/api/objects?page=2&per_page=3"))
        self.assertEqual([row["object_id"] for row in second["objects"]], self.raw.kepoi_name.iloc[3:6].tolist())
        self.assertEqual(len(self.assert_json(self.client.get("/api/objects?per_page=100"))["objects"]), 100)
        empty = self.assert_json(self.client.get("/api/objects?page=999999"))
        self.assertEqual(empty["objects"], [])
        self.assertFalse(empty["pagination"]["has_next"])

    def test_invalid_pagination_and_search(self):
        for query in ("page=0", "page=-1", "page=1.5", "page=abc", "page=", "per_page=0", "per_page=101",
                      "page=1&page=2", "per_page=1&per_page=2", "q=a&q=b", "q=" + "x" * 201):
            with self.subTest(query=query):
                self.assert_json(self.client.get("/api/objects?" + query), 400)

    def test_search_identifiers_and_literal_matching(self):
        for query in ("k00752.01", "Kepler-227 b", "10797460"):
            body = self.assert_json(self.client.get("/api/objects", query_string={"q": query}))
            self.assertGreater(body["pagination"]["total"], 0)
            self.assertIn("K00752.01", [item["object_id"] for item in body["objects"]])
        for query in ("no-such-object", ".*", "["):
            body = self.assert_json(self.client.get("/api/objects", query_string={"q": query}))
            self.assertEqual(body["pagination"]["total"], 0)

    def test_lookup_and_alias_are_real_observations(self):
        for identifier in ("K00752.01", "k00752.01", "Kepler-227 b"):
            obj = self.assert_json(self.client.get("/api/objects/" + identifier))["object"]
            self.assertEqual(obj["object_id"], self.raw.iloc[0].kepoi_name)
            self.assertEqual(obj["nasa_disposition"], self.raw.iloc[0].koi_disposition)
            self.assertEqual(obj["features"], self.payload)
            self.assertIsNone(obj["catalog"]["koi_teq_err1"])
            self.assertEqual(set(obj["catalog"]), set(self.raw.columns))

    def test_ambiguous_host_and_unknown_ids(self):
        expected = set(self.raw.loc[self.raw.kepid == 10797460, "kepoi_name"])
        for suffix in ("", "/predict"):
            body = self.assert_json(self.client.get("/api/objects/10797460" + suffix), 409)
            self.assertEqual(set(body["error"]["details"]["object_ids"]), expected)
            self.assert_json(self.client.get("/api/objects/not-a-real-id" + suffix), 404)

    def test_unique_host_lookup(self):
        counts = self.raw.kepid.value_counts()
        host = counts[counts == 1].index[0]
        obj = self.assert_json(self.client.get(f"/api/objects/{host}"))["object"]
        self.assertEqual(obj["object_id"], self.raw.loc[self.raw.kepid == host, "kepoi_name"].iloc[0])

    def test_catalog_prediction_separates_nasa_disposition(self):
        body = self.assert_json(self.client.get("/api/objects/K00752.01/predict"))
        self.assertEqual(body["object"]["nasa_disposition"], "CONFIRMED")
        self.assert_matches_model(body["model_prediction"], self.raw.loc[[0], FEATURES])

    def test_catalog_missing_measurements_imputed(self):
        row = self.raw.loc[self.raw[FEATURES].isna().any(axis=1)].iloc[0]
        body = self.assert_json(self.client.get(f"/api/objects/{row.kepoi_name}/predict"))
        self.assertTrue(body["model_prediction"]["imputed_features"])
        self.assert_matches_model(body["model_prediction"], self.raw.loc[[row.name], FEATURES])

    def test_invalid_catalog_measurements_explained(self):
        catalog = self.app.extensions["catalog"]
        for value in (-1, np.inf, "bad"):
            row = self.raw.iloc[0].copy()
            row["koi_period"] = value
            with patch.object(catalog, "lookup", return_value=row):
                body = self.assert_json(self.client.get("/api/objects/K00752.01/predict"), 422)
                self.assertEqual(body["error"]["code"], "observation_not_evaluable")
        row = self.raw.iloc[0].copy()
        row[FEATURES] = np.nan
        with patch.object(catalog, "lookup", return_value=row):
            self.assert_json(self.client.get("/api/objects/K00752.01/predict"), 422)

    def test_stats_match_csv(self):
        body = self.assert_json(self.client.get("/api/stats"))
        self.assertEqual(body["total_observations"], len(self.raw))
        for field, label in (("confirmed", "CONFIRMED"), ("candidate", "CANDIDATE"), ("false_positive", "FALSE POSITIVE")):
            self.assertEqual(body[field], int((self.raw.koi_disposition == label).sum()))
        self.assertEqual(body["host_stars"], self.raw.kepid.nunique())
        self.assertEqual(body["available_features"], FEATURES)

    def test_model_metadata_is_historical(self):
        body = self.assert_json(self.client.get("/api/model/info"))
        self.assertEqual(body["input_features"], FEATURES)
        self.assertEqual(body["classification_labels"], {"0": "False Positive", "1": "Planet-like"})
        self.assertFalse(body["historical_evaluation"]["calculated_by_api"])
        self.assertTrue(body["supports_partial_nulls"])

    def test_json_http_errors_and_size_limit(self):
        self.assert_json(self.client.get("/not-a-route"), 404)
        response = self.client.get("/api/predict")
        self.assert_json(response, 405)
        self.assertIn("POST", response.headers["Allow"])
        self.assert_json(self.client.post("/api/predict", data=" " * 17000, content_type="application/json"), 413)

    def test_internal_errors_do_not_leak(self):
        predictor = self.app.extensions["predictor"]
        with patch.object(predictor.model, "predict", side_effect=RuntimeError("private path or trace")), \
             self.assertLogs(self.app.logger, level="ERROR"):
            response = self.client.post("/api/predict", json=self.payload)
        self.assert_json(response, 500)
        self.assertNotIn("private", response.get_data(as_text=True))

    def test_missing_model_or_dataset_degrades_cleanly(self):
        for key, dependent in (("MODEL_PATH", "/api/predict"), ("DATA_PATH", "/api/stats")):
            with self.assertLogs("app", level="ERROR"):
                degraded = create_app({key: ROOT / "does-not-exist", "TESTING": True}).test_client()
            health = self.assert_json(degraded.get("/api/health"), 503)
            self.assertEqual(health["status"], "degraded")
            response = degraded.post(dependent, json=self.payload) if key == "MODEL_PATH" else degraded.get(dependent)
            self.assert_json(response, 503)
            self.assertNotIn(str(ROOT), response.get_data(as_text=True))
            self.assert_json(degraded.get("/"))
            self.assert_json(degraded.get("/api/model/info"))

    def test_corrupt_model_failure_is_handled(self):
        with patch("backend.joblib.load", side_effect=ValueError("bad artifact")), self.assertLogs("app", level="ERROR"):
            degraded = create_app({"TESTING": True}).test_client()
        self.assertFalse(self.assert_json(degraded.get("/api/health"), 503)["model_loaded"])

    def test_paths_work_from_other_directory(self):
        script = (
            f"import sys; sys.path.insert(0, {str(ROOT)!r}); "
            "from app import app; response=app.test_client().get('/api/health'); "
            "assert response.status_code == 200, response.get_json()"
        )
        result = subprocess.run([sys.executable, "-c", script], cwd=ROOT / "tests", capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_protected_files_unchanged(self):
        self.assertEqual(protected_hashes(), BEFORE_IMPORT)


if __name__ == "__main__":
    unittest.main()
