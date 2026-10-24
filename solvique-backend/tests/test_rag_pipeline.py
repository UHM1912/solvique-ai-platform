import pytest

from src.tools.rag_tool import _extract_text, _parse_decomposition
from unittest.mock import patch

from src.ml_tool_utils import orchestrator


def test_extract_text_reads_all_text_parts():
    assert _extract_text([{"type": "text", "text": "{\"doc_answer\":"}, {"text": "null}"}]) == '{"doc_answer":null}'


def test_parse_decomposition_accepts_fenced_json():
    assert _parse_decomposition('```json\n{"doc_answer":"Grounded answer","web_query":null}\n```') == {
        "doc_answer": "Grounded answer",
        "web_query": None,
    }


@pytest.mark.parametrize("raw", ["", "not json", "{}"])
def test_parse_decomposition_rejects_empty_or_invalid_response(raw):
    with pytest.raises((ValueError, __import__("json").JSONDecodeError)):
        _parse_decomposition(raw)


def test_explicit_category_examples_bypass_llm_routing():
    manifest = {"task": "classification"}
    prediction = {"predicted_class": "test_category", "probabilities": {}}
    features = {"price": {"value": 50, "source": "QUERY"}}
    query = "Predict categories for a 200g 50 BRL item and a 2000g 900 BRL item"

    with patch.object(orchestrator, "get_manifest", return_value=manifest), patch.object(
        orchestrator, "run_inference", return_value=(prediction, features)
    ) as infer, patch.object(orchestrator, "_call_llm") as route_llm:
        result = orchestrator.run(query)

    assert "test_category" in result["response"]
    assert result["response"].count("Item 1 (200 g, 50 BRL)") == 1
    assert result["response"].count("Item 2 (2000 g, 900 BRL)") == 1
    assert infer.call_count == 2
    route_llm.assert_not_called()
