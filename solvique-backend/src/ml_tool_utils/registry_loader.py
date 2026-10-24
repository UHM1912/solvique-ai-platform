"""
registry_loader.py
------------------
Loads all manifest files from the registry directory and provides
lookup functions for individual models and imputer statistics.

Adapted from ML_TOOL/registry/registry_loader.py for Solvique backend integration.
"""

import json
from pathlib import Path
from src.logging_config import get_logger

logger = get_logger(__name__)

REGISTRY_DIR = Path(__file__).parent / "registry"


def load_registry(registry_dir: Path = REGISTRY_DIR) -> list[dict]:
    """
    Walk the registry folder and load every manifest.json into a list.
    Returns a list of manifest dicts — one per registered model.
    """
    manifests = []

    for folder in sorted(registry_dir.iterdir()):
        if not folder.is_dir():
            continue
        manifest_path = folder / "manifest.json"
        if not manifest_path.exists():
            continue
        with open(manifest_path) as f:
            manifest = json.load(f)
        manifests.append(manifest)
        logger.info(f"[Registry] Loaded: {manifest['model_id']}  ({manifest['task']})")

    logger.info(f"[Registry] Total models loaded: {len(manifests)}")
    return manifests


def build_registry_context(manifests: list[dict]) -> str:
    """
    Convert the list of manifests into a plain text block
    that gets injected into the LLM system prompt.
    """
    lines = ["AVAILABLE MODELS:\n"]

    for m in manifests:
        hints = m.get("llm_hints", {})
        schema = m.get("feature_schema", {})

        lines.append(f"MODEL: {m['model_id']}")
        lines.append(f"TASK: {m['task']}")
        lines.append(f"DOMAIN: {m['domain']}")
        lines.append(f"DESCRIPTION: {m['description']}")

        triggers = ", ".join(hints.get("trigger_phrases", []))
        lines.append(f"TRIGGERS: {triggers}")

        entity_keys = ", ".join(hints.get("entity_map", {}).keys())
        lines.append(f"FEATURES: {entity_keys}")

        output = m.get("output_config", {})
        lines.append(f"OUTPUT_UNIT: {output.get('units', 'N/A')}")

        lines.append("---")

    return "\n".join(lines)


def get_manifest(model_id: str, registry_dir: Path = REGISTRY_DIR) -> dict:
    """
    Load and return the manifest for a specific model_id.
    Used after the LLM has selected a model.
    """
    manifest_path = registry_dir / model_id / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"No manifest found for model_id='{model_id}'. Expected at: {manifest_path}"
        )
    with open(manifest_path) as f:
        return json.load(f)


def get_imputer_stats(model_id: str, registry_dir: Path = REGISTRY_DIR) -> dict:
    """
    Load the imputer_stats.json for a given model.
    Used by the preprocessing pipeline to fill missing feature values.
    """
    imputer_path = registry_dir / model_id / "artifacts" / "imputer_stats.json"
    if not imputer_path.exists():
        raise FileNotFoundError(
            f"No imputer_stats found for model_id='{model_id}'. "
            f"Expected at: {imputer_path}"
        )
    with open(imputer_path) as f:
        return json.load(f)
