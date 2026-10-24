from fastapi import HTTPException
from io import BytesIO
import re

from src.conversation_store import (
    get_conversation as get_conversation_from_store,
    get_report_asset,
    list_report_assets,
)
from src.reporting.report_builder import build_report
from src.reporting.report_files import (
    ReportDocxRenderer,
    asset_storage,
    chart_asset_service,
)
from src.schemas.api_models import ConversationMessage


def _docx_asset_source(asset_id: str):
    try:
        return BytesIO(asset_storage.read_bytes(get_report_asset_or_404(asset_id)["object_path"]))
    except FileNotFoundError:
        return None


docx_renderer = ReportDocxRenderer(asset_path_resolver=_docx_asset_source)


def create_report_docx(conversation_id: str) -> bytes:
    conversation = get_conversation_or_404(conversation_id)
    ensure_chart_assets(conversation, conversation_id)
    sections = build_report(load_messages(conversation, conversation_id))
    return docx_renderer.render(sections)


def get_conversation_or_404(conversation_id: str) -> dict:
    conversation = get_conversation_from_store(conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


def load_messages(
    conversation: dict, conversation_id: str
) -> list[ConversationMessage]:
    assets_by_message: dict[str, list[str]] = {}
    for asset in list_report_assets(conversation_id):
        assets_by_message.setdefault(asset["message_id"], []).append(asset["id"])

    return [
        ConversationMessage(
            id=message["id"],
            role=message["role"],
            content=message.get("content") or "",
            sql_query=message.get("sql_query"),
            results=message.get("dataframe") or message.get("results"),
            citations=message.get("citations") or message.get("doc_citations"),
            doc_citations=message.get("doc_citations"),
            web_citations=message.get("web_citations"),
            chart_asset_ids=assets_by_message.get(message["id"], []),
        )
        for message in conversation.get("messages", [])
        if message.get("role") in {"user", "assistant"}
        and message.get("tool") != "visualize"
    ]


def ensure_chart_assets(conversation: dict, conversation_id: str) -> None:
    existing_message_ids = {
        asset["message_id"] for asset in list_report_assets(conversation_id)
    }

    for message in conversation.get("messages", []):
        if (
            message.get("id") in existing_message_ids
            or message.get("tool") == "visualize"
        ):
            continue

        chart_specs = message.get("chart_specs") or []
        if not chart_specs:
            continue

        chart = chart_specs[0]
        if not chart.get("figure_json"):
            continue

        chart_asset_service.create_chart_asset(
            conversation_id=conversation_id,
            message_id=message["id"],
            figure_json=chart["figure_json"],
        )


def get_report_asset_or_404(asset_id: str) -> dict:
    if not re.fullmatch(r"asset_[a-f0-9]{32}", asset_id):
        raise HTTPException(status_code=400, detail="Invalid asset ID")
    asset = get_report_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


def get_report_preview_sections(conversation_id: str):
    conversation = get_conversation_or_404(conversation_id)
    ensure_chart_assets(conversation, conversation_id)
    return build_report(load_messages(conversation, conversation_id))


def get_report_asset_bytes(asset_id: str) -> bytes:
    asset = get_report_asset_or_404(asset_id)
    try:
        return asset_storage.read_bytes(asset["object_path"])
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail="Asset file not found")

