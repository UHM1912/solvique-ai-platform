/* ═══════════════════════════════════════════════════════
 *  Solvique Chat Interfaces
 *  Matches the FastAPI backend response shapes
 * ═══════════════════════════════════════════════════════ */

/** Request body for POST /api/chat */
export interface ChatRequest {
    query: string;
    conversation_id?: string;
}

export type ToolName =
    | 'sql_tool'
    | 'ml_tool'
    | 'rag_tool'
    | 'rag_tools'
    | 'multi_tool' 
    | 'conversation_memory_tool'
    | 'pre_filter'
    | 'visualize'
    | 'out_of_scope'
    | 'error'
    | 'unknown_tool';
export type ChatResultRow = Record<string, any>;
export type ChatResultsPayload = ChatResultRow[] | string;

export type RagCitationTable = string[][];

export interface RagChunk {
    chunk_id?: string;
    type?: string;
    filename?: string;
    filetype?: string;
    chunk_no?: number;
    total_chunks?: number;
    heading?: string;
    url?: string;
    domain?: string;
    favicon?: string;
    published_date?: string;
    content?: string | RagCitationTable;
}

export interface RagCitation {
    score?: number;
    retrieved_rank?: number;
    chunk?: RagChunk;
}

export type RagCitationPayload = string | RagCitation[];

export interface ChartSpec {
    title: string;
    chart_type: 'line' | 'bar' | 'scatter' | 'histogram' | 'box' | string;
    figure_json: string;
}

export interface VisualizationOption {
    id: string;
    label: string;
    description: string;
    chart_type?: string | null;
    is_custom?: boolean;
    chart_spec?: ChartSpec | null;
}

export interface StatisticalSummaryItem {
    label: string;
    value: string;
}

export interface StoredMessageMetadata {
    source_tool?: ToolName;
    visualization_mode?: 'chart' | 'summary';
    visualization_options?: VisualizationOption[];
    chart_type_options?: VisualizationOption[];
    statistical_summary?: StatisticalSummaryItem[];
    sample_data?: ChatResultRow[];
    sample_message?: string;
    [key: string]: any;
}

export interface VisualizeRequest {
    conversation_id?: string;
    source_tool: 'sql_tool' | 'ml_tool';
    data: ChatResultRow[];
    source_message_id?: string;
    source_patch_index?: number;
    chart_type?: string;
}

export interface VisualizeResponse {
    source_tool: 'sql_tool' | 'ml_tool';
    summary?: string;
    chart_specs: ChartSpec[];
    visualization_options?: VisualizationOption[];
    chart_type_options?: VisualizationOption[];
    statistical_summary?: StatisticalSummaryItem[];
    sample_data?: ChatResultRow[];
    sample_message?: string;
    visualization_mode?: 'chart' | 'summary';
    error?: string;
}

export type ReportAssetType = 'chart' | 'image' | 'table_snapshot';
export type ReportSectionType = 'insight' | 'chart' | 'table_summary' | 'appendix';

export interface ReportAssetItem {
    asset_id: string;
    message_id: string;
    type: ReportAssetType;
    title: string;
    mime_type: string;
    file_url: string;
    object_path: string;
    metadata?: Record<string, any>;
}

export interface ReportTableSummary {
    message_id: string;
    row_count: number;
    column_count: number;
    columns: string[];
    sample_rows: ChatResultRow[];
    sample_truncated: boolean;
}

export interface ReportMessageItem {
    message_id: string;
    role: 'user' | 'assistant';
    tool?: string | null;
    created_at?: string | null;
    content: string;
    sql_query?: string | null;
    citations?: any;
    table_summary?: ReportTableSummary | null;
    chart_asset_ids: string[];
}

export interface ConversationReportPayload {
    conversation_id: string;
    created_at: string;
    assets: ReportAssetItem[];
    messages: ReportMessageItem[];
}

export interface ReportPlanSection {
    type: ReportSectionType;
    heading: string;
    body: string;
    asset_id?: string | null;
    message_id?: string | null;
}

export interface ReportPlan {
    title: string;
    summary: string;
    sections: ReportPlanSection[];
}

/** Response from POST /api/chat */
export interface ChatResponse {
    conversation_id: string;
    message_id?: string;
    tool: ToolName;
    explanation?: string;
    sql_query?: string;
    results?: ChatResultsPayload;
    citations?: RagCitationPayload;
    doc_citations?: RagCitationPayload;   // ← add
    web_citations?: RagCitationPayload;   // ← add
    metadata?: StoredMessageMetadata;
    error?: string;
    tool_results?: MultiToolResult[];
}

// Add this new interface
export interface MultiToolResult {
    tool: ToolName;
    explanation?: string;
    sql_query?: string;
    results?: ChatResultsPayload;
    citations?: RagCitationPayload;
    doc_citations?: RagCitationPayload;
    web_citations?: RagCitationPayload;
    chart_specs?: ChartSpec[];
    visualization_options?: VisualizationOption[];
    chart_type_options?: VisualizationOption[];
    statistical_summary?: StatisticalSummaryItem[];
    sample_data?: ChatResultRow[];
    sample_message?: string;
    visualization_mode?: 'chart' | 'summary';
    error?: string;
}

/** Summary returned by GET /api/conversations */
export interface ConversationSummary {
    id: string;
    title: string;
    created: string;
}

/** Detail returned by GET /api/conversations/:id */
export interface ConversationDetail {
    id: string;
    created: string;
    messages: StoredMessage[];
}

/** A message as stored in the backend database */
export interface StoredMessage {
    id?: string;
    role: 'user' | 'assistant';
    content: string;
    tool?: ToolName;
    sql_query?: string;
    dataframe?: ChatResultsPayload;
    citations?: RagCitationPayload;
    doc_citations?: RagCitationPayload;   // ← add
    web_citations?: RagCitationPayload;   // ← add
    tool_results?: MultiToolResult[];
    chart_specs?: ChartSpec[];
    metadata?: StoredMessageMetadata;
    created_at?: string;
}

/* ─── Frontend-only types ────────────────────────────── */

/** A chat message in the frontend UI */
export interface ChatMessage {
    id: string;
    conversationId?: string;
    sender: 'user' | 'assistant';
    text: string;
    rawText?: string;
    timestamp: Date;
    tool?: ToolName;
    sqlQuery?: string;
    results?: ChatResultsPayload;
    citations?: RagCitationPayload;
    metadata?: StoredMessageMetadata;
    error?: string;
    isTyping?: boolean;
    renderComplete?: boolean;
    canVisualize?: boolean;
    visualizationData?: ChatResultRow[];
    visualizationLoading?: boolean;
    visualizationError?: string;
    visualizationSummary?: string;
    visualizationChartId?: string;
    chartSpecs?: ChartSpec[];
    primaryVisualizationChartSpec?: ChartSpec;
    visualizationOptions?: VisualizationOption[];
    chartTypeOptions?: VisualizationOption[];
    selectedVisualizationOptionId?: string;
    visualizationStats?: StatisticalSummaryItem[];
    visualizationSampleData?: ChatResultRow[];
    visualizationSampleMessage?: string;
    visualizationMode?: 'chart' | 'summary';
    doc_citations?: RagCitationPayload;
    web_citations?: RagCitationPayload;
    tool_results?: MultiToolResult[];
}

/** A chat session in the frontend */
export interface ChatSession {
    id: string;
    title: string;
    createdAt: Date;
    messages: ChatMessage[];
    isTyping?: boolean;
}

/** Sidebar chat summary */
export interface ChatSummary {
    id: string;
    title: string;
    lastMessageAt: string;
    selected?: boolean;
}

/** Payload emitted by chat-input */
export interface ChatSendPayload {
    text: string;
}

/** Redesigned Solvique Views */
export type SolviqueView = 'assistant' | 'studio' | 'reports';

/** Backend executive report section */
export interface ReportSection {
    heading: string;
    body: string;
    kind: 'analysis' | 'visualization' | 'table' | 'appendix';
    asset_id?: string | null;
    table_columns?: string[];
    table_rows?: Record<string, any>[];
}

