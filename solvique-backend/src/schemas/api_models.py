from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None


class ChatResponse(BaseModel):
    conversation_id: str
    message_id: Optional[str] = None
    tool: str
    explanation: Optional[str] = None
    citations: Optional[Union[str, list[Any], dict[str, Any]]] = None
    doc_citations: Optional[Union[str, list[Any], dict[str, Any]]] = None  # ← add
    web_citations: Optional[Union[str, list[Any], dict[str, Any]]] = None
    metadata: Optional[dict[str, Any]] = None
    sql_query: Optional[str] = None
    results: Optional[Union[list[Any], str]] = None
    error: Optional[str] = None
    tool_results: Optional[list[dict[str, Any]]] = None


class ConversationSummary(BaseModel):
    id: str
    title: str
    created: str


class ConversationDetail(BaseModel):
    id: str
    created: str
    messages: list


class VisualizationOption(BaseModel):
    id: str
    label: str
    description: str
    chart_type: Optional[str] = None
    is_custom: bool = False
    chart_spec: Optional[dict[str, Any]] = None


class VisualizeRequest(BaseModel):
    conversation_id: Optional[str] = None
    source_tool: str
    data: list[dict[str, Any]]
    source_message_id: Optional[str] = None
    source_patch_index: Optional[int] = None
    chart_type: Optional[str] = None


class VisualizeResponse(BaseModel):
    source_tool: str
    summary: Optional[str] = None
    chart_specs: list[dict[str, Any]] = Field(default_factory=list)
    visualization_options: list[VisualizationOption] = Field(default_factory=list)
    chart_type_options: list[VisualizationOption] = Field(default_factory=list)
    statistical_summary: list[dict[str, Any]] = Field(default_factory=list)
    sample_data: list[dict[str, Any]] = Field(default_factory=list)
    sample_message: Optional[str] = None
    visualization_mode: str = "chart"
    error: Optional[str] = None


class ConversationMessage(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    content: str = ""
    sql_query: Optional[str] = None
    results: Optional[Any] = None
    citations: Optional[Any] = None
    doc_citations: Optional[Any] = None  # ← add
    web_citations: Optional[Any] = None  # ← add
    chart_asset_ids: list[str] = Field(default_factory=list)


class ReportSection(BaseModel):
    heading: str
    body: str
    kind: Literal["analysis", "visualization", "table", "appendix"] = "analysis"
    asset_id: Optional[str] = None
    table_columns: list[str] = Field(default_factory=list)
    table_rows: list[dict[str, Any]] = Field(default_factory=list)
