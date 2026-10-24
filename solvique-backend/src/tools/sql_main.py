import json
import os
from time import perf_counter

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from config import MODEL
from src.logging_config.logger import get_logger
from src.sql_tool_utils.execute_sql_query import extract_query, return_results_bigquery
from src.sql_tool_utils.fetch_schema import fetch_tables_schema
from src.sql_tool_utils.sql_rag_pipeline import explain_sql_results_with_internal_docs

from .config import system_message_bigquery

load_dotenv()

logger = get_logger(__name__)

if not os.environ.get("GOOGLE_API_KEY"):
    logger.warning("GOOGLE_API_KEY is not present.")


def _run_sql_generation(model, user_query: str, schema_text: str):
    user_message = f"User Question: {user_query}\n\nProvided Schema:\n{schema_text}"
    return model.invoke(
        [
            SystemMessage(content=system_message_bigquery),
            HumanMessage(content=user_message),
        ]
    )


@tool
def sql_tool(query: str) -> str:
    """
    Use this tool to answer questions that require querying a database.
    This handles data retrieval, aggregation, filtering, counts, totals,
    averages, rankings, comparisons, reports, summaries, and trends
    from historical records.

    Args:
        query: The user's natural language question about data.

    Returns:
        JSON string with keys: user_query, sql_query, results, explanation, error
    """
    main_start = perf_counter()
    output = {
        "user_query": query,
        "sql_query": None,
        "results": [],
        "explanation": None,
        "error": None,
    }

    if not query:
        output["error"] = "No query provided."
        return json.dumps(output, default=str)

    model = init_chat_model(f"google_genai:{MODEL}", max_retries=1)
    logger.info("SQL tool: Starting pipeline.")

    try:
        schema_results = fetch_tables_schema(query)
        schema_text = json.dumps(schema_results, indent=2)
    except Exception as e:
        logger.warning(f"SQL tool: Schema fetch failed: {e}")
        output["error"] = f"Failed to retrieve schema: {e}"
        return json.dumps(output, default=str)

    try:
        start = perf_counter()
        logger.info("SQL tool: Invoking LLM for SQL generation.")
        result = _run_sql_generation(model, query, schema_text)
        logger.info(
            "SQL tool: SQL generation complete. Execution duration: %.3f seconds.",
            perf_counter() - start,
        )
    except Exception as e:
        logger.warning(f"SQL tool: SQL generation failed: {e}")
        output["error"] = f"LLM query generation failed: {e}"
        return json.dumps(output, default=str)

    try:
        sql_query = extract_query(result)
        output["sql_query"] = sql_query
    except Exception as e:
        logger.warning(f"SQL tool: Could not extract SQL query: {e}")
        output["error"] = f"Could not extract SQL from LLM response: {e}"
        return json.dumps(output, default=str)

    df = return_results_bigquery(sql_query)
    if isinstance(df, str):
        logger.warning(f"SQL tool: Query execution error: {df}")
        output["error"] = df
        return json.dumps(output, default=str)

    try:
        output["results"] = json.loads(df.to_json(orient="records", date_format="iso"))
    except Exception:
        output["results"] = df.to_dict(orient="records")

    try:
        start = perf_counter()
        explanation_payload = explain_sql_results_with_internal_docs(
            user_query=query,
            sql_query=sql_query,
            df=df,
        )
        if isinstance(explanation_payload, dict):
            output["explanation"] = explanation_payload.get("explanation")
            output["citations"] = explanation_payload.get("citations")
            output["doc_citations"] = explanation_payload.get("doc_citations")
            output["web_citations"] = explanation_payload.get("web_citations")
            output["metadata"] = explanation_payload.get("metadata")
        else:
            output["explanation"] = explanation_payload
        logger.info(
            "SQL tool: Explanation pipeline complete. Execution duration: %.3f seconds.",
            perf_counter() - start,
        )
    except Exception as e:
        logger.warning(f"SQL tool: Explanation pipeline failed: {e}")
        output["explanation"] = (
            "Results retrieved successfully, but grounded explanation generation failed."
        )

    logger.info(
        "SQL tool: Pipeline complete. Execution duration: %.3f seconds.",
        perf_counter() - main_start,
    )
    return json.dumps(output, default=str)


if __name__ == "__main__":
    query = input("What do you want to know about the table? : ")
    result = sql_tool.invoke(query)
    print(result)
