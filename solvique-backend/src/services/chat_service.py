from fastapi import HTTPException

from graph import run_graph
from src.conversation_store import add_message, ensure_conversation, get_recent_messages
from src.logging_config import get_logger
from src.logging_config.logger import Timer
from src.pre_filter_llm import run_filter
from src.schemas.api_models import ChatRequest, ChatResponse
from src.services.request_service import start_request
from src.sql_tool_utils.exponential_backoff import NonRetryableError, RetryableError

logger = get_logger(__name__)


def handle_chat(req: ChatRequest) -> list[ChatResponse]:
    request_id = start_request(f"POST /api/chat - query: {req.query[:120]!r}")
    conversation = ensure_conversation(req.conversation_id, first_message=req.query)
    conv_id = conversation["id"]
    history = get_recent_messages(conv_id, limit=10)

    add_message(conversation_id=conv_id, role="user", content=req.query)

    if filter_response := run_filter(req.query):
        add_message(
            conversation_id=conv_id,
            role="assistant",
            content=filter_response,
            tool="pre_filter",
        )
        return [
            ChatResponse(
                conversation_id=conv_id, tool="pre_filter", explanation=filter_response
            )
        ]

    try:
        with Timer("langgraph_agent") as timer:
            graph_result = run_graph(req.query, 1, history=history)
    except (NonRetryableError, RetryableError) as exc:
        raise HTTPException(
            status_code=int(exc.error_code), detail=exc.error_message
        ) from exc

    logger.info("LangGraph agent completed in %.3fs", timer.elapsed)

    response_metadata = {
        "request_id": request_id,
        **(graph_result.get("metadata") or {}),
    }

    response = ChatResponse(
        conversation_id=conv_id,
        tool=graph_result.get("tool") or "unknown_tool",
        explanation=graph_result.get("explanation") or "",
        citations=graph_result.get("citations"),
        doc_citations=graph_result.get("doc_citations"),
        web_citations=graph_result.get("web_citations"),
        metadata=response_metadata,
        sql_query=graph_result.get("sql_query"),
        results=graph_result.get("results"),
        error=graph_result.get("error"),
        tool_results=graph_result.get("tool_results"),
    )

    saved_metadata = dict(response_metadata)
    if response.tool_results:
        saved_metadata["tool_results"] = response.tool_results

    saved_message = add_message(
        conversation_id=conv_id,
        role="assistant",
        content=response.explanation or "",
        tool=response.tool,
        sql_query=response.sql_query,
        results=response.results,
        citations=response.citations,
        doc_citations=response.doc_citations,
        web_citations=response.web_citations,
        metadata=saved_metadata,
    )
    response.message_id = saved_message["id"]

    logger.info("Conversation %s saved with assistant response.", conv_id)
    return [response]
