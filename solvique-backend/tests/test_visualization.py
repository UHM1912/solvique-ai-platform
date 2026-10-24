"""
Unit tests for deterministic on-demand visualization.
Verifies Phase 1 requirements:
- Deterministic chart profiling and generation
- Security: No unsafe agents or code execution
- Prophet forecasting confidence bands
- Graceful handling of empty, malformed, and RAG/text-only data
- On-demand chart type selection
"""

import json
import pytest
import pandas as pd

from src.schemas.api_models import VisualizeRequest, VisualizeResponse
from src.services.visualization_service import handle_visualize
from src.visualization_tool.chart_engine import (
    build_figure_spec,
    is_forecast_df,
    profile_dataframe,
)
from src.visualization_tool.dataframe_visualizer import run_dataframe_visualizer


def test_no_unsafe_pandas_agent_in_codebase():
    """Verify create_pandas_dataframe_agent and allow_dangerous_code are eliminated."""
    with open("src/visualization_tool/dataframe_visualizer.py", "r", encoding="utf-8") as f:
        code = f.read()
    assert "create_pandas_dataframe_agent" not in code
    assert "allow_dangerous_code" not in code


def test_forecast_dataframe_profiling_and_generation():
    """Verify Prophet forecast data gets trend line with confidence intervals, bar, and area views."""
    data = [
        {"date": "2018-07-09", "yhat": 150.2, "yhat_lower": 130.0, "yhat_upper": 170.5},
        {"date": "2018-07-10", "yhat": 160.0, "yhat_lower": 140.0, "yhat_upper": 180.0},
        {"date": "2018-07-11", "yhat": 155.8, "yhat_lower": 135.0, "yhat_upper": 175.0},
    ]
    df = pd.DataFrame(data)
    assert is_forecast_df(df)

    profile = profile_dataframe(df)
    assert profile["supported"] is True
    assert profile["default_type"] == "line"
    chart_types = [opt["chart_type"] for opt in profile["options"]]
    assert "line" in chart_types
    assert "bar" in chart_types
    assert "area" in chart_types

    # Test default figure generation
    fig, resolved_type, title = build_figure_spec(df, source_tool="ml_tool")
    assert resolved_type == "line"
    assert len(fig["data"]) == 3  # upper, lower, yhat
    assert fig["data"][0]["name"] == "Upper Bound"
    assert fig["data"][1]["name"] == "Lower Bound"
    assert fig["data"][2]["name"] == "Predicted Orders"

    # Test on-demand bar figure generation
    fig_bar, bar_type, _ = build_figure_spec(df, source_tool="ml_tool", requested_chart_type="bar")
    assert bar_type == "bar"
    assert len(fig_bar["data"]) == 1
    assert fig_bar["data"][0]["type"] == "bar"

    # Test on-demand area figure generation
    fig_area, area_type, _ = build_figure_spec(df, source_tool="ml_tool", requested_chart_type="area")
    assert area_type == "area"
    assert len(fig_area["data"]) == 1
    assert fig_area["data"][0]["fill"] == "tozeroy"


def test_sql_time_series_data():
    """Verify time-series SQL results produce valid line and bar specs."""
    data = [
        {"month": "2017-01", "total_revenue": 125000.50},
        {"month": "2017-02", "total_revenue": 145000.00},
        {"month": "2017-03", "total_revenue": 165000.25},
        {"month": "2017-04", "total_revenue": 155000.10},
    ]
    df = pd.DataFrame(data)
    profile = profile_dataframe(df)
    assert profile["supported"] is True
    chart_types = [opt["chart_type"] for opt in profile["options"]]
    assert "line" in chart_types
    assert "bar" in chart_types

    fig, resolved_type, title = build_figure_spec(df, source_tool="sql_tool", requested_chart_type="line")
    assert resolved_type == "line"
    assert fig["data"][0]["type"] == "scatter"
    assert len(fig["data"][0]["x"]) == 4


def test_sql_categorical_data_and_pie():
    """Verify categorical SQL results support Bar and Pie charts when unique categories <= 8."""
    data = [
        {"payment_type": "credit_card", "total_orders": 76000},
        {"payment_type": "boleto", "total_orders": 19000},
        {"payment_type": "voucher", "total_orders": 5000},
        {"payment_type": "debit_card", "total_orders": 1500},
    ]
    df = pd.DataFrame(data)
    profile = profile_dataframe(df)
    assert profile["supported"] is True
    chart_types = [opt["chart_type"] for opt in profile["options"]]
    assert "bar" in chart_types
    assert "pie" in chart_types  # Since unique categories = 4 <= 8

    # Test pie chart generation
    fig_pie, resolved_type, title = build_figure_spec(df, source_tool="sql_tool", requested_chart_type="pie")
    assert resolved_type == "pie"
    assert fig_pie["data"][0]["type"] == "pie"
    assert len(fig_pie["data"][0]["labels"]) == 4


def test_scatter_plot_two_numerics():
    """Verify 2 numeric columns support scatter plot."""
    data = [
        {"item_price": 45.0, "freight_value": 15.2, "category": "health_beauty"},
        {"item_price": 120.0, "freight_value": 28.5, "category": "watches"},
        {"item_price": 89.0, "freight_value": 19.8, "category": "bed_bath_table"},
    ]
    df = pd.DataFrame(data)
    profile = profile_dataframe(df)
    assert profile["supported"] is True
    chart_types = [opt["chart_type"] for opt in profile["options"]]
    assert "scatter" in chart_types

    fig, resolved_type, title = build_figure_spec(df, source_tool="sql_tool", requested_chart_type="scatter")
    assert resolved_type == "scatter"
    assert fig["data"][0]["mode"] == "markers"


def test_empty_and_unsupported_text_data():
    """Verify empty or non-numeric text data is handled gracefully with no exceptions."""
    # 1. Empty data
    empty_res = run_dataframe_visualizer(source_tool="sql_tool", df=pd.DataFrame())
    assert empty_res["chart_specs"] == []
    assert empty_res["error"] is not None

    # 2. Text-only data (like document notes or IDs without metrics)
    text_df = pd.DataFrame([{"seller_id": "abc", "status": "active"}, {"seller_id": "def", "status": "pending"}])
    text_res = run_dataframe_visualizer(source_tool="sql_tool", df=text_df)
    assert text_res["chart_specs"] == []
    assert "No numeric" in text_res["error"]


def test_handle_visualize_api_integration():
    """Verify the FastAPI service handler accepts VisualizeRequest and returns VisualizeResponse."""
    req = VisualizeRequest(
        source_tool="sql_tool",
        data=[{"category": "electronics", "sales": 500}, {"category": "clothing", "sales": 300}],
        chart_type="bar",
    )
    resp = handle_visualize(req)
    assert isinstance(resp, VisualizeResponse)
    assert resp.error is None
    assert len(resp.chart_specs) == 1
    spec = resp.chart_specs[0]
    assert spec["chart_type"] == "bar"
    fig = json.loads(spec["figure_json"])
    assert "data" in fig and "layout" in fig
