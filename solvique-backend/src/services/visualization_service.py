from typing import Any

import pandas as pd

from src.conversation_store import (
    add_message,
    delete_report_assets_for_message,
    ensure_conversation,
    get_message_by_id,
    update_message_metadata,
    update_message_visualization,
)
from src.logging_config import get_logger
from src.schemas.api_models import VisualizeRequest, VisualizeResponse
from src.reporting.report_files import asset_storage
from src.services.request_service import start_request
from src.visualization_tool.dataframe_visualizer import run_dataframe_visualizer

logger = get_logger(__name__)


def _has_precomputed_chart_specs(options: list[dict[str, Any]] | list[Any]) -> bool:
    if not options:
        return False
    return all(
        isinstance(option, dict) and option.get("chart_spec") for option in options
    )


def _build_visualization_metadata(
    result: dict[str, Any],
    request_id: str,
    source_tool: str,
    stable_chart_type_options: list[Any],
) -> dict[str, Any]:
    return {
        "request_id": request_id,
        "source_tool": source_tool,
        "visualization_mode": result.get("visualization_mode", "chart"),
        "visualization_options": result.get("visualization_options", []),
        "chart_type_options": stable_chart_type_options,
        "statistical_summary": result.get("statistical_summary", []),
        "sample_data": result.get("sample_data", []),
        "sample_message": result.get("sample_message"),
    }


def save_visualization(
    req: VisualizeRequest, result: dict[str, Any], request_id: str
) -> None:
    chart_specs = result.get("chart_specs") or []
    if not req.conversation_id or not chart_specs:
        return

    ensure_conversation(req.conversation_id)
    existing_message = (
        get_message_by_id(req.source_message_id) if req.source_message_id else None
    )
    existing_metadata = existing_message.get("metadata", {}) if existing_message else {}
    existing_chart_type_options = existing_metadata.get("chart_type_options") or []
    stable_chart_type_options = (
        existing_chart_type_options
        if _has_precomputed_chart_specs(existing_chart_type_options)
        else result.get("chart_type_options", [])
    )

    metadata = _build_visualization_metadata(
        result, request_id, req.source_tool, stable_chart_type_options
    )

    if (
        req.source_message_id
        and req.source_patch_index is not None
        and existing_message
    ):
        existing_tool_results = existing_metadata.get("tool_results") or []
        if 0 <= req.source_patch_index < len(existing_tool_results):
            merged_tool_results = list(existing_tool_results)
            patch_result = dict(merged_tool_results[req.source_patch_index] or {})
            patch_result.update(
                {
                    "chart_specs": chart_specs,
                    "visualization_options": metadata.get("visualization_options", []),
                    "chart_type_options": metadata.get("chart_type_options", []),
                    "statistical_summary": metadata.get("statistical_summary", []),
                    "sample_data": metadata.get("sample_data", []),
                    "sample_message": metadata.get("sample_message"),
                    "visualization_mode": metadata.get("visualization_mode", "chart"),
                }
            )
            merged_tool_results[req.source_patch_index] = patch_result

            update_message_metadata(
                message_id=req.source_message_id,
                metadata={
                    **existing_metadata,
                    "tool_results": merged_tool_results,
                },
            )
            return

    if req.source_message_id:
        if update_message_visualization(
            message_id=req.source_message_id,
            chart_specs=chart_specs,
            metadata_updates=metadata,
        ):
            for object_path in delete_report_assets_for_message(req.source_message_id):
                asset_storage.delete_object(object_path)
        return

    add_message(
        conversation_id=req.conversation_id,
        role="assistant",
        content=result.get("summary") or "Generated visualization",
        tool="visualize",
        chart_specs=chart_specs,
        metadata=metadata,
    )


def handle_visualize(req: VisualizeRequest) -> VisualizeResponse:
    request_id = start_request(
        f"POST /api/visualize - source_tool: {req.source_tool}, data_rows: {len(req.data)}"
    )

    def error_response(message: str) -> VisualizeResponse:
        return VisualizeResponse(source_tool=req.source_tool, error=message)

    try:
        if not req.data:
            return error_response("No data provided for visualization.")

        df = pd.DataFrame(req.data)
        if df.empty:
            return error_response("DataFrame is empty.")

        result = run_dataframe_visualizer(
            source_tool=req.source_tool,
            df=df,
            requested_chart_type=req.chart_type,
        )
        if req.source_message_id:
            existing_message = get_message_by_id(req.source_message_id)
            existing_chart_type_options = (existing_message or {}).get(
                "metadata", {}
            ).get("chart_type_options") or []
            if existing_chart_type_options:
                new_specs = result.get("chart_specs") or []
                if new_specs:
                    for opt in existing_chart_type_options:
                        if opt.get("chart_type") == new_specs[0].get("chart_type"):
                            opt["chart_spec"] = new_specs[0]
                result["chart_type_options"] = existing_chart_type_options
        save_visualization(req, result, request_id)
        return VisualizeResponse(source_tool=req.source_tool, **result)

    except pd.errors.EmptyDataError:
        logger.error("Empty data provided")
        return error_response("Invalid or empty data format.")
    except ValueError as exc:
        logger.error("Data validation error: %s", exc)
        return error_response(f"Data format error: {exc}")
    except Exception as exc:
        logger.error("Visualization failed: %s", exc, exc_info=True)
        return error_response(f"Visualization error: {exc}")
