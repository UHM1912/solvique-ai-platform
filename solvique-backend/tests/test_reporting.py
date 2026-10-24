"""
Unit and integration tests for AI-powered and fallback report generation.
Verifies Phase 2 requirements:
- Genuine AI-assisted report synthesis with structured output
- Graceful deterministic fallback on AI timeout or failure
- Grounded reflection of SQL, ML, RAG, and Multi-tool turns
- Preserved DOCX rendering pipeline producing valid Word documents
"""

from io import BytesIO
from unittest.mock import MagicMock, patch
import docx
import pytest

from src.reporting.report_builder import (
    _deterministic_fallback_report,
    _summarize_turn_for_llm,
    _synthesize_with_gemini,
    build_report,
    format_citations,
    group_turns,
)
from src.reporting.report_files import ReportDocxRenderer
from src.schemas.api_models import ConversationMessage, ReportSection


def test_format_citations_handles_rag_and_web():
    """Verify format_citations formats document chunks and web URLs cleanly."""
    citations = [
        {
            "chunk": {
                "filename": "Ecommerce_Business_Insights.pdf",
                "heading": "Customer Retention Policies",
            }
        },
        {
            "title": "Brazilian Logistics Guide",
            "url": "https://example.com/logistics",
        },
    ]
    formatted = format_citations(citations)
    assert "Document: Ecommerce_Business_Insights.pdf" in formatted
    assert "Section: Customer Retention Policies" in formatted
    assert "Web Source: Brazilian Logistics Guide (https://example.com/logistics)" in formatted


def test_summarize_turn_for_llm_truncates_large_tables():
    """Verify tabular results are summarized and truncated to 8 rows for token cost control."""
    prompt = ConversationMessage(id="p1", role="user", content="Show monthly sales")
    rows = [{"month": f"2017-{i:02d}", "revenue": i * 1000} for i in range(1, 25)]
    answer = ConversationMessage(
        id="a1",
        role="assistant",
        content="Here are the sales numbers.",
        sql_query="SELECT month, revenue FROM orders",
        results=rows,
    )
    turn_summary = _summarize_turn_for_llm(0, prompt, [answer])
    assert turn_summary["turn_index"] == 0
    assert turn_summary["user_query"] == "Show monthly sales"
    resp = turn_summary["assistant_responses"][0]
    assert resp["data_summary"]["total_rows"] == 24
    assert len(resp["data_summary"]["preview_rows"]) == 8  # Truncated to 8 for token savings
    assert resp["sql_query"] == "SELECT month, revenue FROM orders"


def test_deterministic_fallback_report():
    """Verify deterministic fallback produces structured sections when LLM is offline."""
    prompt = ConversationMessage(id="p1", role="user", content="What was the total order count?")
    answer = ConversationMessage(
        id="a1",
        role="assistant",
        content="Total orders were 99,441 with an average ticket of R$ 137.",
        sql_query="SELECT COUNT(1) AS total FROM orders",
        results=[{"total": 99441}],
    )
    turns = [(prompt, [answer])]
    sections = _deterministic_fallback_report(turns)

    headings = [s.heading for s in sections]
    assert "Executive Summary" in headings
    assert any("What was the total order count" in h for h in headings)
    assert "Data Table" in headings
    assert "SQL Query" in headings

    # Verify data table section has columns and rows
    table_sec = next(s for s in sections if s.kind == "table")
    assert table_sec.table_columns == ["total"]
    assert table_sec.table_rows == [{"total": 99441}]


def test_ai_synthesis_flow_with_mocked_gemini():
    """Verify build_report integrates Gemini synthesis when LLM returns valid structured JSON."""
    mock_ai_response = {
        "executive_summary": "The analysis demonstrates strong quarterly expansion across Brazilian e-commerce regions.",
        "turn_analyses": [
            {
                "turn_index": 0,
                "heading": "Regional Revenue Growth (2017)",
                "key_findings": [
                    "Southeast region captured 68% of total gross merchandise value.",
                    "Average ticket size remained steady at R$ 142.50 across credit card transactions.",
                ],
                "narrative": "Detailed breakdown shows that Sao Paulo and Rio de Janeiro remain primary demand hubs.",
            }
        ],
        "strategic_recommendations": [
            "Optimize regional fulfillment hubs to reduce transit times in northern corridors.",
            "Incentivize upfront payment methods to decrease chargeback frequency.",
        ],
    }

    prompt = ConversationMessage(id="p1", role="user", content="Analyze regional sales")
    answer = ConversationMessage(
        id="a1",
        role="assistant",
        content="Sales in the Southeast region totaled R$ 8.2M.",
        results=[{"region": "Southeast", "revenue": 8200000}],
        sql_query="SELECT region, SUM(value) FROM sales GROUP BY region",
    )

    with patch("src.reporting.report_builder._synthesize_with_gemini", return_value=mock_ai_response):
        sections = build_report([prompt, answer])

    headings = [s.heading for s in sections]
    assert "Executive Summary" in headings
    assert "1. Regional Revenue Growth (2017)" in headings
    assert "Strategic Recommendations" in headings
    assert "SQL Query" in headings

    # Verify content in analysis section
    analysis_sec = next(s for s in sections if s.heading == "1. Regional Revenue Growth (2017)")
    assert "Key findings:" in analysis_sec.body
    assert "Southeast region captured 68%" in analysis_sec.body
    assert "Sao Paulo and Rio de Janeiro" in analysis_sec.body

    # Verify recommendations
    rec_sec = next(s for s in sections if s.heading == "Strategic Recommendations")
    assert "Optimize regional fulfillment hubs" in rec_sec.body


def test_docx_renderer_produces_valid_docx_binary():
    """Verify ReportDocxRenderer takes ReportSection objects and renders a valid, openable .docx binary."""
    sections = [
        ReportSection(
            heading="Executive Summary",
            body="Overall e-commerce operations expanded by 14% year over year.",
            kind="analysis",
        ),
        ReportSection(
            heading="1. Order Volume Analysis",
            body="Key findings:\n- Order volume peaked in November during Black Friday.\n- Average daily volume exceeded 400 orders.",
            kind="analysis",
        ),
        ReportSection(
            heading="Data Snapshot",
            body="Top performing categories.",
            kind="table",
            table_columns=["category", "order_count"],
            table_rows=[{"category": "bed_bath_table", "order_count": 11115}, {"category": "health_beauty", "order_count": 9670}],
        ),
        ReportSection(
            heading="SQL Query",
            body="SELECT category, COUNT(*) FROM orders GROUP BY category",
            kind="appendix",
        ),
    ]

    renderer = ReportDocxRenderer()
    docx_bytes = renderer.render(sections)
    assert isinstance(docx_bytes, bytes)
    assert len(docx_bytes) > 1000

    # Verify with python-docx that document structure is valid
    doc = docx.Document(BytesIO(docx_bytes))
    paragraphs_text = [p.text for p in doc.paragraphs]
    assert any("Executive Summary" in t for t in paragraphs_text)
    assert any("1. Order Volume Analysis" in t for t in paragraphs_text)

    # Verify table in docx
    assert len(doc.tables) >= 1
    table_cells = [cell.text for t in doc.tables for row in t.rows for cell in row.cells]
    assert any("Category" in c or "Bed Bath Table" in c or "bed_bath_table" in c for c in table_cells)


def test_empty_conversation_returns_graceful_summary():
    """Verify empty message list produces a valid fallback section without erroring."""
    sections = build_report([])
    assert len(sections) == 1
    assert sections[0].heading == "Executive Summary"
    assert "No conversation turns" in sections[0].body
