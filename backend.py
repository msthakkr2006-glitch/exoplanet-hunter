"""Read-only catalog access and inference with the existing fitted pipeline."""

import math
from numbers import Real

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

FEATURES = [
    "koi_period", "koi_duration", "koi_depth", "koi_prad", "koi_teq",
    "koi_insol", "koi_steff", "koi_srad", "koi_impact", "koi_model_snr",
]
LABELS = {0: "False Positive", 1: "Planet-like"}
DATASET_SOURCE = "NASA Exoplanet Archive — Kepler Objects of Interest (local catalog)"
SCORE_NOTE = (
    "The class-1 model score is not a scientifically verified probability that "
    "an exoplanet exists. This model classifies historical Kepler measurements; "
    "it does not independently discover or confirm exoplanets."
)
POSITIVE_FEATURES = {
    "koi_period", "koi_duration", "koi_prad", "koi_teq", "koi_steff", "koi_srad",
}
MAX_MODEL_VALUE = float(np.finfo(np.float32).max)


class APIError(Exception):
    def __init__(self, code, message, status=400, details=None):
        super().__init__(message)
        self.code = code
        self.status = status
        self.details = details


def observation_frame(payload, supports_nulls=True):
    """Validate measurements, then explicitly enforce the training column order."""
    if not isinstance(payload, dict):
        raise APIError("invalid_input", "Expected a JSON object containing the ten features.")
    missing = [name for name in FEATURES if name not in payload]
    extra = sorted(set(payload) - set(FEATURES))
    if missing or extra:
        raise APIError("invalid_features", "Provide exactly the ten required feature keys.",
                       details={"missing": missing, "unknown": extra})
    values, errors = [], {}
    for name in FEATURES:
        value = payload[name]
        if value is None:
            if not supports_nulls:
                errors[name] = "The loaded pipeline does not support null measurements."
            values.append(np.nan)
            continue
        if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
            errors[name] = "Must be a JSON number or null; booleans and numeric strings are invalid."
            values.append(np.nan)
            continue
        try:
            value = float(value)
        except (OverflowError, ValueError):
            value = float("inf")
        if not math.isfinite(value):
            errors[name] = "Must be finite; NaN and infinity are invalid."
        elif value < 0 or (name in POSITIVE_FEATURES and value == 0):
            errors[name] = "Must be greater than zero." if name in POSITIVE_FEATURES else "Must be nonnegative."
        elif value > MAX_MODEL_VALUE:
            errors[name] = "Exceeds the numeric representation supported by the saved Random Forest."
        values.append(value)
    if errors:
        raise APIError("invalid_measurements", "Some measurements are invalid.", details=errors)
    if all(math.isnan(value) for value in values):
        raise APIError("no_measurements", "At least one measured feature is required; all values are null.")
    return pd.DataFrame([values], columns=FEATURES, dtype=float)


class Predictor:
    def __init__(self, path):
        # Only the fixed, trusted local artifact is deserialized. Never fit or save it.
        self.model = joblib.load(path)
        if not isinstance(self.model, Pipeline):
            raise ValueError("Expected the saved scikit-learn Pipeline.")
        if list(self.model.feature_names_in_) != FEATURES:
            raise ValueError("Saved model feature names/order do not match the API contract.")
        if not isinstance(self.model.steps[-1][1], RandomForestClassifier):
            raise ValueError("Expected the existing Random Forest classifier.")
        self.classes = list(self.model.classes_)
        if set(self.classes) != {0, 1}:
            raise ValueError("Expected binary classes 0 and 1.")
        imputer = self.model.steps[0][1]
        self.supports_nulls = (
            isinstance(imputer, SimpleImputer)
            and imputer.strategy == "median"
            and len(imputer.statistics_) == len(FEATURES)
            and bool(np.isfinite(imputer.statistics_).all())
            and bool(pd.isna(imputer.missing_values))
        )

    def predict(self, payload):
        frame = observation_frame(payload, self.supports_nulls)
        prediction = int(self.model.predict(frame)[0])
        score = float(self.model.predict_proba(frame)[0, self.classes.index(1)])
        if prediction not in LABELS or not math.isfinite(score) or not 0 <= score <= 1:
            raise RuntimeError("Invalid output from the saved model.")
        return {
            "success": True, "prediction": prediction,
            "classification": LABELS[prediction], "planet_like_score": score,
            "model": "Random Forest",
            "imputed_features": [name for name in FEATURES if payload[name] is None],
            "score_note": SCORE_NOTE,
        }


def json_scalar(value):
    if pd.isna(value):
        return None
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


class Catalog:
    def __init__(self, path):
        self.data = pd.read_csv(path, comment="#")
        required = set(FEATURES) | {"kepid", "kepoi_name", "koi_disposition"}
        if not required.issubset(self.data.columns):
            raise ValueError("Catalog is missing required feature or identifier columns.")
        if self.data.empty or self.data.kepoi_name.isna().any() or self.data.kepoi_name.duplicated().any():
            raise ValueError("Catalog must have unique, non-null KOI observation identifiers.")
        self.identifiers = [c for c in ("kepoi_name", "kepler_name", "kepid") if c in self.data]
        self.lookup_index = {}
        for index, row in self.data[self.identifiers].iterrows():
            for column in self.identifiers:
                if pd.notna(row[column]):
                    key = str(row[column]).casefold()
                    self.lookup_index.setdefault(key, set()).add(index)

    def record(self, row, full=False):
        result = {
            "object_id": str(row.kepoi_name),
            "identifiers": {name: json_scalar(row[name]) for name in self.identifiers},
            "nasa_disposition": json_scalar(row.koi_disposition),
            "features": {name: json_scalar(row[name]) for name in FEATURES},
        }
        if full:
            result["catalog"] = {name: json_scalar(value) for name, value in row.items()}
        return result

    def lookup(self, object_id):
        matches = sorted(self.lookup_index.get(object_id.strip().casefold(), set()))
        if not matches:
            raise APIError("object_not_found", "No Kepler observation matches this identifier.", 404)
        if len(matches) > 1:
            raise APIError(
                "ambiguous_identifier", "This identifier matches multiple observations. Use a KOI object_id.",
                409, {"match_count": len(matches),
                      "object_ids": self.data.loc[matches[:100], "kepoi_name"].tolist(),
                      "truncated": len(matches) > 100},
            )
        return self.data.loc[matches[0]]

    def search(self, query):
        if not query:
            return self.data
        mask = pd.Series(False, index=self.data.index)
        for name in self.identifiers:
            mask |= self.data[name].astype("string").str.contains(query, case=False, regex=False, na=False)
        return self.data.loc[mask]

    def statistics(self):
        counts = self.data.koi_disposition.value_counts()
        return {
            "total_observations": len(self.data),
            "confirmed": int(counts.get("CONFIRMED", 0)),
            "candidate": int(counts.get("CANDIDATE", 0)),
            "false_positive": int(counts.get("FALSE POSITIVE", 0)),
            "host_stars": int(self.data.kepid.nunique()),
            "dataset_source": DATASET_SOURCE,
            "available_features": [name for name in FEATURES if name in self.data],
        }
