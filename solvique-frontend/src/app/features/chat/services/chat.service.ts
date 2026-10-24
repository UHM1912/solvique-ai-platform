import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { lastValueFrom } from 'rxjs';
import { environment } from '../../../../environments/environment';
import {
    ChatRequest,
    ChatResponse,
    ConversationSummary,
    ConversationDetail,
    ChatSession,
    ChatMessage,
    StoredMessage,
    ChatResultRow,
    VisualizeRequest,
    VisualizeResponse,
    ReportSection
} from '../../../shared/interfaces/chat.interface';

@Injectable({
    providedIn: 'root'
})
export class ChatService {

    private API = environment.apiBaseUrl;

    constructor(private http: HttpClient) {}

    /* ─── Send a chat query ──────────────────────────────── */
    async sendMessage(query: string, conversationId: string): Promise<ChatResponse[]> {
        const body: ChatRequest = { query, conversation_id: conversationId };
        const resp = await lastValueFrom(
            this.http.post<ChatResponse | ChatResponse[]>(`${this.API}/api/chat`, body)
        );
        return Array.isArray(resp) ? resp : [resp];
    }

    async generateVisualization(
        conversationId: string | undefined,
        sourceTool: 'sql_tool' | 'ml_tool',
        data: ChatResultRow[],
        options?: {
            sourceMessageId?: string;
            sourcePatchIndex?: number;
            chartType?: string;
        }
    ): Promise<VisualizeResponse> {
        const body: VisualizeRequest = {
            conversation_id: conversationId,
            source_tool: sourceTool,
            data,
            source_message_id: options?.sourceMessageId,
            source_patch_index: options?.sourcePatchIndex,
            chart_type: options?.chartType,
        };

        return await lastValueFrom(
            this.http.post<VisualizeResponse>(`${this.API}/api/visualize`, body)
        );
    }

    /* ─── List conversations ─────────────────────────────── */
    async getConversations(): Promise<ConversationSummary[]> {
        try {
            return await lastValueFrom(
                this.http.get<ConversationSummary[]>(`${this.API}/api/conversations`)
            );
        } catch {
            return [];
        }
    }

    /* ─── Get single conversation ────────────────────────── */
    async getConversation(id: string): Promise<ConversationDetail | null> {
        try {
            return await lastValueFrom(
                this.http.get<ConversationDetail>(`${this.API}/api/conversations/${id}`)
            );
        } catch {
            return null;
        }
    }

    /* ─── Delete conversation ────────────────────────────── */
    async deleteConversation(id: string): Promise<boolean> {
        try {
            await lastValueFrom(
                this.http.delete(`${this.API}/api/conversations/${id}`)
            );
            return true;
        } catch {
            return false;
        }
    }

    /* ─── Report download and preview URLs ───────────────── */
    getReportDownloadUrl(conversationId: string): string {
        return `${this.API}/api/conversations/${conversationId}/report.docx`;
    }

    async getReportPreview(conversationId: string): Promise<ReportSection[]> {
        try {
            return await lastValueFrom(
                this.http.get<ReportSection[]>(`${this.API}/api/conversations/${conversationId}/report/preview`)
            );
        } catch {
            return [];
        }
    }

    getReportAssetUrl(assetId: string): string {
        return `${this.API}/api/report-assets/${assetId}`;
    }


    mapStoredMessages(stored: StoredMessage[], conversationId: string): ChatMessage[] {
        return stored.map((msg, idx) => {
            const id = msg.id || `${conversationId}-${idx}`;
            const text = this.getDisplayText(msg.content, msg.dataframe);
            const chartSpecs = msg.chart_specs || [];

            return {
                id,
                conversationId,
                sender: msg.role,
                text,
                rawText: text || undefined,
                timestamp: msg.created_at ? new Date(msg.created_at) : new Date(),
                tool: msg.tool,
                sqlQuery: msg.sql_query,
                results: msg.dataframe,
                citations: msg.citations,
                doc_citations: msg.doc_citations,   // ← add
                web_citations: msg.web_citations,   // ← add
                tool_results: msg.tool_results || msg.metadata?.['tool_results'] || [],
                metadata: msg.metadata,
                chartSpecs,
                primaryVisualizationChartSpec: chartSpecs.length ? chartSpecs[0] : undefined,
                visualizationOptions: msg.metadata?.visualization_options || [],
                chartTypeOptions: msg.metadata?.chart_type_options || [],
                selectedVisualizationOptionId: chartSpecs.length ? 'primary_chart_option' : undefined,
                visualizationSummary: chartSpecs.length ? msg.content : undefined,
                visualizationChartId: chartSpecs.length ? `viz-chart-${id}` : undefined,
                visualizationStats: msg.metadata?.statistical_summary || [],
                visualizationSampleData: msg.metadata?.sample_data || [],
                visualizationSampleMessage: msg.metadata?.sample_message || '',
                visualizationMode: msg.metadata?.visualization_mode || 'chart',
                renderComplete: true,
            };
        });
    }

    private getDisplayText(content: string, results?: StoredMessage['dataframe']): string {
        if (content) {
            return this.normalizeResponseText(content);
        }

        if (typeof results === 'string') {
            return this.normalizeResponseText(results);
        }

        return '';
    }

    private normalizeResponseText(value: unknown): string {
        if (typeof value === 'string') {
            const trimmed = value.trim();
            if (!trimmed) {
                return '';
            }

            const extractedPythonStructuredText = this.extractTextFromPythonStructuredPayload(trimmed);
            if (extractedPythonStructuredText) {
                return extractedPythonStructuredText;
            }

            const parsedJsonText = this.tryExtractTextFromJson(trimmed);
            if (parsedJsonText) {
                return parsedJsonText;
            }

            const extractedStructuredText = this.extractTextFromStructuredString(trimmed);
            return extractedStructuredText || trimmed;
        }

        if (Array.isArray(value)) {
            return value
                .map(item => this.normalizeResponseText(item))
                .filter(Boolean)
                .join('\n\n')
                .trim();
        }

        if (value && typeof value === 'object') {
            const record = value as Record<string, unknown>;

            if (typeof record['text'] === 'string') {
                return record['text'];
            }

            if (typeof record['image_url'] === 'string') {
                return record['image_url'];
            }

            if (Array.isArray(record['content'])) {
                return this.normalizeResponseText(record['content']);
            }

            return Object.values(record)
                .map(item => this.normalizeResponseText(item))
                .filter(Boolean)
                .join('\n\n')
                .trim();
        }

        return '';
    }

    private extractTextFromPythonStructuredPayload(value: string): string {
        const keyIndex = value.indexOf(`'text':`);
        if (keyIndex === -1) {
            return '';
        }

        const afterKey = value.slice(keyIndex + `'text':`.length).trimStart();
        const quote = afterKey[0];
        if (quote !== '\'' && quote !== '"') {
            return '';
        }

        let content = '';
        let escaped = false;
        for (let idx = 1; idx < afterKey.length; idx += 1) {
            const ch = afterKey[idx];

            if (escaped) {
                content += ch;
                escaped = false;
                continue;
            }

            if (ch === '\\') {
                escaped = true;
                continue;
            }

            if (ch === quote) {
                return content
                    .replace(/\\n/g, '\n')
                    .replace(/\\r/g, '')
                    .replace(/\\t/g, '\t')
                    .replace(/\\"/g, '"')
                    .replace(/\\'/g, '\'')
                    .trim();
            }

            content += ch;
        }

        return '';
    }

    private tryExtractTextFromJson(value: string): string | null {
        if (!((value.startsWith('{') && value.endsWith('}')) || (value.startsWith('[') && value.endsWith(']')))) {
            return null;
        }

        try {
            const parsed = JSON.parse(value);
            const normalized = this.normalizeResponseText(parsed);
            return normalized || null;
        } catch {
            return null;
        }
    }

    private extractTextFromStructuredString(value: string): string {
        const patterns = [
            /['"]text['"]\s*:\s*'([\s\S]*?)'\s*(?=,\s*['"](?:extras|type|signature|metadata)['"]|\s*[}\]])/g,
            /['"]text['"]\s*:\s*"([\s\S]*?)"\s*(?=,\s*['"](?:extras|type|signature|metadata)['"]|\s*[}\]])/g,
        ];

        const extracted: string[] = [];
        for (const pattern of patterns) {
            const matches = Array.from(value.matchAll(pattern));
            for (const match of matches) {
                const normalized = (match[1] || '')
                    .replace(/\\n/g, '\n')
                    .replace(/\\r/g, '')
                    .replace(/\\t/g, '\t')
                    .replace(/\\"/g, '"')
                    .replace(/\\'/g, '\'')
                    .trim();
                if (normalized) {
                    extracted.push(normalized);
                }
            }
            if (extracted.length > 0) {
                break;
            }
        }

        if (extracted.length === 0) {
            return '';
        }

        const joined = extracted.join('\n\n').trim();
        if (!joined) {
            return '';
        }

        if (value.includes(`'text'`) || value.includes(`"text"`)) {
            const minExpectedLength = Math.max(40, Math.floor(value.length * 0.08));
            if (joined.length < minExpectedLength) {
                return '';
            }
        }

        return joined;
    }

}
