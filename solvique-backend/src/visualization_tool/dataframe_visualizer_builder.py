import json
from typing import Any
import pandas as pd

DEFAULT_CHART_TYPE_OPTIONS = [
    {
        "id": "chart_type_option_1",
        "label": "Bar",
        "description": "Compare values as bars.",
        "chart_type": "bar",
        "is_custom": False,
        "chart_spec": None,
    },
    {
        "id": "chart_type_option_2",
        "label": "Line",
        "description": "Show ordered progression as a line.",
        "chart_type": "line",
        "is_custom": False,
        "chart_spec": None,
    },
    {
        "id": "chart_type_option_3",
        "label": "Scatter",
        "description": "Show numeric relationship as points.",
        "chart_type": "scatter",
        "is_custom": False,
        "chart_spec": None,
    },
]

_LAYOUT = lambda title, extra=None: {
    "title": {"text": title},
    "xaxis": {"title": {"text": "Date"}, "type": "category"},
    "yaxis": {"title": {"text": "Predicted Orders"}, "rangemode": "tozero"},
    "template": "plotly_white",
    "margin": {"l": 60, "r": 30, "t": 80, "b": 70},
    **(extra or {}),
}


def is_forecast_df(df: pd.DataFrame) -> bool:
    return {"date", "yhat", "yhat_lower", "yhat_upper"}.issubset(df.columns)


def _make_forecast_figure(
    dates, yhat, lower=None, upper=None, chart_type="line"
) -> dict[str, Any]:
    if chart_type == "bar":
        return {
            "data": [
                {
                    "x": dates,
                    "y": yhat,
                    "type": "bar",
                    "marker": {"color": "rgb(0, 105, 92)"},
                    "name": "Predicted Orders",
                }
            ],
            "layout": _LAYOUT("Forecast Bar View"),
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
                    "line": {"color": "rgb(0, 105, 92)", "width": 3},
                    "name": "Predicted Orders",
                }
            ],
            "layout": _LAYOUT("Forecast Area View"),
        }
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
                "line": {"color": "rgb(0, 105, 92)", "width": 3},
                "marker": {"size": 7},
                "name": "Predicted Orders",
            },
        ],
        "layout": _LAYOUT(
            f"{len(dates)}-Day Order Forecast with Confidence Range",
            {
                "hovermode": "x unified",
                "legend": {
                    "orientation": "h",
                    "y": 1.12,
                    "x": 0.5,
                    "xanchor": "center",
                },
            },
        ),
    }


def build_forecast_visualization(df: pd.DataFrame) -> dict[str, Any]:
    df = df[["date", "yhat", "yhat_lower", "yhat_upper"]].copy()
    df["date"] = df["date"].astype(str)
    dates, yhat = df["date"].tolist(), [int(v) for v in df["yhat"]]
    lower, upper = (
        [int(v) for v in df["yhat_lower"]],
        [int(v) for v in df["yhat_upper"]],
    )

    def spec(label, chart_type):
        return {
            "title": f"Forecast {label} View",
            "chart_type": chart_type,
            "figure_json": json.dumps(
                _make_forecast_figure(dates, yhat, lower, upper, chart_type)
            ),
        }

    line_spec, bar_spec, area_spec = (
        spec("Line", "line"),
        spec("Bar", "bar"),
        spec("Area", "area"),
    )
    chart_type_options = [
        {
            "id": "chart_type_option_1",
            "label": "Line",
            "description": "Shows the forecast trend with its confidence range.",
            "chart_type": "line",
            "is_custom": False,
            "chart_spec": line_spec,
        },
        {
            "id": "chart_type_option_2",
            "label": "Bar",
            "description": "Compares predicted orders date by date as bars.",
            "chart_type": "bar",
            "is_custom": False,
            "chart_spec": bar_spec,
        },
        {
            "id": "chart_type_option_3",
            "label": "Area",
            "description": "Emphasizes forecast volume over time as a filled area.",
            "chart_type": "area",
            "is_custom": False,
            "chart_spec": area_spec,
        },
    ]
    return {
        "summary": f"The forecast covers all {len(df)} days and returns precomputed chart-type views.",
        "chart_specs": [line_spec],
        "visualization_options": [],
        "chart_type_options": chart_type_options,
        "visualization_mode": "chart",
    }


def build_dataframe_preview(df: pd.DataFrame, row_count: int = 5) -> str:
    preview = df.head(row_count).where(pd.notna(df.head(row_count)), None)
    return json.dumps(
        {
            "row_count": int(len(df)),
            "columns": [
                {
                    "name": str(c),
                    "dtype": str(df[c].dtype),
                    "non_null": int(df[c].notna().sum()),
                }
                for c in df.columns
            ],
            "first_rows": preview.to_dict(orient="records"),
        },
        default=str,
    )


def build_dataframe_eda(df: pd.DataFrame) -> str:
    numeric_cols = df.select_dtypes(include="number").columns.tolist()
    datetime_like_cols, categorical_cols = [], []
    for col in df.columns:
        if col in numeric_cols:
            continue
        sample = df[col].dropna().head(25)
        (
            datetime_like_cols
            if not sample.empty
            and pd.to_datetime(sample, errors="coerce").notna().mean() >= 0.8
            else categorical_cols
        ).append(str(col))

    def col_summary(col):
        s = df[col]
        info: dict[str, Any] = {
            "name": str(col),
            "dtype": str(s.dtype),
            "non_null": int(s.notna().sum()),
            "null_count": int(s.isna().sum()),
            "unique_count": int(s.nunique(dropna=True)),
        }
        if col in numeric_cols:
            n = pd.to_numeric(s, errors="coerce").dropna()
            if not n.empty:
                info["stats"] = {
                    "min": float(n.min()),
                    "max": float(n.max()),
                    "mean": float(n.mean()),
                    "median": float(n.median()),
                }
        else:
            info["top_values"] = (
                s.astype(str)
                .replace("nan", None)
                .dropna()
                .value_counts()
                .head(5)
                .to_dict()
            )
        return info

    return json.dumps(
        {
            "row_count": int(len(df)),
            "column_count": int(len(df.columns)),
            "numeric_columns": numeric_cols,
            "datetime_like_columns": datetime_like_cols,
            "categorical_columns": categorical_cols,
            "columns": [col_summary(c) for c in df.columns],
        },
        default=str,
    )


def build_prompt(
    *, source_tool: str, dataframe_preview: str, dataframe_eda: str
) -> str:
    return f"""PRISM VISUALIZATION KERNEL :: Purpose - Rules - Identity - Structure - Motion

P:: create.one.best.plotly.visualization.from.dataframe.only - zero.fabrication - strict.json.only
R:: use.preview.only.for.planning - use.eda.for.chart.selection - run.chart.code.on.full.dataframe.variable.df - never.hardcode.preview.rows - no.markdown - no.extra.text - no.sql - no.code.blocks
S:: inspect.preview.and.eda -> choose.valid.columns -> write.primary.plotly.chart -> write.three.frontend.ready.chart.type.variants -> return.strict.payload
M:: output.strict.json.only

DataFrame from `{source_tool}` is available as `df`.
Preview (planning only): {dataframe_preview}
EDA: {dataframe_eda}

Behavior: `chart_specs` renders immediately. `chart_type_options` render on click with no LLM call. Leave `visualization_options` as an empty list.

Rules:
1. Exactly ONE primary chart in `chart_specs`, THREE `chart_type_options`, empty `visualization_options`.
2. `chart_type_options`: dynamic per data, same analytical intent as primary, different geometry, each with complete `figure_json`.
3. Use full `df`, never preview rows. Include axis titles. Return strict JSON only.

Chart type guidance: line/area=ordered or time axis; bar=categories or rankings; scatter=numeric relationships; histogram/box/violin=distributions; pie=small category counts only; heatmap=matrix or pairwise structure only.

Return exactly:
{{
  "summary": "brief insight",
  "chart_specs": [{{"title": "...", "chart_type": "bar", "figure_json": "<fig.to_json()>"}}],
  "visualization_options": [],
  "chart_type_options": [
    {{"id": "chart_type_option_1", "label": "...", "description": "...", "chart_type": "dynamic_type_1", "is_custom": false, "chart_spec": {{"title": "...", "chart_type": "dynamic_type_1", "figure_json": "<fig.to_json()>"}}}},
    {{"id": "chart_type_option_2", "label": "...", "description": "...", "chart_type": "dynamic_type_2", "is_custom": false, "chart_spec": {{"title": "...", "chart_type": "dynamic_type_2", "figure_json": "<fig.to_json()>"}}}},
    {{"id": "chart_type_option_3", "label": "...", "description": "...", "chart_type": "dynamic_type_3", "is_custom": false, "chart_spec": {{"title": "...", "chart_type": "dynamic_type_3", "figure_json": "<fig.to_json()>"}}}}
  ],
  "visualization_mode": "chart"
}}
"""
