import asyncio
import json
import logging
import os
import re
import threading
from time import perf_counter

from dotenv import load_dotenv
from langchain_core.tools import tool
from langchain_google_genai import ChatGoogleGenerativeAI

from config import MODEL
from src.rag_tool_utils.fetch_chunks import fetch_relevant_chunks
from src.rag_tool_utils.web_fallback import build_web_citations, search_web_context

load_dotenv(".env")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not os.environ.get("GOOGLE_API_KEY"):
    logger.warning("RAG tool: GOOGLE_API_KEY is not present.")


load_dotenv(".env")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

if not os.environ.get("GOOGLE_API_KEY"):
    logger.warning("RAG tool: GOOGLE_API_KEY is not present.")

# ── Helpers ───────────────────────────────────────────────────────────────────


def _extract_text(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        ).strip()
    return str(content).strip()


def _parse_decomposition(raw: str) -> dict:
    """Parse the model's JSON object, tolerating common Markdown wrappers."""
    candidate = raw.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*|\s*```$", "", candidate, flags=re.I)
    if not candidate:
        raise ValueError("The model returned an empty decomposition.")
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", candidate)
        if not match:
            raise ValueError("The model response did not contain a JSON object.")
        parsed = json.loads(match.group(0))
    if not isinstance(parsed, dict) or not {"doc_answer", "web_query"}.issubset(parsed):
        raise ValueError("The model JSON is missing doc_answer or web_query.")
    return parsed


def _run_tavily(query: str) -> list[dict]:
    coroutine = search_web_context(
        query=query, max_results=5, search_depth="advanced", topic="general"
    )
    try:
        asyncio.get_running_loop()
        holder: dict = {}

        def _run():
            holder["v"] = asyncio.run(coroutine)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        t.join()
        return holder["v"].get("results", [])
    except RuntimeError:
        return asyncio.run(coroutine).get("results", [])


def _doc_citations(chunks: list[dict]) -> list[dict]:
    return [
        {
            "score": item.get("score"),
            "retrieved_rank": rank,
            "chunk": {
                **{
                    k: (chunk := item.get("chunk", {})).get(k)
                    for k in ("filename", "filetype", "chunk_no", "total_chunks")
                },
                "type": chunk.get("filetype", "document_chunk"),
                "heading": chunk.get("heading") or f"Chunk {rank}",
                "content": chunk.get("content", ""),
            },
        }
        for rank, item in enumerate(chunks, start=1)
    ]


def _fmt_doc_context(chunks: list[dict]) -> str:
    return "\n\n".join(
        f"[Doc {i} | File: {c.get('filename', '?')} | Section: {c.get('heading', '?')}]\n{c.get('content', '')}"
        for i, item in enumerate(chunks, 1)
        if (c := item["chunk"]) is not None
    )


def _fmt_web_context(results: list[dict]) -> str:
    return "\n\n".join(
        f"[Web {i} | Title: {r.get('title', '?')} | URL: {r.get('url', '')}]\n{r.get('content', '')}"
        for i, r in enumerate(results, 1)
    )


def _llm_invoke(llm, prompt: str, label: str) -> str:
    t = perf_counter()
    resp = llm.invoke(prompt)
    logger.info("RAG tool: %s — %.3fs", label, perf_counter() - t)
    return _extract_text(resp.content).strip()


# ── Prompts ───────────────────────────────────────────────────────────────────

# Step 1: Decompose the query against doc context.
# LLM identifies what it can answer from docs and what sub-questions need web.
DECOMPOSE_PROMPT = """
You are a query decomposer for a RAG pipeline.
 
Given a user question and retrieved document context, your job is to:
1. Answer the parts of the question that are covered by the documents.
2. Identify the specific sub-questions or information gaps that the documents do NOT cover.
 
RULES
- Only use information explicitly present in the document context.
- Do not fabricate or guess missing information.
- Be precise about what is missing — phrase it as a focused search query for a web search engine.
- If the documents fully answer the question, set web_query to null.
- If the documents answer nothing, set doc_answer to null.
- Do not mention filenames, chunk ids, or retrieval labels in doc_answer.
 
DOCUMENT CONTEXT
{doc_context}
 
USER QUESTION
{query}
 
Respond ONLY with valid JSON (no fences, no explanation):
{{
  "doc_answer": "<what the documents can answer, or null>",
  "web_query": "<focused web search query for the missing part, or null>"
}}
"""
# Step 2 (only when web results exist): Merge doc answer + web results into one response.
MERGE_PROMPT = """
You are a response synthesizer. Combine the document answer and web search results
into a single, coherent, natural response for the user.
 
RULES
- Blend both sources seamlessly — do not say "from the documents" or "from the web".
- Do not repeat information unnecessarily.
- Do not mention chunk ids, filenames, URLs, or pipeline internals.
- The frontend handles citations separately.
- Be precise and directly answer the user's question.
 
DOCUMENT ANSWER
{doc_answer}
 
WEB RESULTS
{web_context}
 
USER QUESTION
{query}
 
Respond with a clean, unified answer only.
"""


@tool
def rag_tool(query: str) -> str:
    """
    Answers questions using documents and web search intelligently:
    - Doc only    → if documents fully cover the query
    - Web only    → if documents have nothing relevant
    - Hybrid      → doc answers its part, web fills the identified gap

    Args:
        query: The user's natural language question.

    Returns:
        JSON with keys: user_query, retrieved_chunks, answer, error, citations, citation_origin
    """
    t0 = perf_counter()
    output = {
        "user_query": query,
        "retrieved_chunks": [],
        "answer": None,
        "error": None,
        "citations": [],
        "citation_origin": "documents",
    }

    if not query:
        output["error"] = "No query provided."
        return json.dumps(output, default=str)

    # ── Step 1: Retrieve document chunks ──────────────────────────────────
    try:
        t = perf_counter()
        chunks = fetch_relevant_chunks(query)
        logger.info(
            "RAG tool: Retrieved %d chunks — %.3fs", len(chunks), perf_counter() - t
        )
        output["retrieved_chunks"] = chunks
        output["citations"] = _doc_citations(chunks)
    except Exception as e:
        output["error"] = f"Chunk retrieval failed: {e}"
        return json.dumps(output, default=str)

    # ── Step 2: Decompose — what can docs answer? what needs web? ─────────
    llm = ChatGoogleGenerativeAI(model=MODEL, max_retries=1)
    try:
        prompt = DECOMPOSE_PROMPT.format(doc_context=_fmt_doc_context(chunks), query=query)
        raw = _llm_invoke(llm, prompt, "decompose")
        try:
            decomp = _parse_decomposition(raw)
        except (ValueError, json.JSONDecodeError):
            # Retry once with an explicit format reminder. Never turn malformed
            # model output into a fabricated answer or a success response.
            raw = _llm_invoke(
                llm,
                prompt + "\n\nYour previous response was invalid. Return one valid JSON object with exactly the requested keys.",
                "decompose-retry",
            )
            decomp = _parse_decomposition(raw)
    except Exception as e:
        logger.warning("RAG tool: decomposition failed after retry: %s", e)
        output["error"] = "Answer generation failed while analyzing retrieved documents. Please retry."
        return json.dumps(output, default=str)

    doc_answer = decomp.get("doc_answer")  # str | None — what docs covered
    web_query = decomp.get("web_query")  # str | None — focused query for missing part

    logger.info("RAG tool: doc_answer=%s | web_query=%s", bool(doc_answer), web_query)

    # ── Step 3: Route ─────────────────────────────────────────────────────

    if doc_answer and not web_query:
        #  Fully answered by documents
        output["answer"] = doc_answer
        output["citation_origin"] = "documents"

    elif web_query:
        #  Web needed — either to fill a gap (partial) or answer fully (none)
        try:
            web_results = _run_tavily(web_query)
        except Exception as e:
            logger.warning("RAG tool: Tavily failed: %s", e)
            # Graceful degradation — return whatever docs had
            output["answer"] = doc_answer or "Could not retrieve information."
            return json.dumps(output, default=str)

        if doc_answer and web_results:
            #  Hybrid — merge doc answer + web results
            output["answer"] = _llm_invoke(
                llm,
                MERGE_PROMPT.format(
                    doc_answer=doc_answer,
                    web_context=_fmt_web_context(web_results),
                    query=query,
                ),
                "merge",
            )
            output["citations"] = _doc_citations(chunks) + build_web_citations(
                web_results
            )
            output["citation_origin"] = "hybrid"

        elif web_results:
            #  Docs had nothing — answer purely from web
            output["answer"] = _llm_invoke(
                llm,
                MERGE_PROMPT.format(
                    doc_answer="",
                    web_context=_fmt_web_context(web_results),
                    query=query,
                ),
                "web-only",
            )
            output["citations"] = build_web_citations(web_results)
            output["citation_origin"] = "web"

        else:
            output["answer"] = (
                doc_answer or "No relevant information found in documents or web."
            )

    else:
        output["answer"] = "No relevant information found."

    logger.info("RAG tool: done — %.3fs", perf_counter() - t0)
    if not isinstance(output["answer"], str) or not output["answer"].strip():
        output["error"] = output["error"] or "Answer generation returned no response. Please retry."
        output["answer"] = ""
    return json.dumps(output, default=str)
