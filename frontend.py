"""Presentation-only routes and documented feature descriptions. No ML changes."""
from flask import Blueprint, render_template

frontend = Blueprint("frontend", __name__)
FEATURE_INFO = [
    ("koi_period", "Orbital Period", "days", "Time taken to complete one orbit.", True),
    ("koi_duration", "Transit Duration", "hours", "How long the transit signal lasts.", True),
    ("koi_depth", "Transit Depth", "ppm", "The decrease in measured starlight.", False),
    ("koi_prad", "Planet Radius", "Earth radii", "Estimated radius relative to Earth.", True),
    ("koi_teq", "Equilibrium Temperature", "K", "Estimated temperature from incoming starlight.", True),
    ("koi_insol", "Insolation Flux", "Earth units", "Received stellar energy relative to Earth.", False),
    ("koi_steff", "Stellar Temperature", "K", "Effective temperature of the host star.", True),
    ("koi_srad", "Stellar Radius", "Solar radii", "Host-star radius relative to the Sun.", True),
    ("koi_impact", "Impact Parameter", "dimensionless", "Transit path offset in stellar-radius units.", False),
    ("koi_model_snr", "Transit Signal-to-Noise", "ratio", "Strength of the transit signal relative to noise.", False),
]
VALIDATION_RESULTS = [
    {"name": "Logistic Regression", "accuracy": .7600, "f1": .7720, "auc": .8218},
    {"name": "Random Forest", "accuracy": .8358, "f1": .8262, "auc": .9231},
    {"name": "Artificial Neural Network", "accuracy": .8178, "f1": .8121, "auc": .9005},
]


@frontend.get("/explore")
def explore():
    return render_template("explore.html", active_page="explore")


@frontend.get("/predict")
def predict():
    return render_template("predict.html", active_page="predict", feature_info=FEATURE_INFO)


@frontend.get("/model")
def model():
    return render_template("model.html", active_page="model", feature_info=FEATURE_INFO,
                           validation_results=VALIDATION_RESULTS)


@frontend.get("/about")
def about():
    return render_template("about.html", active_page="about")
