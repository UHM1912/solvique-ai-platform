"""
Solvique - LangGraph Agent
A StateGraph that routes user queries to tools and runs a summarization node
when multiple tool calls are present.
"""

import json
import time
from typing import Any, Literal, TypedDict

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph
from langgraph.prebuilt import ToolNode

from config import MODEL
from src.logging_config import get_logger
from src.logging_config.logger import Timer
from src.services.summarizer_service import summarize_multi_tool_results
from src.sql_tool_utils.exponential_backoff import handle_error
from src.tools.ml_tool import ml_tool
from src.tools.rag_tool import rag_tool
from src.tools.sql_main import sql_tool

load_dotenv()

logger = get_logger(__name__)


tools = [sql_tool, ml_tool, rag_tool]

SYSTEM_PROMPT = """
///▙▖▙▖▞▞▙▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂
▛///▞ SOLVIQUE KERNEL :: QUERY.ORCHESTRATION.ENGINE ⫸
//▞▞〔Purpose · Rules · Identity · Structure · Motion〕
P:: Solvique orchestrator — single intelligent brain routing all user queries to appropriate data tools
R:: Tool Selection Protocol
  ┌─ SCOPE GATE
  │  ├─ IN-SCOPE: business data, predictions, analytics, reports, document insights, and document-style knowledge lookup requests
  │  ├─ OUT-OF-SCOPE: chitchat, unrelated personal conversation, and questions with no business/document/data context at all
  │  │  └─ REJECT: "I'm designed to answer business data and prediction questions.
  │  │               Could you ask something related to your data or forecasting needs?"
  │  │
  │  └─ AMBIGUOUS: query intent unclear, insufficient context for tool selection
  │     └─ CLARIFY: "I couldn't determine the best way to answer your question.
  │                   Could you provide more specific details? For example:
  │                   - For data queries: specify what metrics, time periods, or filters you need
  │                   - For predictions: clarify what you want to forecast
  │                   - For document lookups: mention specific information you're seeking"
  │
  ├─ TOOL ROUTING MATRIX
  │  ├─ sql_tool :: STRUCTURED DATA OPERATIONS
  │  │  └─ Triggers: retrieval, filtering, aggregation, counts, totals, averages,
  │  │              rankings, comparisons, reports, summaries, trends
  │  │              from historical database records
  │  │
  │  ├─ ml_tool :: PREDICTIVE INFERENCE
  │  │  └─ Triggers: prediction, forecast, future estimate, probability score,
  │  │              risk classification, model inference, "what if" scenarios
  │  │
  │  └─ rag_tool :: UNSTRUCTURED DOCUMENT RETRIEVAL
  │     └─ Triggers: information lookup, explanations, details, insights
  │                 from reports, invoices, logs, notes, uploaded files
  │                 (definitions, descriptions, context, event details)
  │                 AND questions explicitly framed as being about the provided/uploaded documents,
  │                 even if they ask for latest/current/recent information that may require fallback
  │                 to external web context inside the rag_tool.
  │
  ├─ AMBIGUITY DETECTION
  │  └─ Trigger clarification request when:
  │     ├─ Query lacks specific action verb or metric
  │     ├─ Multiple tools could apply with equal confidence
  │     ├─ Context insufficient to determine data type (structured vs unstructured)
  │     ├─ Query too vague or abstract to map to tool capabilities
  │     └─ Missing critical parameters (time range, entity, comparison basis)
  │
  └─ HYBRID QUERY PROTOCOL
     ├─ Numeric/structured computation → sql_tool (primary)
     ├─ Supporting context/explanations → rag_tool (secondary)
     └─ NEVER: rag_tool for aggregation; sql_tool for document text; ml_tool without explicit prediction need

SPECIAL RAG ROUTING OVERRIDE:
- If the user says things like:
  - "based on the provided documents"
  - "from the uploaded documents"
  - "according to the documents"
  - "using the document set"
  - "from the reports/files/notes"
  then route to rag_tool by default unless the request is clearly a structured SQL aggregation or a forecast request.
- This override still applies when the question contains words like latest, current, recent, news, updates, or 2026.
- Do NOT reject those as out-of-scope if they are framed as document lookup questions.
- The rag_tool is responsible for falling back to web context when the documents do not contain the requested information.
I:: Intelligent query classifier and tool dispatcher — MANDATORY tool invocation OR explicit clarification request
S:: Execution Flow
  ┌─ INPUT ANALYSIS
  ├─ SCOPE VALIDATION
  │  ├─ Out-of-scope? → REJECT
  │  └─ In-scope? → Continue
  ├─ CLARITY CHECK
  │  ├─ Ambiguous/vague? → REQUEST CLARIFICATION
  │  └─ Clear intent? → Continue
  ├─ TOOL SELECTION (required)
  ├─ PARAMETER CONSTRUCTION
  └─ RESULT SYNTHESIS
M:: Activated on every user query; fires scope validation → clarity check → tool selection logic before response generation
:: ∎ //▚▚▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂
:: ∎ //▚▚▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂▂
 
"""

SYSTEM_PROMPT += """

CONVERSATION MEMORY ROUTING RULES:

The conversation history may contain previous user questions, assistant answers,
SQL queries, SQL results, ML predictions, RAG answers, citations, and generated visualizations.

Before selecting any tool, check whether the user's current question can be answered
from the provided conversation history.

ANSWER DIRECTLY FROM CONVERSATION HISTORY when the user asks about:
- previous response
- earlier answer
- above table
- last result
- this result
- that value
- previously generated forecast
- SQL query used earlier
- citations used earlier
- summary of this conversation
- summary of both responses
- comparison between previous SQL/RAG/ML answers
- values already shown in a previous table

Examples:
- "What is the predicted order value for 2018-07-09 in the table above?"
- "Summarize both the SQL and RAG responses."
- "What SQL query did you use?"
- "Compare the previous two answers."
- "What was the value for that date?"

For these questions:
- Do NOT call sql_tool.
- Do NOT call ml_tool.
- Do NOT call rag_tool.
- Answer using only the provided conversation history.
- If the answer is not present in the conversation history, say:
  "I could not find that value in the previous conversation context."

ONLY call tools when the user is asking for a new operation:
- new SQL/database lookup
- new prediction or forecast not already present
- new document/RAG search
- new calculation that cannot be answered from history

If a requested date or value is already present in a previous table, use that table.
If a requested date is not present in previous forecast results and the user is asking
for a new forecast, then call ml_tool.

"""


class GraphState(TypedDict, total=False):
    messages: list[Any]
    tool_results: dict[int, dict[str, Any]]
    final_payload: dict[str, Any]


TOOL_RESULT_OPTIONAL_LIST_FIELDS = (
    "chart_specs",
    "visualization_options",
    "chart_type_options",
    "statistical_summary",
    "sample_data",
)


llm = ChatGoogleGenerativeAI(
    model=MODEL,
    temperature=0,
    max_retries=1,
)

model_with_tools = llm.bind_tools(tools)


def _extract_message_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            item.get("text", "") if isinstance(item, dict) else str(item)
            for item in content
        )
    return str(content or "")


def _empty_tool_result(tool_name: str | None = None) -> dict[str, Any]:
    return {
        "tool": tool_name,
        "explanation": None,
        "citations": None,
        "sql_query": None,
        "answer": None,
        "error": None,
    }


def _message_content_for_history(message: dict) -> str:
    parts = []

    content = message.get("content")
    if content:
        parts.append(str(content))

    sql_query = message.get("sql_query")
    if sql_query:
        parts.append(f"SQL query used:\n{sql_query}")

    results = message.get("dataframe") or message.get("results")
    if results:
        parts.append(f"Structured result:\n{json.dumps(results, default=str)[:8000]}")

    citations = message.get("citations")
    if citations:
        parts.append(f"Citations:\n{json.dumps(citations, default=str)[:4000]}")

    chart_specs = message.get("chart_specs")
    if chart_specs:
        chart_summary = [
            {
                "title": spec.get("title"),
                "chart_type": spec.get("chart_type"),
            }
            for spec in chart_specs
            if isinstance(spec, dict)
        ]
        parts.append(
            f"Generated visualizations:\n{json.dumps(chart_summary, default=str)}"
        )

    return "\n\n".join(parts).strip()


def _build_history_messages(history: list[dict] | None, user_query: str) -> list[Any]:
    history_messages = []

    for message in history or []:
        content = _message_content_for_history(message)
        if not content:
            continue

        role = message.get("role")
        if role == "user":
            history_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            history_messages.append(AIMessage(content=content))

    history_messages.append(HumanMessage(content=user_query))
    return history_messages


def _extract_rag_payload(content: dict[str, Any]) -> dict[str, Any]:
    all_citations = content.get("citations", [])
    return {
        "answer": content.get("answer"),
        "citations": all_citations,
        "doc_citations": [
            c for c in all_citations if c.get("chunk", {}).get("type") != "web_source"
        ]
        or None,
        "web_citations": [
            c for c in all_citations if c.get("chunk", {}).get("type") == "web_source"
        ]
        or None,
        "metadata": {"citation_origin": content.get("citation_origin", "documents")},
        "error": content.get("error"),
    }


def _extract_tool_result(tool_name: str, content: dict[str, Any]) -> dict[str, Any]:
    result = _empty_tool_result(tool_name)

    if tool_name == "sql_tool":
        if content.get("error"):
            result.update(
                {
                    "explanation": (
                        "Execution of the LLM generated SQL query on the Big Query was not "
                        "successful. Please try executing the below query in Big Query by yourself."
                    ),
                    "sql_query": content.get("sql_query"),
                    "error": content.get("error"),
                }
            )
        else:
            result.update(
                {
                    "sql_query": content.get("sql_query"),
                    "results": content.get("results"),
                    "explanation": content.get("explanation"),
                    "citations": content.get("citations"),
                    "doc_citations": content.get("doc_citations"),
                    "web_citations": content.get("web_citations"),
                    "metadata": content.get("metadata"),
                }
            )
        return result

    if tool_name == "ml_tool":
        result.update(
            {
                "explanation": content.get("response"),
                "results": content.get("results", []),
            }
        )
        return result

    if tool_name == "rag_tool":
        result.update(_extract_rag_payload(content))

    return result


def _tool_result_payload(res_data: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "tool": res_data.get("tool"),
        "explanation": res_data.get("explanation") or res_data.get("answer"),
        "sql_query": res_data.get("sql_query"),
        "results": res_data.get("results"),
        "citations": res_data.get("citations"),
        "doc_citations": res_data.get("doc_citations"),
        "web_citations": res_data.get("web_citations"),
        "sample_message": res_data.get("sample_message"),
        "visualization_mode": res_data.get("visualization_mode", "chart"),
        "metadata": res_data.get("metadata"),
        "error": res_data.get("error"),
    }
    payload.update(
        {field: res_data.get(field) or [] for field in TOOL_RESULT_OPTIONAL_LIST_FIELDS}
    )
    return payload


def _last_user_query(messages: list[Any]) -> str:
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return _extract_message_text(msg.content)
    return ""


def _parse_tool_messages(messages: list[Any]) -> dict[int, dict[str, Any]]:
    tool_calls = [msg for msg in messages if isinstance(msg, ToolMessage)]

    if len(tool_calls) == 0:
        direct_result = _empty_tool_result()
        direct_result["explanation"] = _extract_message_text(messages[-1].content)
        return {0: direct_result}

    results: dict[int, dict[str, Any]] = {}
    for idx, msg in enumerate(tool_calls):
        try:
            content = (
                json.loads(msg.content) if isinstance(msg.content, str) else msg.content
            )
        except json.JSONDecodeError:
            continue
        results[idx] = _extract_tool_result(msg.name, content)

    return results


def _build_multi_tool_result_list(
    tool_results: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [_tool_result_payload(res_data) for res_data in tool_results.values()]


def _build_single_or_direct_payload(
    tool_results: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    first = tool_results.get(0, {})
    return {
        "tool": first.get("tool"),
        "explanation": first.get("explanation") or first.get("answer"),
        "sql_query": first.get("sql_query"),
        "results": first.get("results"),
        "citations": first.get("citations"),
        "doc_citations": first.get("doc_citations"),
        "web_citations": first.get("web_citations"),
        "metadata": first.get("metadata"),
        "error": first.get("error"),
    }


def intent_node(state: GraphState) -> GraphState:
    logger.info("Graph: intent_node invoked.")

    messages = state["messages"]
    if not messages or not isinstance(messages[0], SystemMessage):
        messages = [SystemMessage(content=SYSTEM_PROMPT)] + messages

    with Timer("intent_node_llm") as t:
        response = model_with_tools.invoke(messages)

    logger.info(f"Graph: intent_node LLM completed in {t.elapsed:.3f}s")

    if response.tool_calls:
        logger.info(f"Graph: LLM wants to call tool: {response.tool_calls[0]['name']}")
    else:
        logger.info("Graph: LLM responded directly (no tool call).")

    return {"messages": messages + [response]}


tool_node = ToolNode(tools)


def wrapped_tool_node(state: GraphState) -> GraphState:
    logger.info("Graph: tool_node invoked.")
    with Timer("tool_node_execution") as t:
        result = tool_node.invoke({"messages": state["messages"]})
    logger.info(f"Graph: tool_node completed in {t.elapsed:.3f}s")

    updated_messages = state["messages"] + result["messages"]
    tool_results = _parse_tool_messages(updated_messages)

    return {
        "messages": updated_messages,
        "tool_results": tool_results,
    }


def summarize_node(state: GraphState) -> GraphState:
    logger.info("Graph: summarize_node invoked.")

    messages = state["messages"]
    tool_results = state.get("tool_results")

    if tool_results is None:
        tool_results = _parse_tool_messages(messages)

    if len(tool_results) <= 1:
        return {"final_payload": _build_single_or_direct_payload(tool_results)}
    
    logger.info(f"Graph: summarizing {len(tool_results)} tool results.")
    summary = summarize_multi_tool_results(_last_user_query(messages), tool_results)
    final_payload = {
        "tool": "multi_tool",
        "explanation": summary,
        "tool_results": _build_multi_tool_result_list(tool_results),
        "metadata": {
            "tool_count": len(tool_results),
        },
        "error": None,
    }
    return {"final_payload": final_payload}


def should_continue_after_intent(state: GraphState) -> Literal["tools", "summarize"]:
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "summarize"


graph_builder = StateGraph(GraphState)
graph_builder.add_node("intent", intent_node)
graph_builder.add_node("tools", wrapped_tool_node)
graph_builder.add_node("summarize", summarize_node)

graph_builder.add_edge(START, "intent")
graph_builder.add_conditional_edges("intent", should_continue_after_intent)
graph_builder.add_edge("tools", "summarize")
graph_builder.add_edge("summarize", END)

graph = graph_builder.compile()

logger.info("Graph: LangGraph compiled successfully.")


def run_graph(
    user_query: str, attempt: int, history: list[dict] | None = None
) -> dict[str, Any]:
    """
    Run the Solvique graph for a user query.

    Returns:
        A normalized final payload ready for API response construction.
    """
    logger.info(f"Graph: run_graph called with query: {user_query[:80]!r}")
    logger.info(f"Attempt {attempt} starting at time: {time.time()}")

    try:
        history_messages = _build_history_messages(history, user_query)

        with Timer("full_graph_run") as t:
            result = graph.invoke({"messages": history_messages})

    except Exception as e:
        print(f"Exception occurred while running the graph:\n{e}")
        print(f"Raised exception type: {type(e)}")
        wait = handle_error(e, attempt=attempt)
        time.sleep(wait)
        return run_graph(user_query, attempt=attempt + 1, history=history)

    logger.info(f"Graph: run_graph completed in {t.elapsed:.3f}s")
    logger.info("Graph: finished execution.")
    return result["final_payload"]
