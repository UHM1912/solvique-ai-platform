import json
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage

from config import MODEL
from src.sql_tool_utils.sql_rag_embed import fetch_internal_doc_chunks
from src.sql_tool_utils.df_summary import build_result_eda_text


def _safe_extract_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict):
            return first.get("text", str(first))
        return str(first)
    return str(content)


def _format_doc_context(chunks: list[dict]) -> str:
    if not chunks:
        return "No matching internal documentation found."
    return "\n\n".join(
        f"[Doc {i} | File: {item['chunk'].get('filename', '?')} | Section: {item['chunk'].get('heading', '?')}]\n"
        f"{item['chunk'].get('content', '')}"
        for i, item in enumerate(chunks, start=1)
    )


def explain_sql_results_with_internal_docs(user_query: str, sql_query: str, df):
    eda_text = build_result_eda_text(df)

    try:
        retrieved_chunks = fetch_internal_doc_chunks(user_query, k=5)
    except Exception:
        retrieved_chunks = []

    prompt_payload = {
        "user_query": user_query,
        "sql_query": sql_query,
        "eda_output": eda_text,
        "result_preview": json.loads(
            df.head(10).to_json(orient="records", date_format="iso")
        ),
        "internal_doc_context": _format_doc_context(retrieved_chunks),
    }

    system_prompt = """
You are a SQL result explanation assistant.

You will receive:
1. the user question
2. SQL query used to fetch data
3. EDA output derived from the BigQuery result
4. retrieved internal document chunks

Rules:
- Use the EDA output and result preview as the source of factual result statements.
- Use internal document chunks for definitions, business meaning, KPI interpretation, and domain context.
- Do not invent context not present in the chunks.
- If the internal docs do not explain some part, say that clearly.
- Do not reproduce the result rows as a table, list, month-by-month breakdown, or structured data dump.
- Do not output markdown tables.
- Do not restate values row-by-row when the frontend already shows the dataset.
- Focus on high-level interpretation, trend summary, and business context only.
- Respond in plain paragraphs only.
- Do not output raw SQL unless explicitly asked.
- Give a concise, business-friendly explanation.
"""

    llm = ChatGoogleGenerativeAI(model=MODEL, max_retries=1)
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(
            content=json.dumps(prompt_payload, ensure_ascii=False, default=str)
        ),
    ]
    response = llm.invoke(messages)
    citations = [
        {
            "score": item.get("score"),
            "retrieved_rank": index,
            "chunk": {
                **item.get("chunk", {}),
                "type": item.get("chunk", {}).get("type", "document_chunk"),
            },
        }
        for index, item in enumerate(retrieved_chunks, start=1)
    ]

    return {
        "explanation": _safe_extract_text(response.content),
        "citations": citations,
        "doc_citations": citations,
        "web_citations": [],
        "metadata": {
            "citation_origin": "documents",
        },
    }
