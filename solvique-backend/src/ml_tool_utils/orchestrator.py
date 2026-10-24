"""
orchestrator.py
---------------
Main ML pipeline — ties LLM routing, inference, and response generation together.

Flow:
  1. LLM Call 1 — Routes query to the correct model and extracts features
  2. Inference   — Runs the selected ML model(s)
  3. LLM Call 2 — Generates a plain English explanation
"""

import json
import os
import re
import warnings
from datetime import date

warnings.filterwarnings("ignore", category=UserWarning)

from google import genai
from google.genai import types

from src.logging_config import get_logger
from src.ml_tool_utils.registry_loader import load_registry, get_manifest
from src.ml_tool_utils.prompt import (
    build_master_prompt,
    build_master_schema,
    build_response_prompt,
)
from src.ml_tool_utils.inference import run_inference
from config import MODEL as MODEL1

logger = get_logger(__name__)

# ── Gemini client ──────────────────────────────────────────────────────────────
client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
MODEL = MODEL1

MANIFESTS = load_registry()
MASTER_PROMPT = build_master_prompt(MANIFESTS)
MASTER_SCHEMA = build_master_schema(MANIFESTS)

# ── Constants ──────────────────────────────────────────────────────────────────
_DISPLAY_NAMES = {
    "price": "Item price",
    "freight_value": "Freight value",
    "payment_installments": "Payment installments",
    "total_order_value": "Total order value",
    "price_to_freight_ratio": "Price to freight ratio",
    "is_installment": "Is installment",
    "horizon_days": "Forecast horizon",
}

_UNITS = {
    "price": "BRL",
    "freight_value": "BRL",
    "total_order_value": "BRL",
    "horizon_days": "days",
}

_MONTHS = {
    "jan": 1,"january": 1, "feb": 2,"february": 2,"mar": 3,"march": 3,
    "apr": 4,"april": 4,"may": 5,"jun": 6,"june": 6,"jul": 7,"july": 7,
    "aug": 8,"august": 8,"sep": 9,"sept": 9,"september": 9,"oct": 10,
    "october": 10,"nov": 11,"november": 11,"dec": 12,"december": 12,
}


# ── Helpers ────────────────────────────────────────────────────────────────────
def _format_value(feat: str, val) -> str:
    val_str = f"{val:.2f}" if isinstance(val, float) else str(val)
    unit = _UNITS.get(feat, "")
    return f"{val_str} {unit}".strip() if unit else val_str


def _safe_date(year: int, month: int, day: int) -> str | None:
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _extract_target_date(query: str) -> str | None:
    q = query.lower()
    month_names = "|".join(sorted(_MONTHS, key=len, reverse=True))

    patterns = [
        (r"\b(20\d{2})[-/](\d{1,2})[-/](\d{1,2})\b", lambda m: (m[1], m[2], m[3])),
        (r"\b(\d{1,2})[-/](\d{1,2})[-/](20\d{2})\b", lambda m: (m[3], m[2], m[1])),
        (
            rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({month_names})\.?,?\s+(20\d{{2}})\b",
            lambda m: (m[3], _MONTHS[m[2]], m[1]),
        ),
        (
            rf"\b({month_names})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?,?\s+(20\d{{2}})\b",
            lambda m: (m[3], _MONTHS[m[1]], m[2]),
        ),
    ]

    for pattern, extractor in patterns:
        if match := re.search(pattern, q):
            y, mo, d = extractor(match)
            return _safe_date(int(y), int(mo), int(d))
    return None


def _extract_horizon_days(query: str) -> int | None:
    multipliers = {"week": 7, "weeks": 7, "month": 30, "months": 30}
    patterns = [
        r"\bnext\s+(\d{1,4})\s*(day|days|week|weeks|month|months)\b",
        r"\bfor\s+(?:the\s+)?(?:next\s+)?(\d{1,4})\s*(day|days|week|weeks|month|months)\b",
        r"\b(\d{1,4})\s*[- ]?(day|days|week|weeks|month|months)\s+(?:forecast|ahead|prediction)\b",
    ]
    for pattern in patterns:
        if match := re.search(pattern, query.lower()):
            value, unit = int(match.group(1)), match.group(2)
            return value * multipliers.get(unit, 1)
    return None


def _resolve_forecast_request(user_query: str) -> dict:
    target_date = _extract_target_date(user_query)
    horizon_days = _extract_horizon_days(user_query)
    return {
        "target_date": target_date,
        "horizon_days": horizon_days,
        "return_single_date": bool(target_date),
    }


def _predict_explicit_category_examples(user_query: str) -> dict | None:
    """Skip LLM routing for an unambiguous category query with explicit examples."""
    if not re.search(r"\b(categor(?:y|ies)|classif(?:y|ication))\b", user_query, re.I):
        return None

    weights = [float(value) for value in re.findall(
        r"\b(\d+(?:\.\d+)?)\s*(?:g|grams?)\b", user_query, re.I
    )]
    price_matches = re.findall(
        r"(?:\b(\d+(?:\.\d+)?)\s*(?:BRL|reais)\b|\bR\$\s*(\d+(?:\.\d+)?))",
        user_query,
        re.I,
    )
    prices = [float(brl_value or real_value) for brl_value, real_value in price_matches]
    if len(weights) < 2 or len(prices) < 2:
        return None

    manifest = get_manifest("category_classifier")
    instances = []
    for weight, price in zip(weights, prices):
        prediction, feature_sources = run_inference(
            {"final_feature_vector": {"product_weight_g": weight, "price": price}},
            manifest,
            manifest["task"],
        )
        instances.append({"feature_sources": feature_sources, "prediction": prediction})

    feature_table = _build_feature_table(
        instances_data=[
            {"instance_label": f"Item {i + 1}", **item}
            for i, item in enumerate(instances)
        ],
        task=manifest["task"],
    )
    predictions = "; ".join(
        f"Item {i + 1} ({weight:g} g, {price:g} BRL): **{item['prediction']['predicted_class']}**"
        for i, (weight, price, item) in enumerate(zip(weights, prices, instances))
    )
    return {
        "response": f"Predicted product categories: {predictions}.",
        "results": [],
    }


# ── Feature table builders ─────────────────────────────────────────────────────
def _prediction_str(prediction: dict, task: str) -> str:
    if task == "regression":
        v, lo, hi, u = (
            prediction.get(k, "")
            for k in ("predicted_value", "lower_bound", "upper_bound", "units")
        )
        return f"{v} {u} (range: {lo} – {hi} {u})"
    if task == "classification":
        return str(prediction.get("predicted_class", ""))
    if task == "forecasting":
        total, peak, peak_val = (
            prediction.get(k, "") for k in ("total_orders", "peak_date", "peak_value")
        )
        return f"{total} orders, peak {peak} ({peak_val}/day)"
    return str(prediction)


def _feature_rows(
    feature_sources: dict, prediction_str: str, task_str: str
) -> list[str]:
    rows = ["| Feature | Value | Prediction | Task |", "|---|---|---|---|"]
    for i, (feat, info) in enumerate(feature_sources.items()):
        if feat.startswith("_"):
            continue
        display = _DISPLAY_NAMES.get(feat, feat.replace("_", " ").title())
        value_str = _format_value(feat, info.get("value", ""))
        pred_col = prediction_str if i == 0 else ""
        task_col = task_str if i == 0 else ""
        rows.append(f"| {display} | {value_str} | {pred_col} | {task_col} |")
    return rows


def _daily_forecast_rows(daily: list) -> list[str]:
    if not daily:
        return []
    rows = [
        "",
        "**Daily Forecast Breakdown:**",
        "| Date | Predicted Orders | Lower Bound | Upper Bound |",
        "|---|---|---|---|",
    ]
    for row in daily:
        rows.append(
            f"| {row['date']} | {row['yhat']} | {row['yhat_lower']} | {row['yhat_upper']} |"
        )
    return rows


def _build_feature_table(
    feature_sources: dict = None,
    instances_data: list = None,
    prediction: dict = None,
    task: str = None,
) -> str:
    task_str = task.title() if task else ""

    if instances_data:
        blocks = []
        for inst in instances_data:
            pred = inst["prediction"]
            p_str = _prediction_str(pred, task) if task else str(pred)
            rows = [f"( {inst['instance_label']} )"]
            rows += _feature_rows(inst["feature_sources"], p_str, task_str)
            rows += _daily_forecast_rows(pred.get("daily_forecast", []))
            blocks.append("\n".join(rows))
        return "\n\n".join(blocks)

    p_str = _prediction_str(prediction, task) if prediction else ""
    rows = _feature_rows(feature_sources, p_str, task_str)
    rows += _daily_forecast_rows((prediction or {}).get("daily_forecast", []))
    return "\n".join(rows)


# ── LLM callers ────────────────────────────────────────────────────────────────
def _call_llm(prompt: str, schema: dict) -> dict:
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=schema,
            ),
        )
        logger.info(
            "\n=== LLM 1 RAW OUTPUT ===\n%s\n========================\n", response.text
        )
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", response.text.strip())
        return json.loads(cleaned)
    except Exception as e:
        logger.error("LLM 1 CALL FAILED: %s", e)
        raise Exception(f"LLM 1 (routing + extraction) failed: {e}")


def _call_llm_response(user_query: str, feature_table: str) -> str:
    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=build_response_prompt(
                user_query=user_query, feature_table=feature_table
            ),
            config=types.GenerateContentConfig(response_mime_type="text/plain"),
        )
        logger.info(
            "\n=== LLM 2 RAW OUTPUT ===\n%s\n========================\n", response.text
        )
        return response.text.strip()
    except Exception as e:
        logger.error("LLM 2 CALL FAILED: %s", e)
        raise Exception(f"LLM 2 (business language writer) failed: {e}")


# ── Inference helpers ──────────────────────────────────────────────────────────
def _run_item(item: dict, forecast_request: dict) -> dict:
    model_id = item["model_id"]
    manifest = get_manifest(model_id)
    feature_vector = dict(item.get("final_feature_vector") or {})

    if manifest["task"] == "forecasting":
        if forecast_request["horizon_days"]:
            feature_vector["horizon_days"] = forecast_request["horizon_days"]
        if forecast_request["target_date"]:
            feature_vector["_target_date"] = forecast_request["target_date"]
            feature_vector["_return_single_date"] = forecast_request[
                "return_single_date"
            ]

    prediction, feature_sources = run_inference(
        {"final_feature_vector": feature_vector}, manifest, manifest["task"]
    )
    return {
        "model_id": model_id,
        "manifest": manifest,
        "prediction": prediction,
        "feature_sources": feature_sources,
    }


def _patch_single_date_prediction(prediction: dict, target_date: str) -> dict | None:
    """Narrow a multi-day forecast down to one target date row."""
    matched = [
        r for r in prediction.get("daily_forecast", []) if r.get("date") == target_date
    ]
    if not matched:
        return None
    row = matched[0]
    return {
        **prediction,
        "horizon_days": 1,
        "total_orders": row["yhat"],
        "peak_date": row["date"],
        "peak_value": row["yhat"],
        "avg_lower": row["yhat_lower"],
        "avg_upper": row["yhat_upper"],
        "daily_forecast": [row],
    }


# ── Main entry point ───────────────────────────────────────────────────────────
def run(user_query: str) -> dict:
    """Run the full ML inference pipeline and return a response dict."""
    fast_prediction = _predict_explicit_category_examples(user_query)
    if fast_prediction is not None:
        return fast_prediction

    llm_output = _call_llm(
        prompt=f"{MASTER_PROMPT}\n\nUSER QUERY: {user_query}",
        schema=MASTER_SCHEMA,
    )

    if llm_output.get("execution_mode") == "ambiguous":
        return {
            "response": llm_output.get(
                "fallback_question", "Could you clarify what you'd like to predict?"
            ),
            "results": [],
        }

    return _handle(llm_output, user_query)


def _handle(llm_output: dict, user_query: str) -> dict:
    execution_mode = llm_output.get("execution_mode", "single")
    forecast_request = _resolve_forecast_request(user_query)

    results = [
        _run_item(item, forecast_request) for item in llm_output.get("items", [])
    ]
    primary = results[0] if results else None

    # ── Build feature table ────────────────────────────────────────
    if execution_mode == "multi_model":
        feature_table = "\n\n".join(
            _build_feature_table(
                feature_sources=r["feature_sources"],
                prediction=r["prediction"],
                task=r["manifest"]["task"],
            )
            for r in results
        )

    elif execution_mode == "multi_instance":
        feature_table = _build_feature_table(
            instances_data=[
                {
                    "instance_label": f"Scenario {i + 1}",
                    **{k: r[k] for k in ("feature_sources", "prediction")},
                }
                for i, r in enumerate(results)
            ],
            task=primary["manifest"]["task"],
        )

    else:  # single
        prediction = primary["prediction"]
        if (
            primary["manifest"]["task"] == "forecasting"
            and forecast_request["return_single_date"]
            and isinstance(prediction, dict)
        ):
            prediction = (
                _patch_single_date_prediction(
                    prediction, forecast_request["target_date"]
                )
                or prediction
            )

        feature_table = _build_feature_table(
            feature_sources=primary["feature_sources"],
            prediction=prediction,
            task=primary["manifest"]["task"],
        )

    logger.info(
        "\n=== FEATURE TABLE SENT TO LLM 2 ===\n%s\n====================================\n",
        feature_table,
    )

    # ── Build explanation ──────────────────────────────────────────
    explanation = _get_explanation(primary, forecast_request, user_query, feature_table)
    logger.info("ML Tool explanation: %s", explanation)

    visualization_rows = []
    if primary and primary["manifest"]["task"] == "forecasting":
        visualization_rows = (primary["prediction"] or {}).get(
            "daily_forecast", []
        ) or []

    return {
        # Keep the evidence table in the tool response as well as the prompt.
        # The chat renderer extracts this markdown table and displays it below
        # the concise natural-language explanation.
        "response": f"{explanation}\n\n### Feature Table\n{feature_table}",
        "results": visualization_rows,
    }


def _get_explanation(
    primary: dict, forecast_request: dict, user_query: str, feature_table: str
) -> str:
    """Return a direct string for simple forecasts, or call LLM 2 otherwise."""
    if not primary:
        return _call_llm_response(user_query, feature_table)

    prediction = primary["prediction"]
    is_single_date_forecast = (
        primary["manifest"]["task"] == "forecasting"
        and forecast_request["return_single_date"]
        and isinstance(prediction, dict)
    )

    if is_single_date_forecast:
        daily = prediction.get("daily_forecast", [])
        if len(daily) == 1:
            row = daily[0]
            units = prediction.get("units", "orders")
            return (
                f"For {row['date']}, the forecasted order value is {row['yhat']} {units}. "
                f"The estimated range is {row['yhat_lower']} to {row['yhat_upper']} {units}."
            )
        if prediction.get("error"):
            return prediction["error"]

    return _call_llm_response(user_query, feature_table)
