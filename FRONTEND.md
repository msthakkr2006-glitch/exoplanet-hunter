# Frontend

The website uses Flask templates, local CSS, and vanilla JavaScript. It has no
frontend build step or external font dependency. Setup is covered in the
[README](README.md#installation).

## Pages

| Route | Purpose | API requests |
|---|---|---|
| `/` | Homepage, archive counts, and an introduction to the model | `/api/stats` |
| `/explore` | Search, pagination, and observation details | `/api/objects`, `/api/objects/<object_id>` |
| `/predict` | Manual or catalog-based classification | `/api/objects/<object_id>`, `/api/predict` |
| `/model` | Recorded model comparison, test results, and feature explanations | `/api/model/info` |
| `/about` | Project purpose, dataset counts, technology, and credits | `/api/stats`, `/api/model/info` |

Explore passes the selected KOI identifier to Predict in the `object_id` query
parameter. Predict loads that observation's measurements rather than using
sample values. Host-star IDs that match several observations display a choice
of KOI identifiers.

The prediction form has ten fields in the model's training order. Empty fields
are sent as null and use the saved training medians. An entirely blank form,
non-finite numbers, and physically invalid negative or zero values are rejected.
Editing a field clears the previous result. The displayed score is the model's
class-1 output; NASA's catalog disposition is shown separately.

The Model page separates validation results from final test results. The
comparison is a recorded project result; it is not recalculated by the frontend.
The application does not retrain the model.

## Files

- `templates/base.html`: shared header, footer, navigation, and asset loading.
- `templates/home.html`: homepage sections.
- `templates/interior.html`: shared layout for the four interior pages.
- `templates/explore.html`, `predict.html`, `model.html`, and `about.html`: page content.
- `templates/icons.html`: shared SVG icons.
- `static/css/site.css`: shared design tokens and homepage styling.
- `static/css/interior.css`: interior page layouts; not loaded on the homepage.
- `static/js/home.js`: homepage navigation, scroll effects, and archive counts.
- `static/js/interior.js`: interior navigation and shared API helpers.
- `static/js/explore.js`, `predict.js`, `model.js`, and `about.js`: page interactions.
- `static/images/starfield.png`: original supplied photograph, 1647 x 867 pixels.
- `static/images/orbit.svg`: orbital favicon.
- `frontend.py`: page routes, feature labels, and recorded validation values.

The original photograph is stored unchanged. CSS controls its crop and overlays.
Planet silhouettes and orbital diagrams are illustrations rather than images of
specific Kepler objects.

## Interaction and accessibility

The homepage uses short entrance animations, scroll reveals, and restrained
parallax. Reduced-motion preferences disable animations and transitions.
The navigation collapses to a mobile menu with Escape dismissal. A skip link,
visible focus styles, input labels, and validation messages support keyboard use.

Explore and Predict stack their panels on smaller screens. Tables scroll within
their own regions. API requests show loading and error states, have a 15-second
timeout, and support retry. Superseded requests are cancelled. Results and counts
come from the local Flask API.

## Verification

Run `python -W error -m unittest discover -s tests -v` from the repository root.
The suite includes page routes, static assets, field order, HTML labels, API
integration, and homepage asset hashes. With Node.js installed, `node --check`
can check each file under `static/js/`; Node.js is not a runtime dependency.

Browser checks during frontend development covered search, pagination, empty
results, selected-record prediction, invalid inputs, missing measurements,
ambiguous identifiers, both model classes, and mobile navigation. A deliberate
service outage was followed by a successful retry. Width checks passed at 1440,
768, 390, and 320 pixels. Reduced-motion rules were inspected but not separately
emulated in the browser.

## Screenshots

| Page | Desktop | Mobile |
|---|---|---|
| Home | [Screenshot](preview/homepage-stage2-unchanged.jpg) | [Screenshot](preview/starfield-revised-mobile.jpg) |
| Explore | [Screenshot](preview/explore-desktop.jpg) | [Screenshot](preview/explore-mobile.jpg) |
| Predict | [Screenshot](preview/predict-desktop.jpg) | [Screenshot](preview/predict-mobile.jpg) |
| Model | [Screenshot](preview/model-desktop.jpg) | [Screenshot](preview/model-mobile.jpg) |
| About | [Screenshot](preview/about-desktop.jpg) | [Screenshot](preview/about-mobile.jpg) |

The desktop Predict capture shows K00752.01 (Planet-like, 98.0% class-1 score).
The mobile capture shows K00754.01 (False Positive, 0.0% class-1 score).
