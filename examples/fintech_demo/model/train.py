"""Trains a simple credit-risk model on sample data.

Pure-Python logistic regression, trained by batch gradient descent. No sklearn,
no XGBoost, no pickle.

That is a deliberate choice for a *fixture*. The model is not the subject of
this project — Custos is — and a fixture that needs a scientific-computing
stack to load is a fixture that eventually stops loading. Weights are written
as JSON, which is portable, diffable, and cannot execute code on load the way
an unpickled object can.
"""

from __future__ import annotations

import json
import math
import random
from pathlib import Path

MODEL_PATH = Path(__file__).with_name("credit_model.json")

FEATURES = ["income", "utilisation", "bureau_score", "months_employed"]

# The population the model is trained on. Drift, later, means live traffic
# stops looking like this.
TRAINING_POPULATION = {
    "income": (60000.0, 15000.0),
    "utilisation": (0.35, 0.12),
    "bureau_score": (720.0, 60.0),
    "months_employed": (48.0, 24.0),
}


def sample_applicant(rng: random.Random) -> dict[str, float]:
    return {name: rng.gauss(mu, sigma) for name, (mu, sigma) in TRAINING_POPULATION.items()}


def _true_default_probability(row: dict[str, float]) -> float:
    """The latent relationship the model has to learn.

    Low bureau score, high utilisation and low income raise default risk —
    the directions a credit analyst would expect.
    """
    z = (
        -2.2
        + 2.8 * (row["utilisation"] - 0.35) / 0.12 * 0.35
        - 1.9 * (row["bureau_score"] - 720) / 60 * 0.5
        - 0.9 * (row["income"] - 60000) / 15000 * 0.4
        - 0.4 * (row["months_employed"] - 48) / 24 * 0.3
    )
    return 1 / (1 + math.exp(-z))


def generate_dataset(n: int = 4000, seed: int = 20260904) -> tuple[list[dict], list[int]]:
    rng = random.Random(seed)
    rows, labels = [], []
    for _ in range(n):
        row = sample_applicant(rng)
        rows.append(row)
        labels.append(1 if rng.random() < _true_default_probability(row) else 0)
    return rows, labels


def _standardise(row: dict[str, float]) -> list[float]:
    """Z-score against the training population, so weights are comparable."""
    return [
        (row[name] - TRAINING_POPULATION[name][0]) / TRAINING_POPULATION[name][1]
        for name in FEATURES
    ]


def train(epochs: int = 400, learning_rate: float = 0.35, seed: int = 20260904) -> dict:
    rows, labels = generate_dataset(seed=seed)
    x = [_standardise(row) for row in rows]

    weights = [0.0] * len(FEATURES)
    bias = 0.0
    n = len(x)

    for _ in range(epochs):
        grad_w = [0.0] * len(FEATURES)
        grad_b = 0.0
        for features, label in zip(x, labels, strict=True):
            z = bias + sum(w * f for w, f in zip(weights, features, strict=True))
            error = 1 / (1 + math.exp(-max(-60.0, min(60.0, z)))) - label
            for i, f in enumerate(features):
                grad_w[i] += error * f
            grad_b += error
        weights = [w - learning_rate * g / n for w, g in zip(weights, grad_w, strict=True)]
        bias -= learning_rate * grad_b / n

    accuracy = _accuracy(x, labels, weights, bias)
    return {
        "features": FEATURES,
        "weights": weights,
        "bias": bias,
        "standardisation": TRAINING_POPULATION,
        "training_rows": n,
        "train_accuracy": round(accuracy, 4),
    }


def _accuracy(x, labels, weights, bias) -> float:
    correct = 0
    for features, label in zip(x, labels, strict=True):
        z = bias + sum(w * f for w, f in zip(weights, features, strict=True))
        correct += int((1 / (1 + math.exp(-z)) >= 0.5) == bool(label))
    return correct / len(labels)


def save(model: dict, path: Path = MODEL_PATH) -> Path:
    path.write_text(json.dumps(model, indent=2) + "\n")
    return path


def load(path: Path = MODEL_PATH) -> dict:
    if not path.exists():
        save(train(), path)
    return json.loads(path.read_text())


def predict_default_probability(model: dict, row: dict[str, float]) -> float:
    """Probability this applicant defaults, in [0, 1]."""
    z = model["bias"]
    for name, weight in zip(model["features"], model["weights"], strict=True):
        mu, sigma = model["standardisation"][name]
        z += weight * (row.get(name, mu) - mu) / sigma
    return 1 / (1 + math.exp(-max(-60.0, min(60.0, z))))


if __name__ == "__main__":
    trained = train()
    path = save(trained)
    print(f"trained on {trained['training_rows']} rows")
    print(f"train accuracy: {trained['train_accuracy']:.1%}")
    print(f"saved to {path}")
