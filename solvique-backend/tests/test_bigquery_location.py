from unittest.mock import patch

from src.sql_tool_utils import execute_sql_query


def test_ecommerce_bigquery_query_uses_us_location_by_default(monkeypatch):
    monkeypatch.setenv("big_query_dataset", "ecommerce")
    monkeypatch.delenv("big_query_location", raising=False)
    expected_result = object()

    with patch.object(execute_sql_query, "read_gbq", return_value=expected_result) as read_gbq:
        result = execute_sql_query.return_results_bigquery("SELECT 1;")

    assert result is expected_result
    read_gbq.assert_called_once_with(
        "SELECT 1",
        project_id=execute_sql_query.project_id,
        dialect="standard",
        location="US",
    )


def test_other_bigquery_dataset_keeps_location_configurable(monkeypatch):
    monkeypatch.setenv("big_query_dataset", "analytics_eu")
    monkeypatch.setenv("big_query_location", "EU")
    expected_result = object()

    with patch.object(execute_sql_query, "read_gbq", return_value=expected_result) as read_gbq:
        result = execute_sql_query.return_results_bigquery("SELECT 1")

    assert result is expected_result
    read_gbq.assert_called_once_with(
        "SELECT 1",
        project_id=execute_sql_query.project_id,
        dialect="standard",
        location="EU",
    )


def test_other_dataset_without_location_keeps_existing_inference(monkeypatch):
    monkeypatch.setenv("big_query_dataset", "analytics_eu")
    monkeypatch.delenv("big_query_location", raising=False)
    expected_result = object()

    with patch.object(execute_sql_query, "read_gbq", return_value=expected_result) as read_gbq:
        result = execute_sql_query.return_results_bigquery("SELECT 1")

    assert result is expected_result
    read_gbq.assert_called_once_with(
        "SELECT 1",
        project_id=execute_sql_query.project_id,
        dialect="standard",
        location=None,
    )
