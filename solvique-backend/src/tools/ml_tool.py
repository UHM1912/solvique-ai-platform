"""
ML Tool — Solvique.
Routes ML prediction queries through the LLM-powered orchestrator
to provide regression, classification, and forecasting answers.
"""

import json
import traceback
from langchain_core.tools import tool
from src.logging_config import get_logger
from src.logging_config.logger import Timer
from src.ml_tool_utils.orchestrator import run as ml_run

logger = get_logger(__name__)


@tool
def ml_tool(query: str) -> str:
    """
    Use this tool to answer questions that require predictions, forecasts,
    future estimates, probability scores, risk classifications, or inference
    from a trained machine learning model.

    Supported models:
    - Freight cost prediction (regression)
    - Payment type classification
    - Order volume forecasting

    Args:
        query: The natural language query requesting a prediction or forecast.

    Returns:
        JSON string with the prediction result.
    """
    logger.info(f"ML Tool: Received query: {query[:80]}...")

    with Timer("ml_tool_pipeline") as t:
        try:
            response = ml_run(query)
            result = {
                "status": "success",
                "response": response.get("response"),
                "results": response.get("results", []),
            }
        except Exception as e:
            logger.error(f"ML Tool: Pipeline failed: {e}")
            logger.error(traceback.format_exc())
            result = {
                "status": "error",
                "response": f"ML prediction failed: {str(e)}",
                "results": [],
            }

    logger.info(f"ML Tool: Completed in {t.elapsed:.3f}s (status={result['status']})")
    return json.dumps(result, default=str)
