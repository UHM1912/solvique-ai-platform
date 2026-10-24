"""
inference.py
------------
Model loading and prediction for classification, regression, and forecasting.

Adapted from ML_TOOL/inference/inference.py for Solvique backend integration.
"""

import joblib
import pickle
import numpy as np
import pandas as pd
from datetime import timedelta
from pathlib import Path
from src.logging_config import get_logger

from src.ml_tool_utils.pipeline import run_pipeline

logger = get_logger(__name__)

PROJECT_ROOT = Path(__file__).parent


def run_inference(payload: dict, manifest: dict, task: str):
    """
    Runs a single inference for any task.
    Returns (prediction, feature_sources).
    """
    if task == "forecasting":
        final_features = payload["final_feature_vector"]
        requested_horizon = final_features.get("horizon_days")
        target_date = final_features.get("_target_date")
        prediction = _run_forecaster(payload, manifest)
        horizon = final_features.get("horizon_days")
        source = "QUERY" if requested_horizon else "IMPUTED"
        if target_date and not requested_horizon:
            source = "DERIVED_FROM_TARGET_DATE"

        feature_sources = {
            "horizon_days": {
                "value": int(horizon) if horizon else 30,
                "source": source,
            }
        }
        return prediction, feature_sources

    df, feature_sources = run_pipeline(payload, manifest)

    if task == "classification":
        prediction = _run_classifier(df, manifest)
    elif task == "regression":
        prediction = _run_regressor(df, manifest)
    else:
        raise ValueError(f"[_run_single] Unknown task: '{task}'")

    return prediction, feature_sources


# ─────────────────────────────────────────────────────────────────
# CLASSIFICATION
# ─────────────────────────────────────────────────────────────────


def _run_classifier(df: pd.DataFrame, manifest: dict) -> dict:
    model = joblib.load(PROJECT_ROOT / manifest["pkl_path"])
    label_encoder = joblib.load(PROJECT_ROOT / manifest["artifacts"]["label_encoder"])

    # This is a single-row inference. Avoid spawning a large worker pool for
    # every item in a multi-instance request.
    if hasattr(model, "n_jobs"):
        model.n_jobs = 1

    X = df.to_numpy()
    proba = model.predict_proba(X)[0]
    pred_index = int(np.argmax(proba))

    predicted_class = label_encoder.inverse_transform([pred_index])[0]

    class_names = label_encoder.classes_.tolist()
    probabilities = {cls: round(float(p), 4) for cls, p in zip(class_names, proba)}

    return {
        "predicted_class": predicted_class,
        "probabilities": probabilities,
    }


# ─────────────────────────────────────────────────────────────────
# REGRESSION
# ─────────────────────────────────────────────────────────────────


def _run_regressor(df: pd.DataFrame, manifest: dict) -> dict:
    output = manifest["output_config"]
    round_to = output.get("round_to", 2)

    model = joblib.load(PROJECT_ROOT / manifest["pkl_path"])

    X = df.to_numpy()
    prediction = round(float(model.predict(X)[0]), round_to)

    tree_predictions = [tree.predict(X)[0] for tree in model.estimators_]
    lower = round(float(np.percentile(tree_predictions, 10)), round_to)
    upper = round(float(np.percentile(tree_predictions, 90)), round_to)

    return {
        "predicted_value": prediction,
        "lower_bound": lower,
        "upper_bound": upper,
        "units": output.get("units", "BRL"),
    }


# ─────────────────────────────────────────────────────────────────
# FORECASTING
# ─────────────────────────────────────────────────────────────────


def _run_forecaster(payload: dict, manifest: dict) -> dict:
    output = manifest["output_config"]
    final_features = payload["final_feature_vector"]
    horizon_days = int(final_features.get("horizon_days") or 30)
    target_date = final_features.get("_target_date")

    if not final_features.get("horizon_days"):
        logger.info("[_run_forecaster] horizon_days not in payload — defaulting to 30")

    prophet_path = PROJECT_ROOT / manifest["artifacts"]["prophet_model"]
    with open(prophet_path, "rb") as f:
        model = pickle.load(f)

    forecast_start = pd.to_datetime(model.history["ds"]).max().date() + timedelta(
        days=1
    )
    if target_date:
        parsed_target = pd.to_datetime(target_date).date()
        required_horizon = (parsed_target - forecast_start).days + 1

        if required_horizon <= 0:
            return {
                "horizon_days": 0,
                "total_orders": 0,
                "peak_date": None,
                "peak_value": 0,
                "avg_lower": 0,
                "avg_upper": 0,
                "daily_forecast": [],
                "units": output.get("units", "order count per day"),
                "error": (
                    f"{target_date} is before the forecast window. "
                    f"The model can forecast from {forecast_start.isoformat()} onward."
                ),
            }

        if required_horizon > horizon_days:
            logger.info(
                "[_run_forecaster] extending horizon_days from %s to %s to include target date %s",
                horizon_days,
                required_horizon,
                target_date,
            )
            horizon_days = required_horizon

    final_features["horizon_days"] = horizon_days

    future = model.make_future_dataframe(periods=horizon_days, freq="D")
    forecast = model.predict(future)

    future_fc = (
        forecast[["ds", "yhat", "yhat_lower", "yhat_upper"]].tail(horizon_days).copy()
    )
    future_fc.columns = ["date", "yhat", "yhat_lower", "yhat_upper"]

    future_fc["yhat"] = future_fc["yhat"].clip(lower=0).round(0).astype(int)
    future_fc["yhat_lower"] = future_fc["yhat_lower"].clip(lower=0).round(0).astype(int)
    future_fc["yhat_upper"] = future_fc["yhat_upper"].clip(lower=0).round(0).astype(int)

    total_orders = int(future_fc["yhat"].sum())
    peak_row = future_fc.loc[future_fc["yhat"].idxmax()]
    peak_date = str(peak_row["date"].date())
    peak_value = int(peak_row["yhat"])
    avg_lower = int(future_fc["yhat_lower"].mean())
    avg_upper = int(future_fc["yhat_upper"].mean())

    daily_forecast = [
        {
            "date": str(row["date"].date()),
            "yhat": int(row["yhat"]),
            "yhat_lower": int(row["yhat_lower"]),
            "yhat_upper": int(row["yhat_upper"]),
        }
        for _, row in future_fc.iterrows()
    ]

    return {
        "horizon_days": horizon_days,
        "total_orders": total_orders,
        "peak_date": peak_date,
        "peak_value": peak_value,
        "avg_lower": avg_lower,
        "avg_upper": avg_upper,
        "daily_forecast": daily_forecast,
        "units": output.get("units", "order count per day"),
    }
