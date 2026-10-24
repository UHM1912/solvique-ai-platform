import ast
import json
from typing import Any

PAYLOAD_KEYS = ("summary", "chart_specs", "visualization_options", "chart_type_options")
ANCHORS = tuple(f"{quote}{key}{quote}" for key in PAYLOAD_KEYS for quote in ('"', "'"))


def empty_payload() -> dict[str, Any]:
    return {
        "summary": None,
        "chart_specs": [],
        "visualization_options": [],
        "chart_type_options": [],
        "visualization_mode": "chart",
    }


def is_plotly_figure(obj: Any) -> bool:
    return (
        isinstance(obj, dict)
        and isinstance(obj.get("data"), list)
        and isinstance(obj.get("layout"), dict)
    )


def _normalize_chart_spec(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None

    title = str(value.get("title") or "Generated Visualization")
    chart_type = str(value.get("chart_type") or "chart")
    figure_json = value.get("figure_json")

    if not isinstance(figure_json, str):
        return None

    try:
        parsed = json.loads(figure_json)
        if not is_plotly_figure(parsed):
            return None
    except json.JSONDecodeError:
        return None

    return {
        "title": title,
        "chart_type": chart_type,
        "figure_json": figure_json,
    }


def normalize_options(options: Any, limit: int = 4) -> list[dict[str, Any]]:
    if not isinstance(options, list):
        return []

    normalized = []
    for idx, option in enumerate(
        option for option in options if isinstance(option, dict)
    ):
        option_id = str(option.get("id") or f"option_{idx + 1}")
        normalized.append(
            {
                "id": option_id,
                "label": str(
                    option.get("label") or option_id.replace("_", " ").title()
                ),
                "description": str(option.get("description") or ""),
                "chart_type": option.get("chart_type"),
                "is_custom": bool(option.get("is_custom", False)),
                "chart_spec": _normalize_chart_spec(option.get("chart_spec")),
            }
        )

    return [option for option in normalized if not option["is_custom"]][:limit]


def normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    specs = payload.get("chart_specs") or []
    return {
        "summary": payload.get("summary"),
        "chart_specs": [specs]
        if isinstance(specs, dict)
        else specs
        if isinstance(specs, list)
        else [],
        "visualization_options": normalize_options(
            payload.get("visualization_options"), limit=3
        ),
        "chart_type_options": normalize_options(
            payload.get("chart_type_options"), limit=3
        ),
        "visualization_mode": payload.get("visualization_mode", "chart"),
    }


def has_content(payload: dict[str, Any]) -> bool:
    return bool(
        payload.get("chart_specs")
        or payload.get("visualization_options")
        or payload.get("chart_type_options")
        or payload.get("summary") is not None
    )


def has_valid_chart(payload: dict[str, Any]) -> bool:
    for spec in payload.get("chart_specs", []):
        figure_json = spec.get("figure_json", "") if isinstance(spec, dict) else ""
        try:
            if isinstance(figure_json, str) and is_plotly_figure(
                json.loads(figure_json)
            ):
                return True
        except json.JSONDecodeError:
            pass
    return False


def coerce_plotly_payload(raw: Any, summary: str | None = None) -> dict[str, Any]:
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return empty_payload()
    if not is_plotly_figure(raw):
        return empty_payload()

    title = raw.get("layout", {}).get("title", "")
    title = title.get("text", "") if isinstance(title, dict) else str(title)
    return {
        "summary": summary,
        "chart_specs": [
            {
                "title": title or "Generated Visualization",
                "chart_type": raw["data"][0].get("type", "chart"),
                "figure_json": json.dumps(raw),
            }
        ],
        "visualization_options": [],
        "chart_type_options": [],
        "visualization_mode": "chart",
    }


def parse_once(text: str) -> Any:
    for parser in (json.loads, ast.literal_eval):
        try:
            return parser(text)
        except (json.JSONDecodeError, SyntaxError, ValueError):
            pass
    return None


def extract_balanced_object(text: str, anchor: str) -> str | None:
    anchor_pos = text.find(anchor)
    start = text.rfind("{", 0, anchor_pos)
    if anchor_pos == -1 or start == -1:
        return None

    depth, in_string, escape, quote_char = 0, False, False, ""
    for idx, char in enumerate(text[start:], start):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == quote_char:
                in_string = False
        elif char in ('"', "'"):
            in_string, quote_char = True, char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return None


def first_useful_payload(candidates: list[Any]) -> dict[str, Any]:
    for candidate in candidates:
        result = extract_json_block(candidate)
        if has_content(result):
            return result
    return empty_payload()


def extract_json_block(payload: Any) -> dict[str, Any]:
    if payload is None:
        return empty_payload()

    if isinstance(payload, dict):
        if any(key in payload for key in PAYLOAD_KEYS):
            return normalize_payload(payload)
        return first_useful_payload(
            [payload.get(key) for key in ("text", "output", "content")]
        )

    if isinstance(payload, list):
        return first_useful_payload(payload)

    if not isinstance(payload, str) or not payload.strip():
        return empty_payload()

    text = payload.strip()
    candidates = [parse_once(text)]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(parse_once(text[start : end + 1]))
    candidates.extend(extract_balanced_object(text, anchor) for anchor in ANCHORS)

    result = first_useful_payload(
        [candidate for candidate in candidates if candidate is not None]
    )
    return result if has_content(result) else {**empty_payload(), "summary": text}


def extract_observation(step: Any) -> Any:
    if isinstance(step, (list, tuple)) and len(step) >= 2:
        return step[1]
    if isinstance(step, dict):
        return step.get("observation") or step.get("output")
    return None


def extract_from_agent_response(response: dict[str, Any]) -> dict[str, Any]:
    parsed = extract_json_block(response.get("output", ""))
    if has_valid_chart(parsed):
        return parsed

    fallback_summary = parsed.get("summary")
    fallback_options = parsed.get("visualization_options", [])
    fallback_chart_type_options = parsed.get("chart_type_options", [])

    for observation in filter(
        None, map(extract_observation, response.get("intermediate_steps", []))
    ):
        obs_payload = extract_json_block(observation)
        fallback_summary = fallback_summary or obs_payload.get("summary")
        fallback_options = fallback_options or obs_payload.get(
            "visualization_options", []
        )
        fallback_chart_type_options = fallback_chart_type_options or obs_payload.get(
            "chart_type_options", []
        )

        for candidate in (
            obs_payload,
            coerce_plotly_payload(observation, fallback_summary),
        ):
            if has_valid_chart(candidate):
                candidate["summary"] = candidate.get("summary") or fallback_summary
                candidate["visualization_options"] = (
                    candidate.get("visualization_options") or fallback_options
                )
                candidate["chart_type_options"] = (
                    candidate.get("chart_type_options") or fallback_chart_type_options
                )
                return candidate

    parsed["visualization_options"] = (
        parsed.get("visualization_options") or fallback_options
    )
    parsed["chart_type_options"] = (
        parsed.get("chart_type_options") or fallback_chart_type_options
    )
    return parsed
