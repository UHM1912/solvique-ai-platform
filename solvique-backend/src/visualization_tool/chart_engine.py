"""
Deterministic, secure Plotly chart profiling and specification builder for Solvique.
Replaces the unsafe create_pandas_dataframe_agent with deterministic, zero-latency
chart generation.
"""

import json
from typing import Any
import pandas as pd

# Palette tailored for Solvique clean modern analytics
PRIMARY_COLOR = "#0D9488"  # Solvique Teal brand tone
COLOR_PALETTE = [
    "#0D9488",  # Solvique Teal
    "#0284C7",  # Sky Blue
    "#6366F1",  # Indigo
    "#F59E0B",  # Amber
    "#10B981",  # Emerald
    "#EC4899",  # Pink
    "#8B5CF6",  # Violet
    "#14B8A6",  # Cyan
]

BASE_LAYOUT = {
    "template": "plotly_white",
    "font": {"family": "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif", "size": 12},
    "margin": {"l": 55, "r": 25, "t": 65, "b": 60},
    "hoverlabel": {"font": {"family": "Inter, sans-serif"}, "namelength": -1},
}


def _clean_column_title(col_name: str) -> str:
    """Format column names into human-readable labels."""
    return col_name.replace("_", " ").title()


def is_forecast_df(df: pd.DataFrame) -> bool:
    """Check if DataFrame contains Prophet forecast fields."""
    return {"date", "yhat", "yhat_lower", "yhat_upper"}.issubset(df.columns)


def profile_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    """
    Profile DataFrame columns to detect suitable chart types without generating
    full chart specifications.
    """
    if df is None or df.empty:
        return {
            "supported": False,
            "reason": "Dataset is empty.",
            "options": [],
            "default_type": None,
        }

    # Case 1: Prophet Forecast DataFrame
    if is_forecast_df(df):
        options = [
            {
                "id": "chart_type_line",
                "label": "Trend Line",
                "description": "Trajectory with confidence bounds.",
                "chart_type": "line",
                "is_custom": False,
                "chart_spec": None,
            },
            {
                "id": "chart_type_bar",
                "label": "Daily Bar",
                "description": "Compare predicted values date by date.",
                "chart_type": "bar",
                "is_custom": False,
                "chart_spec": None,
            },
            {
                "id": "chart_type_area",
                "label": "Volume Area",
                "description": "Filled area showing cumulative forecast volume.",
                "chart_type": "area",
                "is_custom": False,
                "chart_spec": None,
            },
        ]
        return {
            "supported": True,
            "data_pattern": "forecast",
            "options": options,
            "default_type": "line",
            "date_col": "date",
            "numeric_cols": ["yhat"],
            "category_cols": [],
        }

    # General tabular analysis
    numeric_cols = []
    datetime_cols = []
    category_cols = []
    id_cols = []

    for col in df.columns:
        col_str = str(col).lower()
        if col_str.endswith("_id") and df[col].nunique() > len(df) * 0.7:
            id_cols.append(col)
            continue

        # Check numeric
        if pd.api.types.is_numeric_dtype(df[col]):
            numeric_cols.append(col)
            continue

        # Check datetime
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            datetime_cols.append(col)
            continue

        sample = df[col].dropna().head(20)
        if not sample.empty:
            # Check if strings are parseable as dates
            date_match_rate = pd.to_datetime(sample, errors="coerce", format="mixed").notna().mean()
            if date_match_rate >= 0.8:
                datetime_cols.append(col)
                continue

            # Check if strings can be coerced to numeric (e.g. string numbers)
            num_match_rate = pd.to_numeric(sample, errors="coerce").notna().mean()
            if num_match_rate >= 0.8:
                numeric_cols.append(col)
                continue

        category_cols.append(col)

    if not numeric_cols:
        return {
            "supported": False,
            "reason": "No numeric metrics found in dataset to plot.",
            "options": [],
            "default_type": None,
        }

    options = []
    default_type = "bar"

    # Pattern A: Time series (Date + Numeric)
    if datetime_cols:
        date_col = datetime_cols[0]
        metric_name = _clean_column_title(numeric_cols[0])
        options.append({
            "id": "chart_type_line",
            "label": "Line Chart",
            "description": f"Track {metric_name} trends over time.",
            "chart_type": "line",
            "is_custom": False,
            "chart_spec": None,
        })
        options.append({
            "id": "chart_type_bar",
            "label": "Bar Chart",
            "description": f"Compare {metric_name} across time intervals.",
            "chart_type": "bar",
            "is_custom": False,
            "chart_spec": None,
        })
        options.append({
            "id": "chart_type_area",
            "label": "Area Chart",
            "description": f"Volume progression of {metric_name}.",
            "chart_type": "area",
            "is_custom": False,
            "chart_spec": None,
        })
        default_type = "line" if len(df) > 7 else "bar"
        pattern = "time_series"

    # Pattern B: Categorical dimension + Numeric
    elif category_cols:
        cat_col = category_cols[0]
        metric_name = _clean_column_title(numeric_cols[0])
        dim_name = _clean_column_title(cat_col)
        options.append({
            "id": "chart_type_bar",
            "label": "Bar Chart",
            "description": f"Compare {metric_name} by {dim_name}.",
            "chart_type": "bar",
            "is_custom": False,
            "chart_spec": None,
        })
        # Pie chart only if small number of distinct categories
        unique_count = df[cat_col].nunique()
        if 2 <= unique_count <= 8:
            options.append({
                "id": "chart_type_pie",
                "label": "Pie Chart",
                "description": f"Percentage distribution of {metric_name}.",
                "chart_type": "pie",
                "is_custom": False,
                "chart_spec": None,
            })
        if len(numeric_cols) >= 2:
            options.append({
                "id": "chart_type_scatter",
                "label": "Scatter Plot",
                "description": f"Relationship between {_clean_column_title(numeric_cols[0])} and {_clean_column_title(numeric_cols[1])}.",
                "chart_type": "scatter",
                "is_custom": False,
                "chart_spec": None,
            })
        if len(df) > 4:
            options.append({
                "id": "chart_type_line",
                "label": "Line Progression",
                "description": f"Ranked values of {metric_name}.",
                "chart_type": "line",
                "is_custom": False,
                "chart_spec": None,
            })
        default_type = "bar"
        pattern = "categorical"

    # Pattern C: Two numeric columns (Scatter relationship)
    elif len(numeric_cols) >= 2:
        col1, col2 = numeric_cols[0], numeric_cols[1]
        options.append({
            "id": "chart_type_scatter",
            "label": "Scatter Plot",
            "description": f"Relationship between {_clean_column_title(col1)} and {_clean_column_title(col2)}.",
            "chart_type": "scatter",
            "is_custom": False,
            "chart_spec": None,
        })
        options.append({
            "id": "chart_type_bar",
            "label": "Bar Chart",
            "description": f"Compare {_clean_column_title(col1)} values.",
            "chart_type": "bar",
            "is_custom": False,
            "chart_spec": None,
        })
        default_type = "scatter"
        pattern = "numeric_relationship"

    # Pattern D: Single numeric column
    else:
        options.append({
            "id": "chart_type_bar",
            "label": "Bar Chart",
            "description": f"Distribution of {_clean_column_title(numeric_cols[0])}.",
            "chart_type": "bar",
            "is_custom": False,
            "chart_spec": None,
        })
        default_type = "bar"
        pattern = "single_metric"

    return {
        "supported": True,
        "data_pattern": pattern,
        "options": options,
        "default_type": default_type,
        "date_col": datetime_cols[0] if datetime_cols else None,
        "numeric_cols": numeric_cols,
        "category_cols": category_cols,
    }


def _make_forecast_figure(dates: list[str], yhat: list[float], lower: list[float], upper: list[float], chart_type: str = "line") -> dict[str, Any]:
    """Generate deterministic Plotly figure for Prophet forecasts with confidence bands."""
    layout = {
        **BASE_LAYOUT,
        "title": {"text": "Predicted Order Forecast"},
        "xaxis": {"title": {"text": "Date"}, "type": "category"},
        "yaxis": {"title": {"text": "Predicted Orders"}, "rangemode": "tozero"},
    }

    if chart_type == "bar":
        return {
            "data": [
                {
                    "x": dates,
                    "y": yhat,
                    "type": "bar",
                    "marker": {"color": PRIMARY_COLOR},
                    "name": "Predicted Orders",
                }
            ],
            "layout": {**layout, "title": {"text": "Daily Order Forecast Comparison"}},
        }

    if chart_type == "area":
        return {
            "data": [
                {
                    "x": dates,
                    "y": yhat,
                    "type": "scatter",
                    "mode": "lines",
                    "fill": "tozeroy",
                    "line": {"color": PRIMARY_COLOR, "width": 3},
                    "name": "Predicted Orders",
                }
            ],
            "layout": {**layout, "title": {"text": "Cumulative Forecast Volume"}},
        }

    # Default: Line with confidence interval bands
    return {
        "data": [
            {
                "x": dates,
                "y": upper,
                "type": "scatter",
                "mode": "lines",
                "line": {"width": 0},
                "showlegend": False,
                "hoverinfo": "skip",
                "name": "Upper Bound",
            },
            {
                "x": dates,
                "y": lower,
                "type": "scatter",
                "mode": "lines",
                "line": {"width": 0},
                "fill": "tonexty",
                "fillcolor": "rgba(0, 105, 92, 0.18)",
                "showlegend": False,
                "hoverinfo": "skip",
                "name": "Lower Bound",
            },
            {
                "x": dates,
                "y": yhat,
                "type": "scatter",
                "mode": "lines+markers",
                "line": {"color": PRIMARY_COLOR, "width": 3},
                "marker": {"size": 6},
                "name": "Predicted Orders",
            },
        ],
        "layout": {
            **layout,
            "title": {"text": f"{len(dates)}-Day Order Forecast with Confidence Range"},
            "hovermode": "x unified",
            "legend": {"orientation": "h", "y": 1.12, "x": 0.5, "xanchor": "center"},
        },
    }


def build_figure_spec(df: pd.DataFrame, source_tool: str, requested_chart_type: str | None = None) -> tuple[dict[str, Any], str, str]:
    """
    Build a single validated Plotly figure specification for the requested chart type.
    Returns (figure_dict, resolved_chart_type, title).
    """
    profile = profile_dataframe(df)
    if not profile["supported"]:
        raise ValueError(profile["reason"])

    target_type = requested_chart_type or profile["default_type"]

    # 1. Forecast data
    if profile.get("data_pattern") == "forecast":
        clean_df = df[["date", "yhat", "yhat_lower", "yhat_upper"]].copy()
        clean_df["date"] = clean_df["date"].astype(str)
        dates = clean_df["date"].tolist()
        yhat = [round(float(v), 2) for v in clean_df["yhat"]]
        lower = [round(float(v), 2) for v in clean_df["yhat_lower"]]
        upper = [round(float(v), 2) for v in clean_df["yhat_upper"]]

        fig = _make_forecast_figure(dates, yhat, lower, upper, chart_type=target_type)
        title = fig["layout"]["title"]["text"]
        return fig, target_type, title

    # 2. General Tabular Data
    date_col = profile.get("date_col")
    numeric_cols = profile.get("numeric_cols") or []
    category_cols = profile.get("category_cols") or []

    # Sort if date column exists
    work_df = df.copy()
    if date_col:
        work_df[date_col] = work_df[date_col].astype(str)

    metric_col = numeric_cols[0]
    metric_title = _clean_column_title(metric_col)

    # 2A. Pie Chart
    if target_type == "pie" and category_cols:
        cat_col = category_cols[0]
        labels = work_df[cat_col].astype(str).tolist()
        values = pd.to_numeric(work_df[metric_col], errors="coerce").fillna(0).tolist()
        title = f"{metric_title} Breakdown by {_clean_column_title(cat_col)}"

        fig = {
            "data": [
                {
                    "labels": labels,
                    "values": values,
                    "type": "pie",
                    "hole": 0.35,
                    "marker": {"colors": COLOR_PALETTE[:len(labels)]},
                    "textinfo": "label+percent",
                    "hoverinfo": "label+value+percent",
                }
            ],
            "layout": {
                **BASE_LAYOUT,
                "title": {"text": title},
            },
        }
        return fig, "pie", title

    # 2B. Scatter Plot
    if target_type == "scatter":
        y_col = numeric_cols[1] if len(numeric_cols) >= 2 else metric_col
        y_vals = pd.to_numeric(work_df[y_col], errors="coerce").tolist()

        if len(numeric_cols) >= 2:
            x_col = numeric_cols[0]
            x_vals = pd.to_numeric(work_df[x_col], errors="coerce").tolist()
            x_title = _clean_column_title(x_col)
            title = f"{_clean_column_title(y_col)} vs. {x_title}"
            hover_text = (
                work_df[category_cols[0]].astype(str).tolist() if category_cols else None
            )
            x_axis = {"title": {"text": x_title}}
        elif category_cols:
            x_col = category_cols[0]
            x_vals = work_df[x_col].astype(str).tolist()
            x_title = _clean_column_title(x_col)
            title = f"{metric_title} by {x_title}"
            hover_text = None
            x_axis = {"title": {"text": x_title}, "type": "category", "tickangle": -45}
        else:
            x_vals = list(range(1, len(work_df) + 1))
            x_title = "Row"
            title = f"{metric_title} by {x_title}"
            hover_text = None
            x_axis = {"title": {"text": x_title}}

        trace = {
            "x": x_vals,
            "y": y_vals,
            "mode": "markers",
            "type": "scatter",
            "marker": {"size": 8, "color": PRIMARY_COLOR, "opacity": 0.8},
            "name": metric_title,
            "hovertemplate": "%{x}<br>%{y}<extra></extra>",
        }
        if hover_text is not None:
            trace["text"] = hover_text

        fig = {
            "data": [trace],
            "layout": {
                **BASE_LAYOUT,
                "title": {"text": title},
                "xaxis": x_axis,
                "yaxis": {"title": {"text": _clean_column_title(y_col)}},
            },
        }
        return fig, "scatter", title

    # 2C. Line Chart (Time-series or Ordered)
    x_axis_col = date_col or (category_cols[0] if category_cols else None)
    if x_axis_col:
        x_vals = work_df[x_axis_col].astype(str).tolist()
    else:
        x_vals = list(range(1, len(work_df) + 1))

    if target_type in ("line", "area"):
        y_vals = pd.to_numeric(work_df[metric_col], errors="coerce").fillna(0).tolist()
        x_title = _clean_column_title(x_axis_col) if x_axis_col else "Index"
        title = f"{metric_title} Over {x_title}"

        trace: dict[str, Any] = {
            "x": x_vals,
            "y": y_vals,
            "type": "scatter",
            "mode": "lines+markers",
            "line": {"color": PRIMARY_COLOR, "width": 2.5},
            "marker": {"size": 6},
            "name": metric_title,
        }
        if target_type == "area":
            trace["fill"] = "tozeroy"
            title = f"{metric_title} Cumulative Volume"

        fig = {
            "data": [trace],
            "layout": {
                **BASE_LAYOUT,
                "title": {"text": title},
                "xaxis": {"title": {"text": x_title}, "type": "category"},
                "yaxis": {"title": {"text": metric_title}, "rangemode": "tozero"},
            },
        }
        return fig, target_type, title

    # 2D. Default Bar Chart
    # Support multi-metric grouping if multiple numeric columns exist and len(df) is small
    x_title = _clean_column_title(x_axis_col) if x_axis_col else "Categories"
    y_vals = pd.to_numeric(work_df[metric_col], errors="coerce").fillna(0).tolist()
    title = f"{metric_title} by {x_title}"

    fig = {
        "data": [
            {
                "x": x_vals,
                "y": y_vals,
                "type": "bar",
                "marker": {"color": PRIMARY_COLOR},
                "name": metric_title,
            }
        ],
        "layout": {
            **BASE_LAYOUT,
            "title": {"text": title},
            "xaxis": {"title": {"text": x_title}, "type": "category"},
            "yaxis": {"title": {"text": metric_title}, "rangemode": "tozero"},
        },
    }
    return fig, "bar", title
