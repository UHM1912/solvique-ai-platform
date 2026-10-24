"""
AI-assisted report generation module.
Synthesizes conversation history, query results, ML predictions, and RAG citations
into a professional, structured executive report using Google Gemini.
Falls back gracefully to deterministic structure upon AI timeout or failure.
"""

import json
import logging
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

from config import MODEL
from src.logging_config import get_logger
from src.schemas.api_models import ConversationMessage, ReportSection

logger = get_logger(__name__)

MARKDOWN_TABLE_RE = re.compile(r"^\s*\|.*\|\s*$")
MARKDOWN_HEADING_RE = re.compile(r"^\s*#{1,6}\s*")
SPACE_RE = re.compile(r"\s+")

REPORT_SYNTHESIS_SYSTEM_PROMPT = """
You are an executive business intelligence analyst and report author.
Your task is to analyze the user's questions, the system's execution results (SQL data, ML forecasts, RAG document citations), and generate a cohesive, professional analytical report.

CRITICAL GROUNDING RULES:
1. ONLY state facts, numbers, dates, categories, and metrics that appear in the provided query results or assistant responses.
2. NEVER invent, extrapolate, or hallucinate metrics, percentages, dollar amounts, or dates not supported by the data.
3. If an answer was not found or an error occurred, clearly state that limitation.
4. Synthesize across turns: connect the user's goals with the metrics discovered.

OUTPUT FORMAT:
Return a single strictly valid JSON object (no markdown code fences, no extra text):
{
  "executive_summary": "2-3 comprehensive paragraphs providing an executive overview of the conversation, key findings, and business implications.",
  "turn_analyses": [
    {
      "turn_index": 0,
      "heading": "Professional business title for this analysis topic",
      "key_findings": [
        "Concise, metric-grounded key takeaway 1",
        "Concise, metric-grounded key takeaway 2",
        "Concise, metric-grounded key takeaway 3"
      ],
      "narrative": "Detailed, professional paragraph interpreting the results, trends, or documented facts in business context."
    }
  ],
  "strategic_recommendations": [
    "Actionable, forward-looking business recommendation 1 based on findings",
    "Actionable, forward-looking business recommendation 2 based on findings",
    "Actionable, forward-looking business recommendation 3 based on findings"
  ]
}
"""


def clean(text: str) -> str:
    lines = []
    for line in (text or "").splitlines():
        line = MARKDOWN_HEADING_RE.sub("", line).replace("*", "").strip()
        if line and not MARKDOWN_TABLE_RE.match(line):
            lines.append(line)
    return SPACE_RE.sub(" ", " ".join(lines)).strip()


def is_table(value) -> bool:
    return isinstance(value, list) and bool(value) and isinstance(value[0], dict)


def format_citations(citations: Any) -> str:
    if isinstance(citations, dict):
        citations = [citations]
    if not isinstance(citations, list):
        return str(citations or "")

    lines = []
    for item in citations:
        if isinstance(item, dict):
            # Check for RAG chunk citation structure
            chunk = item.get("chunk") or {}
            filename = chunk.get("filename") or item.get("filename")
            heading = chunk.get("heading") or item.get("heading")
            url = chunk.get("url") or item.get("url") or item.get("link")
            title = item.get("title") or filename or "Source Document"

            if filename and heading:
                lines.append(f"Document: {filename} (Section: {heading})")
            elif url:
                lines.append(f"Web Source: {title} ({url})")
            else:
                lines.append(f"Reference: {title}")
        elif isinstance(item, str):
            lines.append(f"Reference: {item}")

    return "\n".join(lines) if lines else "No references recorded."


def group_turns(
    messages: list[ConversationMessage],
) -> list[tuple[ConversationMessage, list[ConversationMessage]]]:
    turns = []
    prompt = None
    answers: list[ConversationMessage] = []

    for message in messages:
        if message.role == "user":
            if prompt and answers:
                turns.append((prompt, answers))
            prompt, answers = message, []
        elif message.role == "assistant" and prompt:
            answers.append(message)

    if prompt and answers:
        turns.append((prompt, answers))
    return turns


def _summarize_turn_for_llm(
    turn_idx: int, prompt: ConversationMessage, answers: list[ConversationMessage]
) -> dict[str, Any]:
    turn_summary: dict[str, Any] = {
        "turn_index": turn_idx,
        "user_query": prompt.content,
        "assistant_responses": [],
    }

    for ans in answers:
        resp_data: dict[str, Any] = {
            "explanation": clean(ans.content),
            "sql_query": ans.sql_query,
        }

        # Tabular data preview (limit to top 8 rows to control token cost)
        if is_table(ans.results):
            rows = ans.results
            cols = list(rows[0].keys())
            resp_data["data_summary"] = {
                "total_rows": len(rows),
                "columns": cols,
                "preview_rows": rows[:8],
            }

        # Citations preview
        if ans.citations:
            resp_data["citations"] = format_citations(ans.citations)

        turn_summary["assistant_responses"].append(resp_data)

    return turn_summary


def _synthesize_with_gemini(
    turns_payload: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Call Gemini to synthesize conversation turns into an executive report."""
    try:
        llm = ChatGoogleGenerativeAI(
            model=MODEL,
            temperature=0.2,
            timeout=25,
        )

        user_content = json.dumps(
            {"conversation_turns": turns_payload}, default=str, ensure_ascii=False
        )

        logger.info(
            "Invoking Gemini for AI report synthesis (%d turns)...", len(turns_payload)
        )
        response = llm.invoke(
            [
                SystemMessage(content=REPORT_SYNTHESIS_SYSTEM_PROMPT),
                HumanMessage(content=user_content),
            ]
        )

        raw_text = response.content if isinstance(response.content, str) else str(response.content)
        raw_text = raw_text.strip()

        # Strip markdown fences if present
        if raw_text.startswith("```"):
            raw_text = re.sub(r"^```[a-zA-Z]*\n?", "", raw_text)
            raw_text = re.sub(r"\n?```$", "", raw_text).strip()

        parsed = json.loads(raw_text)
        if isinstance(parsed, dict) and "executive_summary" in parsed:
            logger.info("Gemini AI report synthesis successful.")
            return parsed

        logger.warning("Gemini returned invalid report schema: %s", raw_text[:200])
        return None

    except Exception as exc:
        logger.warning("AI report synthesis failed or timed out: %s. Using deterministic fallback.", exc)
        return None


def _deterministic_fallback_report(
    turns: list[tuple[ConversationMessage, list[ConversationMessage]]],
) -> list[ReportSection]:
    """Graceful deterministic fallback if AI synthesis is unavailable."""
    sections: list[ReportSection] = []

    # Overall Summary
    queries = [clean(p.content) for p, _ in turns if p.content]
    summary_text = (
        f"This report covers {len(turns)} analytical inquiry turns: "
        + "; ".join(queries[:4])
        + ("." if len(queries) <= 4 else f", among {len(queries)} total queries.")
    )
    sections.append(
        ReportSection(
            heading="Executive Summary",
            body=summary_text,
            kind="analysis",
        )
    )

    for idx, (prompt, answers) in enumerate(turns, 1):
        heading = clean(prompt.content).strip(" ?.!") or f"Analysis Turn {idx}"
        findings = []
        for ans in answers:
            if ans.content:
                cleaned_ans = clean(ans.content)
                if cleaned_ans:
                    findings.append(cleaned_ans[:300])

        body_lines = ["Key findings:"]
        for f in findings:
            body_lines.append(f"- {f}")

        sections.append(
            ReportSection(
                heading=f"{idx}. {heading}",
                body="\n".join(body_lines),
                kind="analysis",
            )
        )

        # Charts
        visuals = [ans for ans in answers if ans.chart_asset_ids]
        for visual in visuals:
            sections.append(
                ReportSection(
                    heading="Visualization",
                    body="Chart asset generated from the analytical query.",
                    kind="visualization",
                    asset_id=visual.chart_asset_ids[0],
                )
            )

        # Tables
        tables = [ans for ans in answers if is_table(ans.results)]
        for table_ans in tables:
            rows = table_ans.results
            cols = list(rows[0].keys())
            sections.append(
                ReportSection(
                    heading="Data Table",
                    body=f"Supporting dataset ({len(rows)} rows). Showing first {min(len(rows), 8)} sample rows.",
                    kind="table",
                    table_columns=cols[:6],
                    table_rows=rows[:8],
                )
            )

        # Appendix
        for ans in answers:
            if ans.sql_query:
                sections.append(
                    ReportSection(
                        heading="SQL Query",
                        body=f"Query executed for: {heading}\n\n{ans.sql_query}",
                        kind="appendix",
                    )
                )
            if ans.citations:
                sections.append(
                    ReportSection(
                        heading="References",
                        body=f"Source citations for: {heading}\n\n{format_citations(ans.citations)}",
                        kind="appendix",
                    )
                )

    return sections


def build_report(messages: list[ConversationMessage]) -> list[ReportSection]:
    """
    Build a comprehensive, AI-synthesized report from conversation messages.
    Falls back gracefully to deterministic structure upon error.
    """
    turns = group_turns(messages)
    if not turns:
        return [
            ReportSection(
                heading="Executive Summary",
                body="No conversation turns were recorded for this session.",
                kind="analysis",
            )
        ]

    # Compile structured payload for AI synthesis
    turns_payload = [
        _summarize_turn_for_llm(idx, prompt, answers)
        for idx, (prompt, answers) in enumerate(turns)
    ]

    ai_result = _synthesize_with_gemini(turns_payload)
    if not ai_result:
        return _deterministic_fallback_report(turns)

    sections: list[ReportSection] = []

    # 1. Executive Summary
    exec_summary = ai_result.get("executive_summary", "")
    sections.append(
        ReportSection(
            heading="Executive Summary",
            body=exec_summary,
            kind="analysis",
        )
    )

    # 2. Per-Turn Analytical Findings
    turn_analyses = ai_result.get("turn_analyses", [])
    analysis_lookup = {t.get("turn_index"): t for t in turn_analyses if isinstance(t, dict)}

    for idx, (prompt, answers) in enumerate(turns):
        t_data = analysis_lookup.get(idx, {})
        heading = t_data.get("heading") or clean(prompt.content).strip(" ?.!") or f"Analysis {idx + 1}"
        key_findings = t_data.get("key_findings") or []
        narrative = t_data.get("narrative") or ""

        body_parts = []
        if key_findings:
            body_parts.append("Key findings:")
            body_parts.extend([f"- {item}" for item in key_findings])
        if narrative:
            if body_parts:
                body_parts.append("")
            body_parts.append(narrative)

        analysis_body = "\n".join(body_parts) if body_parts else clean(" ".join(a.content for a in answers))

        sections.append(
            ReportSection(
                heading=f"{idx + 1}. {heading}",
                body=analysis_body,
                kind="analysis",
            )
        )

        # Charts associated with this turn
        for ans in answers:
            if ans.chart_asset_ids:
                sections.append(
                    ReportSection(
                        heading=f"Visualization: {heading}",
                        body="The chart below supports this analysis and illustrates the primary trend.",
                        kind="visualization",
                        asset_id=ans.chart_asset_ids[0],
                    )
                )

        # Tables associated with this turn
        for ans in answers:
            if is_table(ans.results):
                rows = ans.results
                cols = list(rows[0].keys())
                sections.append(
                    ReportSection(
                        heading=f"Data Snapshot: {heading}",
                        body=f"Supporting dataset contains {len(rows)} records. Displaying top sample records.",
                        kind="table",
                        table_columns=cols[:6],
                        table_rows=rows[:8],
                    )
                )

    # 3. Strategic Recommendations
    recommendations = ai_result.get("strategic_recommendations") or []
    if recommendations:
        rec_body = "Key recommendations based on observed findings:\n" + "\n".join(
            f"- {r}" for r in recommendations
        )
        sections.append(
            ReportSection(
                heading="Strategic Recommendations",
                body=rec_body,
                kind="analysis",
            )
        )

    # 4. Appendix: Technical queries and citations
    for idx, (prompt, answers) in enumerate(turns, 1):
        heading = clean(prompt.content).strip(" ?.!") or f"Analysis {idx}"
        for ans in answers:
            if ans.sql_query:
                sections.append(
                    ReportSection(
                        heading="SQL Query",
                        body=f"Query for {heading}:\n\n{ans.sql_query}",
                        kind="appendix",
                    )
                )
            if ans.citations:
                sections.append(
                    ReportSection(
                        heading="Document References",
                        body=f"Citations for {heading}:\n\n{format_citations(ans.citations)}",
                        kind="appendix",
                    )
                )

    return sections
