from fastapi import HTTPException

from src.conversation_store import (
    delete_conversation as delete_conversation_from_store,
    get_conversation as get_conversation_from_store,
    list_conversations,
    list_report_asset_paths_for_conversation,
)
from src.reporting.report_files import asset_storage
from src.services.request_service import start_request


def handle_list_conversations():
    start_request("GET /api/conversations")
    return list_conversations()


def handle_get_conversation(conv_id: str):
    start_request(f"GET /api/conversations/{conv_id}")
    data = get_conversation_from_store(conv_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return data


def handle_delete_conversation(conv_id: str):
    start_request(f"DELETE /api/conversations/{conv_id}")
    asset_paths = list_report_asset_paths_for_conversation(conv_id)
    if not delete_conversation_from_store(conv_id):
        raise HTTPException(status_code=404, detail="Conversation not found")

    for object_path in asset_paths:
        asset_storage.delete_object(object_path)
    return {"status": "deleted", "id": conv_id}
