"""Training, persistence and scoring for the IPF demand model.

The model is a gradient-boosted regressor over the windowed features in
`dataset.py`. It is always scored against the naive baseline a shop owner would
use by hand — "it will sell about what it sold last fortnight" — and the
comparison is reported honestly, including when the model fails to beat it.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error, r2_score

from ..config import get_settings
from .dataset import HORIZON_DAYS, LOOKBACK_DAYS, feature_names

DEFAULT_MODEL_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "models"
)


def model_dir() -> str:
    """Resolved at call time so the test suite can redirect it."""
    return get_settings().ipf_model_dir or DEFAULT_MODEL_DIR


def model_path() -> str:
    return os.path.join(model_dir(), "ipf_model.joblib")


def metadata_path() -> str:
    return os.path.join(model_dir(), "ipf_model.json")

# Minimum rows before training is worth attempting at all.
MIN_TRAINING_ROWS = 200
TEST_FRACTION = 0.2


@dataclass
class ModelMetadata:
    trained_at: str
    horizon_days: int
    lookback_days: int
    n_samples: int
    n_train: int
    n_test: int
    mae: float
    baseline_mae: float
    improvement_percent: float
    r2: float
    beats_baseline: bool
    feature_count: int
    categories: list[str]
    algorithm: str = "HistGradientBoostingRegressor"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class NotEnoughData(RuntimeError):
    """Raised when the history is too short or too sparse to train on."""


def _time_ordered_split(anchors: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Split by anchor date, never at random.

    Every row for a given product overlaps its neighbours in time, so a random
    split would leak the future into training and produce a flattering score
    that collapses in real use.
    """
    unique = np.unique(anchors)
    if unique.size < 3:
        raise NotEnoughData("The history does not span enough distinct days to validate a model")
    cutoff_index = max(1, int(round(unique.size * (1 - TEST_FRACTION))))
    cutoff = unique[min(cutoff_index, unique.size - 1)]
    return anchors < cutoff, anchors >= cutoff


def train_model(
    features: np.ndarray,
    targets: np.ndarray,
    baselines: np.ndarray,
    anchors: np.ndarray,
    categories: list[str],
) -> tuple[HistGradientBoostingRegressor, ModelMetadata]:
    if features.shape[0] < MIN_TRAINING_ROWS:
        raise NotEnoughData(
            f"Only {features.shape[0]} training windows available; at least "
            f"{MIN_TRAINING_ROWS} are needed. Record more sales first."
        )

    train_mask, test_mask = _time_ordered_split(anchors)
    if train_mask.sum() == 0 or test_mask.sum() == 0:
        raise NotEnoughData("Not enough distinct trading days to hold out a test period")

    estimator = HistGradientBoostingRegressor(
        loss="absolute_error",  # robust to the occasional bulk-buy spike
        max_iter=300,
        learning_rate=0.06,
        max_depth=5,
        min_samples_leaf=15,
        l2_regularization=1.0,
        early_stopping=True,
        validation_fraction=0.15,
        random_state=20261002,
    )
    estimator.fit(features[train_mask], targets[train_mask])

    predictions = np.clip(estimator.predict(features[test_mask]), 0, None)
    actual = targets[test_mask]
    mae = float(mean_absolute_error(actual, predictions))
    baseline_mae = float(mean_absolute_error(actual, np.clip(baselines[test_mask], 0, None)))
    improvement = ((baseline_mae - mae) / baseline_mae * 100) if baseline_mae > 0 else 0.0

    metadata = ModelMetadata(
        trained_at=datetime.now(timezone.utc).isoformat(),
        horizon_days=HORIZON_DAYS,
        lookback_days=LOOKBACK_DAYS,
        n_samples=int(features.shape[0]),
        n_train=int(train_mask.sum()),
        n_test=int(test_mask.sum()),
        mae=round(mae, 3),
        baseline_mae=round(baseline_mae, 3),
        improvement_percent=round(improvement, 2),
        r2=round(float(r2_score(actual, predictions)), 3),
        beats_baseline=mae < baseline_mae,
        feature_count=int(features.shape[1]),
        categories=categories,
    )
    return estimator, metadata


def save_model(estimator: Any, metadata: ModelMetadata) -> None:
    os.makedirs(model_dir(), exist_ok=True)
    joblib.dump({"estimator": estimator, "categories": metadata.categories}, model_path())
    with open(metadata_path(), "w", encoding="utf-8") as handle:
        json.dump(metadata.to_dict(), handle, indent=2)


def load_model() -> tuple[Any, list[str], dict[str, Any]] | None:
    """Return (estimator, categories, metadata), or None when never trained."""
    artifact, meta = model_path(), metadata_path()
    if not (os.path.exists(artifact) and os.path.exists(meta)):
        return None
    try:
        bundle = joblib.load(artifact)
        with open(meta, encoding="utf-8") as handle:
            metadata = json.load(handle)
    except Exception:  # pragma: no cover - corrupt or version-mismatched artifact
        return None
    return bundle["estimator"], bundle.get("categories", []), metadata


def predict(estimator: Any, features: np.ndarray) -> np.ndarray:
    if features.size == 0:
        return np.empty(0)
    # Demand cannot be negative, whatever the regressor extrapolates.
    return np.clip(estimator.predict(features), 0, None)


def expected_feature_count(categories: list[str]) -> int:
    return len(feature_names(categories))
