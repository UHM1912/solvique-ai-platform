"""
pipeline.py
-----------
Preprocessing pipeline for single inference.
Handles feature imputation from training statistics and returns
a DataFrame ready for model prediction.

Adapted from ML_TOOL/preprocessing/pipeline.py for Solvique backend integration.
"""

import json
import pandas as pd
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent


def run_pipeline(payload: dict, manifest: dict):
    """
    Preprocessing pipeline for single inference.

    Flow:
        LLM payload (top-k extracted, rest null)
            → imputer fills all nulls from training statistics
            → validation ensures no nulls remain
            → DataFrame returned in correct col_order

    Returns:
        df             : preprocessed single-row DataFrame in col_order
        feature_sources: {feat: {"value": ..., "source": "LLM" | "IMPUTED"}}
    """

    schema = manifest["feature_schema"]
    col_order = schema["col_order"]
    artifacts = manifest["artifacts"]
    model_id = manifest["model_id"]

    # ── Step 1: Start with LLM extracted feature vector ───────────
    raw_vector = payload["final_feature_vector"]

    # Binary features where 0 is a valid value — do not treat as null
    BINARY_FEATURES = {"is_installment"}

    row = {}
    for feat, val in raw_vector.items():
        if feat in BINARY_FEATURES:
            row[feat] = val  # 0 is valid for binary
        else:
            row[feat] = val if val not in (0, None) else None  # 0 → null

    feature_sources = {}

    # ── Step 2: Load imputer stats ────────────────────────────────
    imputer_path = PROJECT_ROOT / artifacts["imputer_stats"]
    with open(imputer_path) as f:
        imputer_stats = json.load(f)

    # ── Step 3: Fill nulls + record source per feature ────────────
    for feat in col_order:
        if row.get(feat) is not None:
            feature_sources[feat] = {"value": row[feat], "source": "LLM"}
        else:
            if feat in imputer_stats:
                row[feat] = imputer_stats[feat]
                feature_sources[feat] = {"value": row[feat], "source": "IMPUTED"}

    # ── Step 4: Validate — no nulls allowed past this point ───────
    missing = [f for f in col_order if row.get(f) is None]
    if missing:
        raise ValueError(
            f"[Pipeline] Features still null after imputer fill for "
            f"model '{model_id}': {missing}. "
            f"Check imputer_stats.json — these keys may be missing."
        )

    # ── Step 5: Assemble DataFrame in correct col_order ───────────
    df = pd.DataFrame([row])[col_order]

    return df, feature_sources
