"""
DataFrame Visualizer module.
Provides deterministic, on-demand visualization for SQL and ML query results.
Eliminates unsafe agent execution paths and excessive latency.
"""

from typing import Any
import json
import pandas as pd

from src.logging_config import get_logger
from src.visualization_tool.chart_engine import (
    build_figure_spec,
    profile_dataframe,
)

logger = get_logger(__name__)


def run_dataframe_visualizer(
    *,
    source_tool: str,
    df: pd.DataFrame,
    requested_chart_type: str | None = None,
) -> dict[str, Any]:
    """
    Generate on-demand, validated Plotly chart specifications.

    Args:
        source_tool: Tool identifier (sql_tool, ml_tool).
        df: Pandas DataFrame containing query results.
        requested_chart_type: Specific chart type selected by the user (bar, line, etc.).

    Returns:
        Structured visualization payload matching VisualizeResponse.
    """
    logger.info(
        "Deterministic visualization requested: source_tool=%s, rows=%s, columns=%s, requested_type=%s",
        source_tool,
        len(df) if df is not None else 0,
        len(df.columns) if df is not None else 0,
        requested_chart_type,
    )

    if df is None or df.empty:
        return {
            "summary": "The dataset contains no records to visualize.",
            "chart_specs": [],
            "visualization_options": [],
            "chart_type_options": [],
            "visualization_mode": "chart",
            "error": "No data rows available for visualization.",
        }

    profile = profile_dataframe(df)
    if not profile.get("supported"):
        reason = profile.get("reason", "Dataset not suitable for visual representation.")
        logger.info("Visualization not supported: %s", reason)
        return {
            "summary": reason,
            "chart_specs": [],
            "visualization_options": [],
            "chart_type_options": [],
            "visualization_mode": "chart",
            "error": reason,
        }

    try:
        fig_dict, resolved_type, title = build_figure_spec(
            df, source_tool=source_tool, requested_chart_type=requested_chart_type
        )
        figure_json = json.dumps(fig_dict)

        primary_spec = {
            "title": title,
            "chart_type": resolved_type,
            "figure_json": figure_json,
        }

        # Populate chart_spec only for the generated option; others remain on-demand
        options = []
        for opt in profile.get("options", []):
            opt_copy = dict(opt)
            if opt_copy.get("chart_type") == resolved_type:
                opt_copy["chart_spec"] = primary_spec
            options.append(opt_copy)

        return {
            "summary": f"{title} generated successfully.",
            "chart_specs": [primary_spec],
            "visualization_options": [],
            "chart_type_options": options,
            "visualization_mode": "chart",
        }

    except Exception as exc:
        logger.error("Chart generation error: %s", exc, exc_info=True)
        return {
            "summary": "Failed to construct chart for this dataset.",
            "chart_specs": [],
            "visualization_options": [],
            "chart_type_options": profile.get("options", []),
            "visualization_mode": "chart",
            "error": str(exc),
        }
