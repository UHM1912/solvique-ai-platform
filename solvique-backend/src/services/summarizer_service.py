"""
Multi-tool summarizer: takes outputs from multiple tool calls and produces
a single coherent summary using a lightweight LLM call.
"""

import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from config import MODEL
from src.logging_config import get_logger

logger = get_logger(__name__)

SUMMARIZER_SYSTEM_PROMPT = """
You are a concise business intelligence analyst.

You will receive structured outputs from multiple data tools (SQL queries, ML predictions, 
document retrieval). Your job is to write a single, coherent, natural-language summary 
that synthesizes the key insights from ALL the tool outputs together.

Rules:
- Do NOT repeat raw numbers in large tables; reference them by pattern or highlight key figures.
- Keep the summary between 3–6 sentences unless complexity demands more.
- Explicitly connect findings across tools when relevant (e.g., "The SQL data shows X, 
  which aligns with the ML forecast of Y").
- Do not mention tool names like "sql_tool" or "rag_tool" — refer to them as 
  "database records", "forecast model", "document insights" etc.
- Never say "I was given" or "the tools returned" — write as if you are the analyst.
"""


def _format_tool_output_for_summarizer(tool_name: str, res_data: dict) -> str:
    """Convert a single tool result dict into a human-readable block for the summarizer."""
    parts = [f"## {tool_name.upper()} OUTPUT"]

    if tool_name == "sql_tool":
        if res_data.get("sql_query"):
            parts.append(f"Query: {res_data['sql_query']}")
        if res_data.get("explanation"):
            parts.append(f"Explanation: {res_data['explanation']}")
        if res_data.get("results"):
            # Truncate large result sets to avoid huge prompts
            results_preview = (
                res_data["results"][:20]
                if isinstance(res_data["results"], list)
                else res_data["results"]
            )
            parts.append(
                f"Results (first 20 rows): {json.dumps(results_preview, default=str)[:3000]}"
            )

    elif tool_name == "ml_tool":
        if res_data.get("explanation"):
            parts.append(f"Forecast Summary: {res_data['explanation']}")
        if res_data.get("results"):
            results_preview = (
                res_data["results"][:20]
                if isinstance(res_data["results"], list)
                else res_data["results"]
            )
            parts.append(
                f"Predicted Values (first 20): {json.dumps(results_preview, default=str)[:3000]}"
            )

    elif tool_name == "rag_tool":
        if res_data.get("answer"):
            parts.append(f"Document Insights: {res_data['answer']}")
        if res_data.get("citations"):
            parts.append(f"Citations count: {len(res_data['citations'])}")

    else:
        if res_data.get("explanation"):
            parts.append(f"Output: {res_data['explanation']}")

    return "\n".join(parts)


def summarize_multi_tool_results(user_query: str, tool_results: dict[int, dict]) -> str:
    """
    Call a summarizer LLM with all tool outputs and the original user query.
    Returns a single summary string.

    Args:
        user_query: The original question the user asked.
        tool_results: The raw dict returned by run_graph (keyed by index).

    Returns:
        A synthesized natural-language summary string.
    """
    formatted_blocks = []
    for idx, res_data in tool_results.items():
        tool_name = res_data.get("tool") or f"tool_{idx}"
        block = _format_tool_output_for_summarizer(tool_name, res_data)
        formatted_blocks.append(block)

    combined = "\n\n".join(formatted_blocks)

    user_message = (
        f"User's original question:\n{user_query}\n\n"
        f"Tool outputs to synthesize:\n{combined}\n\n"
        f"Write a unified summary of these findings."
    )

    llm = ChatGoogleGenerativeAI(model=MODEL, temperature=0, max_retries=1)

    messages = [
        SystemMessage(content=SUMMARIZER_SYSTEM_PROMPT),
        HumanMessage(content=user_message),
    ]

    logger.info("Summarizer: invoking LLM for multi-tool synthesis.")
    response = llm.invoke(messages)
    summary = (
        response.content if isinstance(response.content, str) else str(response.content)
    )
    logger.info("Summarizer: completed.")
    return summary
