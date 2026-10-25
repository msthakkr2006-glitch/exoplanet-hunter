# Exoplanet Hunter backend

Local Flask JSON API using the existing trusted `models/exoplanet_rf.joblib`.
The model and raw catalog are loaded once per application initialization. No
training, notebook execution, dataset writes, or live NASA requests occur.

## Run and test (PowerShell)

The runtime was verified with Python 3.13.5. See the [README](README.md#installation)
for environment setup. `requirements.txt` pins the versions used with the saved
model. Install them with `python -m pip install -r requirements.txt` in your environment.
Do not upgrade scikit-learn independently of checking artifact compatibility.

```powershell
Set-Location exoplanet-hunter
python app.py
```

The development server listens at `http://127.0.0.1:5000`, with debugging disabled.
Stop with Ctrl+C. Model and catalog paths are resolved relative to `app.py`,
so resource loading does not depend on the current working directory.
Unrestricted CORS is not enabled.

```powershell
python -m unittest discover -s tests -v
```

Tests use Flask's test client and the actual saved pipeline and NASA records.
They compare direct inference with API results, exercise validation, verify
counts against the CSV, and hash all datasets, models, and notebooks before and
after the test run. No additional test dependencies are required.

## Routes

| Method | Path | Result |
|---|---|---|
| GET | `/` | Homepage for browsers (`Accept: text/html`); original welcome JSON for API clients |
| GET | `/explore`, `/predict`, `/model`, `/about` | HTML pages using the JSON APIs |
| GET | `/api` | Explicit project welcome JSON |
| GET | `/api/health` | Application status, `model_loaded`, `dataset_loaded` |
| POST | `/api/predict` | Prediction for ten supplied measurements |
| GET | `/api/objects?page=1&per_page=20&q=Kepler-227` | Paginated catalog search |
| GET | `/api/objects/<object_id>` | One observation, including all catalog columns |
| GET | `/api/objects/<object_id>/predict` | Catalog observation and separate model prediction |
| GET | `/api/stats` | Counts calculated from the loaded raw catalog |
| GET | `/api/model/info` | Feature order, labels, historical metrics, limitations |

### Predict

The homepage uses content negotiation with `Vary: Accept`. Requests with no
Accept header, `*/*`, or a preference for JSON preserve the original root JSON
response. Browser requests preferring HTML receive the homepage. All
existing `/api/...` response contracts are unchanged.

Send `Content-Type: application/json` and exactly these feature keys. Object key
order is irrelevant: the DataFrame always uses the order below.

| Feature | Meaning / units | Accepted measured value |
|---|---|---|
| `koi_period` | Orbital period, days | > 0 |
| `koi_duration` | Transit duration, hours | > 0 |
| `koi_depth` | Transit depth, parts per million | >= 0 |
| `koi_prad` | Estimated planet radius, Earth radii | > 0 |
| `koi_teq` | Equilibrium temperature, kelvin | > 0 |
| `koi_insol` | Insolation flux relative to Earth | >= 0 |
| `koi_steff` | Host-star effective temperature, kelvin | > 0 |
| `koi_srad` | Host-star radius, solar radii | > 0 |
| `koi_impact` | Transit impact parameter | >= 0 |
| `koi_model_snr` | Transit model signal-to-noise ratio | >= 0 |

All values must be finite JSON numbers or explicit `null`. Strings, booleans,
arrays, missing keys, unknown keys, NaN, and infinities return 400. Partial nulls
become NaN and use the **existing fitted median imputer**; the response names
these fields in `imputed_features`. All-null observations return 400 because
they contain no measured inputs. No additional scientific upper bounds are
imposed: large catalog values, including impact parameters above 1 and depths
above one million ppm, remain accepted. Values above float32's maximum are
rejected because the saved forest cannot represent them. Request bodies are
limited to 16 KiB (413 when exceeded).

Example using the actual local catalog observation **K00752.01 / Kepler-227 b**:

```json
{
  "koi_period": 9.48803557,
  "koi_duration": 2.9575,
  "koi_depth": 615.8,
  "koi_prad": 2.26,
  "koi_teq": 793.0,
  "koi_insol": 93.59,
  "koi_steff": 5455.0,
  "koi_srad": 0.927,
  "koi_impact": 0.146,
  "koi_model_snr": 35.8
}
```

Successful responses contain `success`, integer `prediction` (0 or 1),
`classification` (`False Positive` or `Planet-like`), `planet_like_score`,
`model` (`Random Forest`), `imputed_features`, and `score_note`.
The score is taken from `predict_proba` at the class-1 column, located using
the pipeline's class labels; the prediction comes from `predict`.

`Planet-like` combines the project's confirmed and candidate training labels.
The class-1 model score is **not a scientifically verified probability that an
exoplanet exists**. The application classifies historical Kepler measurements;
it does not independently discover or confirm exoplanets.

### Catalog browsing and lookup

`page` starts at 1. `per_page` defaults to 20 and must be 1–100. Both must be
positive decimal integers. `q` is an optional, case-insensitive literal substring
search across KOI name, Kepler name, and host-star ID, limited to 200 characters.
Repeated pagination/search parameters are rejected. Results retain CSV order.
An unmatched search or a page past the end returns an empty `objects` array.

List responses have `success`, `objects`, and `pagination` containing `page`,
`per_page`, `total` (matching observations), `total_pages`, `has_next`, and
`has_previous`. Each object contains:

- `object_id`: the unique KOI observation name, e.g. `K00752.01`.
- `identifiers`: `kepoi_name`, `kepler_name`, and `kepid` where available.
- `nasa_disposition`: NASA's `koi_disposition`, kept separate from inference.
- `features`: the ten measurements; missing values serialize as JSON null.

Detail responses have `success` and `object`, which additionally contains a
`catalog` dictionary of all 49 source columns (including uncertainties and the
original NASA disposition fields). Non-finite catalog display values become null.

Lookup accepts exact KOI names, Kepler names, or decimal host-star IDs,
case-insensitively. URL-encode names containing spaces. Prefer `object_id` from
the listing. A `kepid` identifies a **host star**, which can have multiple
observations. Ambiguous aliases return 409 with `match_count`, up to 100 matching
`object_ids`, and `truncated`; the API never chooses an arbitrary observation.
Unknown identifiers return 404.

Object prediction responses contain `success`, `object`, and `model_prediction`.
`object.nasa_disposition` is the catalog label; `model_prediction` has the same
fields as POST inference. Missing catalog measurements use the saved imputer.
Invalid or entirely unavailable measurements return 422 with validation details.
Invalid numeric catalog values are rejected, not silently imputed.

```powershell
$observation = Invoke-RestMethod 'http://127.0.0.1:5000/api/objects/K00752.01'
$body = $observation.object.features | ConvertTo-Json
Invoke-RestMethod 'http://127.0.0.1:5000/api/predict' -Method Post -ContentType 'application/json' -Body $body
Invoke-RestMethod 'http://127.0.0.1:5000/api/objects/K00752.01/predict'
```

### Statistics and model information

`/api/stats` returns `success`, `total_observations`, `confirmed`, `candidate`,
`false_positive`, `host_stars` (distinct non-null `kepid`), `dataset_source`,
and `available_features`. Counts describe the loaded catalog, not model results.

The raw CSV is read with `comment="#"` and supplies both identifiers and all ten
features. The prepared file, `data/model_data.csv`, contains the same feature values as
the raw CSV. The backend
does not join the files or rely on their row alignment. Restart the application
to reload local resources after any separately authorized future changes.

`/api/model/info` includes `algorithm`, `model_loaded`, `input_features`,
`classification_labels`, `supports_partial_nulls`, `dataset_source`,
`description`, `limitations`, and `historical_evaluation`. The latter records
approximately 0.8165 test accuracy, 0.9024 test ROC-AUC, 0.82 weighted F1, and
0.8358 validation accuracy, matching the recorded training-notebook results. They are labeled
historical with `calculated_by_api: false`; no evaluation or retraining is run
by this endpoint. The test set was inspected during development, so these results
are not an untouched independent benchmark.

### Errors and resource failures

Errors are JSON, including routing errors:

```json
{
  "success": false,
  "error": {
    "code": "invalid_measurements",
    "message": "Some measurements are invalid.",
    "details": {"koi_period": "Must be greater than zero."}
  }
}
```

`details` is optional. Status codes: 400 invalid requests, 404 unknown objects or
routes, 405 unsupported methods, 409 ambiguous identifiers, 413 oversized body,
422 unevaluable catalog observation, 500 unexpected inference/server failure,
and 503 unavailable model/catalog. Stack traces and resource paths stay in the
local server logs. Missing/corrupt resources leave the homepage and model metadata
accessible. Health returns 503 with `status: degraded`; dependent routes return
503. Healthy startup returns 200 with `status: success` and both load flags true.
Only the configured trusted local model is deserialized; no API accepts paths.
