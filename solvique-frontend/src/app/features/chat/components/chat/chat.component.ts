import { Component, ElementRef, Input, Output, EventEmitter, ViewChild, AfterViewChecked, ViewChildren, QueryList } from '@angular/core';
import { CommonModule } from '@angular/common';
import { LucideAngularModule, Database, Bot, AlertCircle, Ban, ChevronDown, ChevronUp, User, Copy, Check, Download, ChartColumn, ChartLine, ChartScatter, ChartArea, ChartPie, ChartNoAxesCombined } from 'lucide-angular';
import {
    ChatMessage,
    ChatResultRow,
    RagCitation,
    RagCitationPayload,
    RagCitationTable,
    ToolName,
    ChartSpec,
    VisualizationOption,
    StatisticalSummaryItem,
    MultiToolResult,

} from '../../../../shared/interfaces/chat.interface';
import { MarkedPipe } from '../../../../shared/pipes/marked.pipe';
import { ChatService } from '../../services/chat.service';
import { ThemeService } from '../../../../core/services/theme.service';
import Plotly from 'plotly.js-dist-min';
import { format } from 'sql-formatter';
import Prism from 'prismjs';
import 'prismjs/components/prism-sql';

interface RenderableRagTable {
    title: string;
    source?: string;
    headers: string[];
    rows: string[][];
}

interface ParsedRagMessageContent {
    narrativeText: string;
    fallbackCitations: string[];
    tables: RenderableRagTable[];
}

type PlotlyTypedArrayPayload = {
    dtype: string;
    bdata: string;
    shape?: number | number[];
};

@Component({
    selector: 'app-chat',
    standalone: true,
    imports: [CommonModule, LucideAngularModule, MarkedPipe],
    templateUrl: './chat.component.html',
    styleUrls: ['./chat.component.scss']
})
export class ChatComponent implements AfterViewChecked {
    readonly Database = Database;
    readonly Bot = Bot;
    readonly AlertCircle = AlertCircle;
    readonly Ban = Ban;
    readonly ChevronDown = ChevronDown;
    readonly ChevronUp = ChevronUp;
    readonly User = User;
    readonly Copy = Copy;
    readonly Check = Check;
    readonly Download = Download;
    readonly ChartColumn = ChartColumn;
    readonly ChartLine = ChartLine;
    readonly ChartScatter = ChartScatter;
    readonly ChartArea = ChartArea;
    readonly ChartPie = ChartPie;
    readonly ChartNoAxesCombined = ChartNoAxesCombined;

    @Input() messages: ChatMessage[] = [];
    @Input() conversationId?: string;
    @Input() isTyping = false;
    @Input() scrollOnNewMessage = false;

    @Output() suggestionSelected = new EventEmitter<string>();

    onSuggestionClick(text: string): void {
        this.suggestionSelected.emit(text);
    }
    @ViewChild('scrollContainer') scrollContainer!: ElementRef<HTMLDivElement>;
    @ViewChildren('vizChartHost') vizChartHosts!: QueryList<ElementRef<HTMLDivElement>>;

    showScrollToBottom = false;
    userHasScrolledUp = false;

    /** Expanded state for SQL query expanders (by message id) */
    expandedSql: Set<string> = new Set();
    /** Expanded state for data table expanders (by message id) */
    expandedTable: Set<string> = new Set();
    /** Expanded state for RAG citation expanders (by message id) */
    expandedCitations: Set<string> = new Set();
    /** Parsed RAG content cache keyed by message state */
    private parsedRagContentCache = new Map<string, ParsedRagMessageContent>();
    /** Parsed citation payload cache keyed by message state */
    private parsedCitationPayloadCache = new Map<string, RagCitation[]>();
    /** Plotly charts already rendered for persisted visualization messages */
    private renderedVisualizationKeys = new Set<string>();
    /** Stable per-tool message objects for multi-tool rendering */
    private multiToolMessageCache = new Map<string, ChatMessage>();
    copiedSqlMessageId: string | null = null;
    private copiedSqlResetHandle: ReturnType<typeof setTimeout> | null = null;

    constructor(
        private chatService: ChatService,
        public themeService: ThemeService
    ) {}

    /** Returns table column headers from the first result row */
    getColumns(results: ChatResultRow[]): string[] {
        if (!results || results.length === 0) return [];
        return Object.keys(results[0]);
    }

    getColumnLabel(column: string): string {
        const labels: Record<string, string> = {
            date: 'Date',
            yhat: 'Predicted Orders',
            yhat_lower: 'Lower Bound',
            yhat_upper: 'Upper Bound',
            review_score: 'Review Score',
            total_distinct_orders: 'Total Distinct Orders',
            total_revenue: 'Total Revenue',
            avg_freight_cost: 'Avg Freight Cost',
            avg_payment_value: 'Avg Payment Value',
            review_score_rank: 'Review Score Rank',
            customer_state: 'Customer State',
        };

        return labels[column] || column
            .split('_')
            .map(part => part.charAt(0).toUpperCase() + part.slice(1))
            .join(' ');
    }

    toggleSql(msgId: string): void {
        this.expandedSql.has(msgId) ? this.expandedSql.delete(msgId) : this.expandedSql.add(msgId);
    }

    formatSqlQuery(query?: string): string {
        if (!query) return '';

        try {
            return format(query, {
                language: 'sql',
                keywordCase: 'upper',
                tabWidth: 4,
                linesBetweenQueries: 1,
            });
        } catch {
            return query;
        }
    }

    highlightSqlQuery(query?: string): string {
        const formattedQuery = this.formatSqlQuery(query);

        if (!formattedQuery) {
            return '';
        }

        return Prism.highlight(formattedQuery, Prism.languages['sql'], 'sql');
    }

    async copySqlQuery(msg: ChatMessage): Promise<void> {
        const query = this.formatSqlQuery(msg.sqlQuery);
        if (!query) {
            return;
        }

        await navigator.clipboard.writeText(query);
        this.copiedSqlMessageId = msg.id;

        if (this.copiedSqlResetHandle) {
            clearTimeout(this.copiedSqlResetHandle);
        }

        this.copiedSqlResetHandle = setTimeout(() => {
            if (this.copiedSqlMessageId === msg.id) {
                this.copiedSqlMessageId = null;
            }
        }, 1800);
    }

    toggleTable(msgId: string): void {
        this.expandedTable.has(msgId) ? this.expandedTable.delete(msgId) : this.expandedTable.add(msgId);
    }

    toggleCitations(msgId: string): void {
        this.expandedCitations.has(msgId) ? this.expandedCitations.delete(msgId) : this.expandedCitations.add(msgId);
    }

    getNormalizedTool(tool?: string): ToolName {
        switch ((tool || '').trim().toLowerCase()) {
            case 'sql_tool':
                return 'sql_tool';
            case 'ml_tool':
                return 'ml_tool';
            case 'rag_tool':
            case 'rag_tools':
                return 'rag_tool';
            case 'multi_tool':
                return 'multi_tool'; 
            case 'conversation_memory_tool':
                return 'conversation_memory_tool';
            case 'pre_filter':
                return 'pre_filter';
            case 'visualize':
                return 'visualize';
            case 'out_of_scope':
                return 'out_of_scope';
            case 'error':
                return 'error';
            default:
                return 'unknown_tool';
        }
    }
    getMultiPatchLabel(tool?: string): string {
        switch (this.getNormalizedTool(tool)) {
            case 'sql_tool': return 'Database Analytics';
            case 'ml_tool':  return 'Predictive Forecast';
            case 'rag_tool': return 'Document Intelligence';
            default:         return 'Enterprise Data';
        }
    }

    getMultiToolFeatures(msg: ChatMessage): string[] {
        const tool = this.getNormalizedTool(msg.tool);
        const features: string[] = [];

        if (tool === 'sql_tool') {
            if (msg.sqlQuery) {
                features.push('SQL Query');
            }
            if (this.hasDisplayTables(msg)) {
                features.push('Table');
            }
            if (this.hasDocCitations(msg)) {
                features.push('Citations');
            }
            if (this.hasWebCitations(msg)) {
                features.push('Sources');
            }
            if (this.canShowVisualizationButton(msg) || this.hasSavedVisualization(msg)) {
                features.push('Generate Visualization');
            }
        }

        if (tool === 'ml_tool') {
            if (this.hasDisplayTables(msg)) {
                features.push('Table');
            }
            if (this.canShowVisualizationButton(msg) || this.hasSavedVisualization(msg)) {
                features.push('Generate Visualization');
            }
        }

        if (tool === 'rag_tool') {
            if (this.hasDocCitations(msg)) {
                features.push('Citations');
            }
            if (this.hasWebCitations(msg)) {
                features.push('Sources');
            }
            if (this.hasDisplayTables(msg)) {
                features.push('Table');
            }
        }

        return features;
    }

    getTabularResults(msg: ChatMessage): ChatResultRow[] {
        if (this.getNormalizedTool(msg.tool) === 'ml_tool' && this.getRenderableTables(msg).length > 0) {
            return [];
        }

        return Array.isArray(msg.results) ? msg.results : [];
    }

    shouldShowToolBadge(msg: ChatMessage): boolean {
        if (msg.sender !== 'assistant' || !msg.tool) {
            return false;
        }

        const tool = this.getNormalizedTool(msg.tool);
        if (tool === 'multi_tool' || tool === 'error' || tool === 'out_of_scope' || tool === 'unknown_tool') {
            return false;
        }

        return true;
    }

    canShowVisualizationButton(msg: ChatMessage): boolean {
        if (msg.sender !== 'assistant' || msg.isTyping || msg.error) {
            return false;
        }

        const tool = this.getNormalizedTool(msg.tool);
        if (tool !== 'sql_tool' && tool !== 'ml_tool') {
            return false;
        }

        const data = this.getVisualizationData(msg);
        if (!data.length) {
            return false;
        }

        return this.getCandidateVisualizationOptions(msg).length > 0;
    }

    getCandidateVisualizationOptions(msg: ChatMessage): VisualizationOption[] {
        if (Array.isArray(msg.chartTypeOptions) && msg.chartTypeOptions.length > 0) {
            return msg.chartTypeOptions;
        }

        const data = this.getVisualizationData(msg);
        if (!data || data.length === 0) {
            return [];
        }

        const firstRow = data[0];
        const keys = Object.keys(firstRow);

        // Check if Prophet forecast data
        const hasDate = 'date' in firstRow;
        const hasYhat = 'yhat' in firstRow;
        if (hasDate && hasYhat) {
            return [
                {
                    id: 'chart_type_line',
                    label: 'Trend Line',
                    description: 'Forecast trend with confidence intervals',
                    chart_type: 'line',
                    is_custom: false
                },
                {
                    id: 'chart_type_bar',
                    label: 'Daily Bar',
                    description: 'Compare predicted daily volume',
                    chart_type: 'bar',
                    is_custom: false
                },
                {
                    id: 'chart_type_area',
                    label: 'Area View',
                    description: 'Cumulative forecast volume',
                    chart_type: 'area',
                    is_custom: false
                }
            ];
        }

        const numericKeys: string[] = [];
        const dateKeys: string[] = [];
        const categoryKeys: string[] = [];

        for (const k of keys) {
            const val = firstRow[k];
            const kLower = k.toLowerCase();

            if (typeof val === 'number') {
                numericKeys.push(k);
            } else if (
                kLower.includes('date') ||
                kLower.includes('time') ||
                kLower.includes('month') ||
                kLower.includes('year') ||
                kLower.includes('day')
            ) {
                dateKeys.push(k);
            } else if (!kLower.endsWith('_id')) {
                categoryKeys.push(k);
            }
        }

        if (numericKeys.length === 0) {
            return [];
        }

        if (dateKeys.length > 0) {
            return [
                {
                    id: 'chart_type_line',
                    label: 'Line Chart',
                    description: 'Trajectory over time',
                    chart_type: 'line',
                    is_custom: false
                },
                {
                    id: 'chart_type_bar',
                    label: 'Bar Chart',
                    description: 'Compare time intervals',
                    chart_type: 'bar',
                    is_custom: false
                },
                {
                    id: 'chart_type_area',
                    label: 'Area Chart',
                    description: 'Volume progression',
                    chart_type: 'area',
                    is_custom: false
                }
            ];
        }

        if (categoryKeys.length > 0) {
            const opts: VisualizationOption[] = [
                {
                    id: 'chart_type_bar',
                    label: 'Bar Chart',
                    description: 'Compare values by category',
                    chart_type: 'bar',
                    is_custom: false
                }
            ];
            const uniqueCats = new Set(data.map(r => r[categoryKeys[0]])).size;
            if (uniqueCats >= 2 && uniqueCats <= 8) {
                opts.push({
                    id: 'chart_type_pie',
                    label: 'Pie Chart',
                    description: 'Percentage distribution of total',
                    chart_type: 'pie',
                    is_custom: false
                });
            }
            if (data.length > 4) {
                opts.push({
                    id: 'chart_type_line',
                    label: 'Line Chart',
                    description: 'Ranked progression across categories',
                    chart_type: 'line',
                    is_custom: false
                });
            }
            return opts;
        }

        if (numericKeys.length >= 2) {
            return [
                {
                    id: 'chart_type_scatter',
                    label: 'Scatter Plot',
                    description: 'Numeric relationship',
                    chart_type: 'scatter',
                    is_custom: false
                },
                {
                    id: 'chart_type_bar',
                    label: 'Bar Chart',
                    description: 'Comparative bars',
                    chart_type: 'bar',
                    is_custom: false
                }
            ];
        }

        return [
            {
                id: 'chart_type_bar',
                label: 'Bar Chart',
                description: 'Values comparison',
                chart_type: 'bar',
                is_custom: false
            }
        ];
    }

    async onSelectInitialChartType(msg: ChatMessage, option: VisualizationOption): Promise<void> {
        await this.requestVisualizationRefresh(msg, option.chart_type || undefined);
    }

    getVisualizationData(msg: ChatMessage): ChatResultRow[] {
        if (Array.isArray(msg.visualizationData) && msg.visualizationData.length > 0) {
            return msg.visualizationData;
        }

        if (Array.isArray(msg.results) && msg.results.length > 0) {
            return msg.results;
        }

        return [];
    }

    getVisualizationChartId(msg: ChatMessage): string {
        return msg.visualizationChartId || `viz-chart-${msg.id}`;
    }

    hasSavedVisualization(msg: ChatMessage): boolean {
        return Array.isArray(msg.chartSpecs) && msg.chartSpecs.length > 0;
    }

    private getPrimaryChartSpec(msg: ChatMessage): ChartSpec | null {
        return this.hasSavedVisualization(msg) ? msg.chartSpecs![0] : null;
    }

    async onGenerateVisualization(msg: ChatMessage): Promise<void> {
        await this.requestVisualizationRefresh(msg);
    }


    getChartTypeOptions(msg: ChatMessage): VisualizationOption[] {
        return Array.isArray(msg.chartTypeOptions) ? msg.chartTypeOptions : [];
    }

    private hasPrecomputedChartSpecs(options?: VisualizationOption[]): boolean {
        return Array.isArray(options)
            && options.length > 0
            && options.every(option => !!option?.chart_spec?.figure_json);
    }

    private getPrimaryChartOption(msg: ChatMessage): VisualizationOption | null {
        if (!msg.primaryVisualizationChartSpec?.figure_json) {
            return null;
        }

        return {
            id: 'primary_chart_option',
            label: 'Original',
            description: msg.visualizationSummary || msg.primaryVisualizationChartSpec.title || 'Return to the original recommended chart.',
            chart_type: msg.primaryVisualizationChartSpec.chart_type,
            is_custom: false,
            chart_spec: msg.primaryVisualizationChartSpec,
        };
    }

    getChartSwitcherOptions(msg: ChatMessage): VisualizationOption[] {
        const primaryOption = this.getPrimaryChartOption(msg);
        const chartTypeOptions = this.getChartTypeOptions(msg);

        if (!primaryOption) {
            return this.getUniqueVisualizationOptions(chartTypeOptions);
        }

        return this.getUniqueVisualizationOptions([primaryOption, ...chartTypeOptions]);
    }

    private getUniqueVisualizationOptions(options: VisualizationOption[]): VisualizationOption[] {
        const unique: VisualizationOption[] = [];
        const seen = new Set<string>();

        for (const option of options) {
            const figureJson = option.chart_spec?.figure_json || '';
            const key = figureJson || `${option.id}::${option.chart_type || ''}::${option.label}`;
            if (seen.has(key)) {
                continue;
            }
            seen.add(key);
            unique.push(option);
        }

        return unique;
    }

    getVisualizationOptionLabel(option: VisualizationOption): string {
        return option.label;
    }

    getChartTypeIcon(option: VisualizationOption): any {
        const type = (option.chart_type || option.id || '').toLowerCase();
        if (type.includes('line') || type.includes('trend')) {
            return this.ChartLine;
        }
        if (type.includes('scatter') || type.includes('strip')) {
            return this.ChartScatter;
        }
        if (type.includes('area')) {
            return this.ChartArea;
        }
        if (type.includes('pie') || type.includes('donut')) {
            return this.ChartPie;
        }
        if (
            type.includes('combo')
            || type.includes('heatmap')
            || type.includes('box')
            || type.includes('violin')
            || type.includes('histogram')
        ) {
            return this.ChartNoAxesCombined;
        }
        return this.ChartColumn;
    }

    private looksLikeRawVisualizationPayload(value?: string): boolean {
        const text = value?.trim();
        if (!text) {
            return false;
        }

        if (text.length > 400) {
            return true;
        }

        const lowered = text.toLowerCase();
        return (
            lowered.includes('"figure_json"')
            || lowered.includes('"chart_specs"')
            || lowered.includes('"visualization_options"')
            || lowered.includes('"layout"')
            || lowered.includes('"data"')
            || lowered.includes('plotly')
        );
    }

    async onSelectVisualizationOption(msg: ChatMessage, option: VisualizationOption): Promise<void> {
        const tool = this.getNormalizedTool(msg.tool);
        if ((tool !== 'sql_tool' && tool !== 'ml_tool') || msg.visualizationLoading) {
            return;
        }

        msg.selectedVisualizationOptionId = option.id;

        if (option.chart_spec) {
            msg.visualizationError = '';
            msg.chartSpecs = [option.chart_spec];
            msg.visualizationChartId = this.getVisualizationChartId(msg);
            this.renderedVisualizationKeys.delete(this.getVisualizationRenderKey(msg, option.chart_spec));

            setTimeout(() => {
                this.renderChart(msg, option.chart_spec!);
            }, 0);
            return;
        }

        // On-demand generation for chosen option
        await this.requestVisualizationRefresh(msg, option.chart_type || undefined);
    }

    isVisualizationOptionSelected(msg: ChatMessage, option: VisualizationOption): boolean {
        if (option.id === 'primary_chart_option') {
            const currentFigure = msg.chartSpecs?.[0]?.figure_json;
            return !!currentFigure && currentFigure === msg.primaryVisualizationChartSpec?.figure_json;
        }

        return msg.selectedVisualizationOptionId === option.id;
    }

    private async requestVisualizationRefresh(msg: ChatMessage, chartType?: string): Promise<void> {
        const tool = this.getNormalizedTool(msg.tool);
        if (tool !== 'sql_tool' && tool !== 'ml_tool') {
            return;
        }

        const data = this.getVisualizationData(msg);
        if (!data.length) {
            msg.visualizationError = 'No tabular data available for visualization.';
            return;
        }

        msg.visualizationLoading = true;
        msg.visualizationError = '';
        msg.visualizationSummary = '';
        msg.visualizationStats = [];
        msg.visualizationSampleData = [];
        msg.visualizationSampleMessage = '';
        msg.visualizationMode = 'chart';
        msg.visualizationChartId = '';

        try {
            const parentMessageId = msg.metadata?.['multi_tool_parent_message_id'] || msg.id;
            const sourcePatchIndex = typeof msg.metadata?.['multi_tool_patch_index'] === 'number'
                ? msg.metadata['multi_tool_patch_index']
                : undefined;

            const response = await this.chatService.generateVisualization(
                msg.conversationId || this.conversationId,
                tool,
                data,
                {
                    sourceMessageId: parentMessageId,
                    sourcePatchIndex,
                    chartType,
                }
            );

            if (response.error) {
                msg.visualizationError = 'I couldn’t create that visualization right now. Please try again shortly.';
                return;
            }

            msg.visualizationSummary = this.looksLikeRawVisualizationPayload(response.summary)
                ? ''
                : (response.summary || '');
            msg.visualizationStats = response.statistical_summary || [];
            msg.visualizationSampleData = response.sample_data || [];
            msg.visualizationSampleMessage = response.sample_message || '';
            msg.visualizationMode = response.visualization_mode || 'chart';

            const returnedOptions = response.chart_type_options || [];
            if (response.chart_specs && response.chart_specs.length > 0) {
                const generatedSpec = response.chart_specs[0];
                for (const opt of returnedOptions) {
                    if (opt.chart_type === generatedSpec.chart_type) {
                        opt.chart_spec = generatedSpec;
                    }
                }
            }
            msg.chartTypeOptions = returnedOptions.length > 0 ? returnedOptions : msg.chartTypeOptions;
            msg.visualizationOptions = [];
            msg.selectedVisualizationOptionId = chartType
                ? (msg.chartTypeOptions?.find(o => o.chart_type === chartType)?.id || 'primary_chart_option')
                : 'primary_chart_option';

            if ((!response.chart_specs || response.chart_specs.length === 0) && msg.visualizationSampleData.length === 0) {
                msg.visualizationError = this.looksLikeRawVisualizationPayload(response.summary)
                    ? 'The visualization response was invalid. Please try again.'
                    : (response.summary || 'No chart returned by backend.');
                return;
            }

            if (response.chart_specs && response.chart_specs.length > 0) {
                msg.chartSpecs = response.chart_specs;
                msg.primaryVisualizationChartSpec = response.chart_specs[0];
                msg.visualizationChartId = this.getVisualizationChartId(msg);
                this.renderedVisualizationKeys.delete(this.getVisualizationRenderKey(msg, response.chart_specs[0]));
                this.syncMultiToolVisualizationState(msg, response);
                setTimeout(() => {
                    this.renderChart(msg, response.chart_specs[0]);
                }, 0);
            }

        } catch (error: any) {
            msg.visualizationError = 'I couldn’t create that visualization right now. The service may be temporarily unavailable. Please try again shortly.';
        } finally {
            msg.visualizationLoading = false;
        }
    }

    getVisualizationSampleColumns(msg: ChatMessage): string[] {
        if (!Array.isArray(msg.visualizationSampleData) || msg.visualizationSampleData.length === 0) {
            return [];
        }

        return Object.keys(msg.visualizationSampleData[0]);
    }

    hasVisualizationStats(msg: ChatMessage): boolean {
        return Array.isArray(msg.visualizationStats) && msg.visualizationStats.length > 0;
    }

    getVisualizationStats(msg: ChatMessage): StatisticalSummaryItem[] {
        return Array.isArray(msg.visualizationStats) ? msg.visualizationStats : [];
    }

    getVisualizationSummaryForDisplay(msg: ChatMessage): string {
        const summary = (msg.visualizationSummary || '').trim();
        if (!summary) {
            return '';
        }

        if (summary.startsWith('data:image/')) {
            return `![Generated visualization](${summary})`;
        }

        return summary;
    }

    downloadVisualization(msg: ChatMessage): void {
        const target = document.getElementById(this.getVisualizationChartId(msg));
        const chartSpec = this.getPrimaryChartSpec(msg);

        if (!target || !chartSpec) {
            return;
        }

        Plotly.downloadImage(target, {
            format: 'png',
            filename: this.toDownloadFileName(chartSpec.title || 'visualization'),
            width: 1400,
            height: 900,
            scale: 2
        });
    }

    private renderChart(msg: ChatMessage, chartSpec: ChartSpec): void {
        const target = document.getElementById(this.getVisualizationChartId(msg));

        if (!target) {
            msg.visualizationError = 'Chart container not found.';
            return;
        }

        try {
            const figure = this.applyPlotlyTheme(
                this.normalizePlotlyFigure(JSON.parse(chartSpec.figure_json))
            );

            Plotly.react(
                target,
                figure.data || [],
                figure.layout || {},
                {
                    responsive: true,
                    displayModeBar: false
                }
            );
            this.renderedVisualizationKeys.add(this.getVisualizationRenderKey(msg, chartSpec));
        } catch (error) {
            console.error('Failed to render Plotly chart', error, chartSpec);
            msg.visualizationError = 'Failed to render chart.';
        }
    }

    private renderSavedVisualizations(): void {
        for (const msg of this.getVisualizationRenderMessages()) {
            const chartSpec = this.getPrimaryChartSpec(msg);
            if (!chartSpec) {
                continue;
            }

            const target = document.getElementById(this.getVisualizationChartId(msg));
            if (!target) {
                continue;
            }

            const renderKey = this.getVisualizationRenderKey(msg, chartSpec);
            if (this.renderedVisualizationKeys.has(renderKey) && target.childElementCount > 0) {
                continue;
            }

            this.renderChart(msg, chartSpec);
        }
    }

    private getVisualizationRenderMessages(): ChatMessage[] {
        const renderMessages: ChatMessage[] = [];

        for (const msg of this.messages) {
            renderMessages.push(msg);

            if (this.getNormalizedTool(msg.tool) !== 'multi_tool') {
                continue;
            }

            this.getMultiToolResults(msg).forEach((patch, index) => {
                renderMessages.push(this.makeToolResultMessage(patch, msg, index));
            });
        }

        return renderMessages;
    }

    private getVisualizationRenderKey(msg: ChatMessage, chartSpec: ChartSpec): string {
        return `${msg.id}::${this.isDarkTheme() ? 'dark' : 'light'}::${chartSpec.figure_json}`;
    }

    private applyPlotlyTheme(figure: any): any {
        const layout = figure?.layout || {};
        const margin = this.getResponsivePlotlyMargin(figure, layout);
        const isDark = this.isDarkTheme();
        const textColor = isDark ? '#E6EDF7' : '#102235';
        const mutedTextColor = isDark ? '#94A3B8' : '#64748B';
        const gridColor = isDark ? '#29374B' : '#E5EDF4';
        const axisLineColor = isDark ? '#29374B' : '#E5EDF4';
        const chartBackground = isDark ? '#111C2E' : '#FFFFFF';
        const axisTheme = {
            color: mutedTextColor,
            gridcolor: gridColor,
            linecolor: axisLineColor,
            zerolinecolor: gridColor,
            ticks: 'outside',
            tickfont: { color: mutedTextColor, size: 11 },
            title: { font: { color: textColor, size: 12 } }
        };
        const xAxis = this.applyPlotlyAxisTheme(layout.xaxis, axisTheme, textColor);
        const yAxis = this.applyPlotlyAxisTheme(layout.yaxis, axisTheme, textColor);

        return {
            ...figure,
            layout: {
                ...layout,
                autosize: true,
                paper_bgcolor: chartBackground,
                plot_bgcolor: chartBackground,
                margin,
                font: {
                    ...(layout.font || {}),
                    color: textColor
                },
                title: {
                    ...(typeof layout.title === 'object' ? layout.title : { text: layout.title }),
                    x: typeof layout.title === 'object' && layout.title?.x !== undefined ? layout.title.x : 0.02,
                    xanchor: typeof layout.title === 'object' && layout.title?.xanchor ? layout.title.xanchor : 'left',
                    font: {
                        ...(typeof layout.title === 'object' ? layout.title?.font || {} : {}),
                        color: textColor,
                        size: 22
                    }
                },
                xaxis: xAxis,
                yaxis: yAxis,
                legend: {
                    ...(layout.legend || {}),
                    orientation: layout.legend?.orientation || 'h',
                    x: layout.legend?.x ?? 0.02,
                    y: layout.legend?.y ?? 1.08,
                    bgcolor: 'rgba(0,0,0,0)',
                    font: {
                        ...(layout.legend?.font || {}),
                        color: textColor,
                        size: 12
                    }
                }
            }
        };
    }

    private applyPlotlyAxisTheme(axis: any, axisTheme: any, textColor: string): any {
        const axisConfig = axis || {};
        const axisTitle = typeof axisConfig.title === 'object'
            ? axisConfig.title
            : { text: axisConfig.title };

        return {
            ...axisTheme,
            ...axisConfig,
            automargin: true,
            title: {
                ...axisTheme.title,
                ...(axisTitle || {}),
                font: {
                    ...(axisTheme.title?.font || {}),
                    ...(axisTitle?.font || {}),
                    color: textColor,
                    size: axisTitle?.font?.size || axisTheme.title?.font?.size || 12
                }
            }
        };
    }

    private getResponsivePlotlyMargin(figure: any, layout: any): Record<string, number> {
        const suppliedMargin = layout?.margin || {};
        const baseMargin = {
            l: 64,
            r: 34,
            t: 78,
            b: 86,
            ...suppliedMargin
        };
        const horizontalBarChart = Array.isArray(figure?.data)
            && figure.data.some((trace: any) => trace?.type === 'bar' && trace?.orientation === 'h');

        if (!horizontalBarChart) {
            return baseMargin;
        }

        const longestLabelLength = this.getLongestPlotlyAxisLabelLength(figure, layout, 'yaxis', 'y');
        const labelMargin = Math.min(260, Math.max(64, 52 + (longestLabelLength * 7)));

        return {
            ...baseMargin,
            l: Math.max(Number(baseMargin.l) || 0, labelMargin)
        };
    }

    private getLongestPlotlyAxisLabelLength(figure: any, layout: any, axisKey: string, dataKey: string): number {
        const labels: string[] = [];
        const tickText = layout?.[axisKey]?.ticktext;

        if (Array.isArray(tickText)) {
            labels.push(...tickText.map(value => String(value ?? '')));
        }

        if (Array.isArray(figure?.data)) {
            for (const trace of figure.data) {
                const values = trace?.[dataKey];
                if (Array.isArray(values)) {
                    labels.push(...values.map(value => String(value ?? '')));
                }
            }
        }

        return labels.reduce((max, label) => Math.max(max, label.length), 0);
    }

    private isDarkTheme(): boolean {
        return document.body.classList.contains('dark')
            || document.documentElement.getAttribute('data-theme') === 'dark';
    }

    private normalizePlotlyFigure(value: any): any {
        if (Array.isArray(value)) {
            return value.map(item => this.normalizePlotlyFigure(item));
        }

        if (!value || typeof value !== 'object') {
            return value;
        }

        if (this.isPlotlyTypedArrayPayload(value)) {
            return this.decodePlotlyTypedArray(value);
        }

        return Object.fromEntries(
            Object.entries(value).map(([key, item]) => [key, this.normalizePlotlyFigure(item)])
        );
    }

    private isPlotlyTypedArrayPayload(value: any): value is PlotlyTypedArrayPayload {
        return typeof value?.dtype === 'string' && typeof value?.bdata === 'string';
    }

    private decodePlotlyTypedArray(payload: PlotlyTypedArrayPayload): number[] {
        const binary = atob(payload.bdata);
        const bytes = new Uint8Array(binary.length);

        for (let idx = 0; idx < binary.length; idx += 1) {
            bytes[idx] = binary.charCodeAt(idx);
        }

        const view = new DataView(bytes.buffer);
        const dtype = payload.dtype;
        const values: number[] = [];

        const readers: Record<string, { size: number; read: (offset: number) => number }> = {
            f8: { size: 8, read: offset => view.getFloat64(offset, true) },
            f4: { size: 4, read: offset => view.getFloat32(offset, true) },
            i1: { size: 1, read: offset => view.getInt8(offset) },
            u1: { size: 1, read: offset => view.getUint8(offset) },
            i2: { size: 2, read: offset => view.getInt16(offset, true) },
            u2: { size: 2, read: offset => view.getUint16(offset, true) },
            i4: { size: 4, read: offset => view.getInt32(offset, true) },
            u4: { size: 4, read: offset => view.getUint32(offset, true) },
        };

        const reader = readers[dtype];
        if (!reader) {
            return [];
        }

        for (let offset = 0; offset + reader.size <= bytes.byteLength; offset += reader.size) {
            values.push(reader.read(offset));
        }

        return values;
    }

    getToolBadge(tool?: string): { label: string; cssClass: string } {
        switch (this.getNormalizedTool(tool)) {
            case 'sql_tool':
                return { label: 'Database Analytics', cssClass: 'badge-sql' };
            case 'ml_tool':
                return { label: 'Predictive Intelligence', cssClass: 'badge-ml' };
            case 'rag_tool':
                return { label: 'Knowledge Retrieval', cssClass: 'badge-rag' };
            case 'multi_tool':
                return { label: 'Unified Intelligence', cssClass: 'badge-multi' };
            case 'visualize':
                return { label: 'Data Visualization', cssClass: 'badge-sql' };
            case 'out_of_scope':
                return { label: 'Advisory Guidance', cssClass: 'badge-oos' };
            case 'unknown_tool':
                return { label: 'Solvique Intelligence', cssClass: 'badge-rag' };
            default:
                return { label: 'Solvique', cssClass: 'badge-default' };
        }
    }

    getMultiToolResults(msg: ChatMessage): MultiToolResult[] {
    return Array.isArray(msg.tool_results) ? msg.tool_results : [];
    
    }

    private syncMultiToolVisualizationState(msg: ChatMessage, response: {
        chart_specs?: ChartSpec[];
        visualization_options?: VisualizationOption[];
        chart_type_options?: VisualizationOption[];
        statistical_summary?: StatisticalSummaryItem[];
        sample_data?: ChatResultRow[];
        sample_message?: string;
        visualization_mode?: 'chart' | 'summary';
    }): void {
        const parentMessageId = msg.metadata?.['multi_tool_parent_message_id'];
        const patchIndex = msg.metadata?.['multi_tool_patch_index'];

        if (!parentMessageId || typeof patchIndex !== 'number') {
            return;
        }

        const parentMsg = this.messages.find(message => message.id === parentMessageId);
        if (!parentMsg?.tool_results || !parentMsg.tool_results[patchIndex]) {
            return;
        }

        parentMsg.tool_results[patchIndex] = {
            ...parentMsg.tool_results[patchIndex],
            chart_specs: response.chart_specs || [],
            visualization_options: response.visualization_options || [],
            chart_type_options: response.chart_type_options || [],
            statistical_summary: response.statistical_summary || [],
            sample_data: response.sample_data || [],
            sample_message: response.sample_message || '',
            visualization_mode: response.visualization_mode || 'chart',
        };
    }

    makeToolResultMessage(patch: MultiToolResult, parentMsg: ChatMessage, index: number): ChatMessage {
        const cacheKey = `${parentMsg.id}-${index}`;
        const existing = this.multiToolMessageCache.get(cacheKey);

        if (existing) {
            existing.conversationId = parentMsg.conversationId;
            existing.timestamp = parentMsg.timestamp;
            existing.text = patch.explanation || '';
            existing.tool = patch.tool;
            existing.sqlQuery = patch.sql_query;
            existing.results = patch.results;
            existing.citations = patch.citations;
            existing.doc_citations = patch.doc_citations;
            existing.web_citations = patch.web_citations;
            existing.chartSpecs = patch.chart_specs || [];
            existing.primaryVisualizationChartSpec = patch.chart_specs?.length ? patch.chart_specs[0] : undefined;
            existing.visualizationOptions = patch.visualization_options || [];
            existing.chartTypeOptions = patch.chart_type_options || [];
            existing.selectedVisualizationOptionId = patch.chart_specs?.length ? 'primary_chart_option' : undefined;
            existing.visualizationStats = patch.statistical_summary || [];
            existing.visualizationSampleData = patch.sample_data || [];
            existing.visualizationSampleMessage = patch.sample_message || '';
            existing.visualizationMode = patch.visualization_mode || 'chart';
            existing.visualizationChartId = patch.chart_specs?.length ? `viz-chart-${existing.id}` : '';
            existing.metadata = {
                ...(existing.metadata || {}),
                multi_tool_parent_message_id: parentMsg.id,
                multi_tool_patch_index: index,
            };
            existing.error = patch.error;
            existing.renderComplete = true;
            return existing;
        }

        const patchMessage: ChatMessage = {
            id: `${parentMsg.id}-tool-${index}`,
            conversationId: parentMsg.conversationId,
            sender: 'assistant',
            text: patch.explanation || '',
            timestamp: parentMsg.timestamp,
            tool: patch.tool,
            sqlQuery: patch.sql_query,
            results: patch.results,
            citations: patch.citations,
            doc_citations: patch.doc_citations,
            web_citations: patch.web_citations,
            chartSpecs: patch.chart_specs || [],
            primaryVisualizationChartSpec: patch.chart_specs?.length ? patch.chart_specs[0] : undefined,
            visualizationOptions: patch.visualization_options || [],
            chartTypeOptions: patch.chart_type_options || [],
            selectedVisualizationOptionId: patch.chart_specs?.length ? 'primary_chart_option' : undefined,
            visualizationStats: patch.statistical_summary || [],
            visualizationSampleData: patch.sample_data || [],
            visualizationSampleMessage: patch.sample_message || '',
            visualizationMode: patch.visualization_mode || 'chart',
            visualizationChartId: patch.chart_specs?.length ? `viz-chart-${parentMsg.id}-tool-${index}` : undefined,
            metadata: {
                multi_tool_parent_message_id: parentMsg.id,
                multi_tool_patch_index: index,
            },
            error: patch.error,
            renderComplete: true,
        };

        this.multiToolMessageCache.set(cacheKey, patchMessage);
        return patchMessage;
    }

    hasDocCitations(msg: ChatMessage): boolean {
    return this.normalizeCitationPayload(msg.id, msg.doc_citations).length > 0;
    }

    hasWebCitations(msg: ChatMessage): boolean {
        return this.normalizeCitationPayload(msg.id, msg.web_citations).length > 0;
    }

    getDocCitations(msg: ChatMessage): RagCitation[] {
        return this.normalizeCitationPayload(msg.id, msg.doc_citations);
    }

    getWebCitations(msg: ChatMessage): RagCitation[] {
        return this.normalizeCitationPayload(msg.id, msg.web_citations);
    }
    hasCitations(msg: ChatMessage): boolean {
        return this.getStructuredCitations(msg).length > 0 || this.getFallbackCitations(msg).length > 0;
    }

    getCitationToggleLabel(msg: ChatMessage): string {
        return msg.metadata?.['citation_origin'] === 'web' ? 'View Sources' : 'View Citations';
    }

    getCitationCount(msg: ChatMessage): number {
        return this.getStructuredCitations(msg).length || this.getFallbackCitations(msg).length;
    }

    getMessageText(msg: ChatMessage): string {
        if (this.getNormalizedTool(msg.tool) === 'ml_tool') {
            return (msg.text || '').replace(
                /\n\s*#{1,6}\s*Feature Table\b[\s\S]*$/i,
                ''
            ).trim();
        }

        if (!this.shouldExtractTablesFromText(msg)) {
            return msg.text;
        }

        if (msg.rawText && msg.rawText !== msg.text) {
            return msg.text;
        }

        if (!msg.renderComplete) {
            return msg.text;
        }

        const parsedNarrative = this.getParsedRagContent(msg).narrativeText;
        // Table extraction is best-effort. Preserve the generated response if the
        // parser cannot identify any table structure in it.
        return parsedNarrative || msg.text || msg.rawText || '';
    }

    expandedWebCitations: Set<string> = new Set();

    toggleWebCitations(msgId: string): void {
        this.expandedWebCitations.has(msgId)
            ? this.expandedWebCitations.delete(msgId)
            : this.expandedWebCitations.add(msgId);
    }

    getFallbackCitations(msg: ChatMessage): string[] {
        if (this.getStructuredCitations(msg).length > 0 || this.getNormalizedTool(msg.tool) !== 'rag_tool') {
            return [];
        }

        return this.getParsedRagContent(msg).fallbackCitations;
    }

    hasDisplayTables(msg: ChatMessage): boolean {
        return this.getTabularResults(msg).length > 0 || this.getRenderableTables(msg).length > 0;
    }

    getRenderableTables(msg: ChatMessage): RenderableRagTable[] {
        if (!this.shouldExtractTablesFromText(msg)) {
            return [];
        }

        return this.getParsedRagContent(msg).tables;
    }

    getStructuredCitations(msg: ChatMessage): RagCitation[] {
        const citations = this.normalizeCitationPayload(msg.id, msg.citations);

        return [...citations].sort((left, right) => {
            const leftRank = left.retrieved_rank ?? Number.MAX_SAFE_INTEGER;
            const rightRank = right.retrieved_rank ?? Number.MAX_SAFE_INTEGER;
            if (leftRank !== rightRank) {
                return leftRank - rightRank;
            }

            const leftChunk = left.chunk?.chunk_no ?? Number.MAX_SAFE_INTEGER;
            const rightChunk = right.chunk?.chunk_no ?? Number.MAX_SAFE_INTEGER;
            return leftChunk - rightChunk;
        });
    }

    getTableExpanderLabel(msg: ChatMessage): string {
        const normalizedTool = this.getNormalizedTool(msg.tool);

        if (normalizedTool === 'rag_tool' || normalizedTool === 'ml_tool') {
            const tables = this.getRenderableTables(msg);
            return tables.length > 1 ? `Tables (${tables.length})` : 'Table';
        }

        const resultRowCount = this.getTabularResults(msg).length;
        if (resultRowCount > 0) {
            return `View Data Table (${resultRowCount} rows)`;
        }

        const tables = this.getRenderableTables(msg);
        if (tables.length === 0) {
            return 'View Table';
        }

        if (tables.length === 1) {
            return `View Retrieved Table (${tables[0].rows.length} rows)`;
        }

        return `View Retrieved Tables (${tables.length})`;
    }

    getCitationHeading(citation: RagCitation, index: number): string {
        const heading = citation.chunk?.heading?.trim();
        return heading || `Citation ${index + 1}`;
    }

    getCitationRankLabel(citation: RagCitation, index: number): string {
        return `Retrieved ${citation.retrieved_rank ?? index + 1}`;
    }

    getCitationFileLabel(citation: RagCitation): string | null {
        if (this.isWebCitation(citation)) {
            return citation.chunk?.domain || citation.chunk?.filename || 'Web source';
        }

        const filename = citation.chunk?.filename?.trim();
        const filetype = citation.chunk?.filetype?.trim();

        if (filename && filetype) {
            return `${filename} - ${filetype.toUpperCase()}`;
        }

        return filename || (filetype ? filetype.toUpperCase() : null);
    }

    getCitationChunkLabel(citation: RagCitation): string | null {
        const chunkNo = citation.chunk?.chunk_no;
        const totalChunks = citation.chunk?.total_chunks;

        if (chunkNo && totalChunks) {
            return `Chunk ${chunkNo}/${totalChunks}`;
        }

        return chunkNo ? `Chunk ${chunkNo}` : null;
    }

    getCitationTypeLabel(citation: RagCitation): string {
        const type = citation.chunk?.type;
        if (!type) return 'Source';

        switch (type) {
            case 'table':
                return 'Table';
            case 'paragraph_block':
                return 'Paragraph';
            default:
                return type
                    .split('_')
                    .map(part => part.charAt(0).toUpperCase() + part.slice(1))
                    .join(' ');
        }
    }

    isWebCitation(citation: RagCitation): boolean {
        return citation.chunk?.type === 'web_source';
    }

    getWebCitationUrl(citation: RagCitation): string | null {
        return citation.chunk?.url || null;
    }

    getWebCitationSnippet(citation: RagCitation): string {
        const content = typeof citation.chunk?.content === 'string' ? citation.chunk.content.trim() : '';
        return content.length > 280 ? `${content.slice(0, 280).trim()}...` : content;
    }

    getWebCitationPublishedDate(citation: RagCitation): string | null {
        return citation.chunk?.published_date || null;
    }

    formatCitationScore(score?: number): string | null {
        if (typeof score !== 'number' || !Number.isFinite(score)) {
            return null;
        }

        return `Relevance ${score.toFixed(3)}`;
    }

    isCitationTable(citation: RagCitation): boolean {
        const content = citation.chunk?.content;
        if (Array.isArray(content) && content.every(row => Array.isArray(row))) {
            return true;
        }

        return typeof content === 'string' && this.isMarkdownTableText(content);
    }

    getCitationText(citation: RagCitation): string {
        const content = citation.chunk?.content;

        if (typeof content === 'string') {
            return content;
        }

        return '';
    }

    getCitationTableHeaders(citation: RagCitation): string[] {
        const rows = this.getCitationTableRows(citation);
        if (rows.length === 0) return [];

        if (rows.length === 1) {
            return rows[0].map((_, idx) => `Column ${idx + 1}`);
        }

        const headerRow = rows[0];
        return headerRow.map((cell, idx) => cell || `Column ${idx + 1}`);
    }

    getCitationTableBodyRows(citation: RagCitation): string[][] {
        const rows = this.getCitationTableRows(citation);
        if (rows.length === 0) return [];

        if (rows.length === 1) {
            return rows;
        }

        const width = this.getCitationTableHeaders(citation).length;
        return rows.slice(1).map(row => this.normalizeCitationRow(row, width));
    }

    private getCitationTableRows(citation: RagCitation): string[][] {
        if (!this.isCitationTable(citation)) {
            return [];
        }

        const content = citation.chunk?.content;

        if (Array.isArray(content)) {
            return content.map(row => row.map(cell => cell ?? ''));
        }

        if (typeof content === 'string') {
            const parsed = this.parseCitationTableString(content);
            return Array.isArray(parsed) ? parsed : [];
        }

        return [];
    }

    private normalizeCitationRow(row: string[], width: number): string[] {
        return Array.from({ length: width }, (_, idx) => row[idx] || '');
    }

    private normalizeCitationPayload(msgId: string, citations?: RagCitationPayload): RagCitation[] {
        if (!citations) {
            return [];
        }

        if (Array.isArray(citations)) {
            return citations;
        }

        const cacheKey = `${msgId}::${citations}`;
        const cached = this.parsedCitationPayloadCache.get(cacheKey);
        if (cached) {
            return cached;
        }

        const parsed = this.parseCitationStringV2(citations);
        this.parsedCitationPayloadCache.set(cacheKey, parsed);
        return parsed;
    }

    private getParsedRagContent(msg: ChatMessage): ParsedRagMessageContent {
        const sourceText = msg.rawText ?? msg.text;
        const cacheKey = `${msg.id}::${msg.tool ?? ''}::${msg.renderComplete ? '1' : '0'}::${sourceText}`;
        const cached = this.parsedRagContentCache.get(cacheKey);
        if (cached) {
            return cached;
        }

        const parsed = this.parseRagMessageText(sourceText);
        this.parsedRagContentCache.set(cacheKey, parsed);
        return parsed;
    }

    getNarrativeTextForDisplay(text: string): string {
        return this.parseRagMessageText(text).narrativeText;
    }

    shouldExtractTablesFromTool(tool?: string): boolean {
        const normalizedTool = this.getNormalizedTool(tool);
        return normalizedTool === 'rag_tool' || normalizedTool === 'ml_tool';
    }

    private shouldExtractTablesFromText(msg: ChatMessage): boolean {
        return this.shouldExtractTablesFromTool(msg.tool);
    }

    private parseRagMessageText(text: string): ParsedRagMessageContent {
        if (!text) {
            return {
                narrativeText: '',
                fallbackCitations: [],
                tables: [],
            };
        }

        const lines = text.split(/\r?\n/);
        const narrativeLines: string[] = [];
        const fallbackCitations: string[] = [];
        const tables: RenderableRagTable[] = [];

        let pendingHeading: string | null = null;
        let pendingTableLabel: string | null = null;
        let pendingSource: string | null = null;
        let index = 0;

        while (index < lines.length) {
            const line = lines[index];
            const heading = this.parseMarkdownHeading(line);
            const scenarioLabel = this.parseScenarioLabel(line);
            const source = this.parseSourceLine(line);

            if (heading) {
                if (pendingHeading) {
                    narrativeLines.push(`### ${pendingHeading}`);
                }
                if (pendingSource) {
                    fallbackCitations.push(pendingSource);
                    pendingSource = null;
                }
                pendingHeading = heading;
                index += 1;
                continue;
            }

            if (scenarioLabel) {
                pendingTableLabel = scenarioLabel;
                index += 1;
                continue;
            }

            if (source) {
                pendingSource = source;
                index += 1;
                continue;
            }

            if (this.isMarkdownTableStart(lines, index)) {
                const { table, nextIndex } = this.parseMarkdownTable(
                    lines,
                    index,
                    pendingHeading,
                    pendingTableLabel,
                    pendingSource,
                    tables.length + 1
                );
                tables.push(table);
                if (pendingSource) {
                    fallbackCitations.push(pendingSource);
                }
                pendingHeading = null;
                pendingTableLabel = null;
                pendingSource = null;
                index = nextIndex;
                continue;
            }

            if (line.trim() === '' && (pendingHeading || pendingTableLabel || pendingSource)) {
                index += 1;
                continue;
            }

            if (pendingHeading) {
                narrativeLines.push(`### ${pendingHeading}`);
                pendingHeading = null;
            }
            if (pendingTableLabel) {
                narrativeLines.push(pendingTableLabel);
                pendingTableLabel = null;
            }
            if (pendingSource) {
                fallbackCitations.push(pendingSource);
                pendingSource = null;
            }

            narrativeLines.push(line);
            index += 1;
        }

        if (pendingHeading) {
            narrativeLines.push(`### ${pendingHeading}`);
        }
        if (pendingTableLabel) {
            narrativeLines.push(pendingTableLabel);
        }
        if (pendingSource) {
            fallbackCitations.push(pendingSource);
        }

        return {
            narrativeText: this.normalizeNarrativeText(narrativeLines.join('\n')),
            fallbackCitations: Array.from(new Set(fallbackCitations)),
            tables,
        };
    }

    private parseCitationString(citations: string): RagCitation[] {
        const trimmed = citations.trim();
        if (!trimmed) {
            return [];
        }

        const blocks = trimmed
            .split(/(?=\[Chunk\s+\d+\s+[—-])/)
            .map(block => block.trim())
            .filter(Boolean);

        if (blocks.length === 0) {
            return [{
                chunk: {
                    type: 'paragraph_block',
                    heading: 'Citation 1',
                    content: trimmed,
                }
            }];
        }

        return blocks.map((block, index) => this.parseCitationBlock(block, index));
    }

    private parseCitationStringV2(citations: string): RagCitation[] {
        const trimmed = citations.trim();
        if (!trimmed) {
            return [];
        }

        const blocks = trimmed
            .split(/(?=\[(?:Retrieved|Chunk)\s+\d+\s*(?:\||-|—|–))/)
            .map(block => block.trim())
            .filter(Boolean);

        if (blocks.length === 0) {
            return [{
                chunk: {
                    type: 'paragraph_block',
                    heading: 'Citation 1',
                    content: trimmed,
                }
            }];
        }

        return blocks.map((block, index) => this.parseCitationBlockV2(block, index));
    }

    private parseCitationBlockV2(block: string, index: number): RagCitation {
        const [headerLine = '', ...bodyLines] = block.split(/\r?\n/);
        const body = bodyLines.join('\n').trim();
        const retrievedHeader = this.parseRetrievedCitationHeader(headerLine);

        if (retrievedHeader) {
            const parsedTable = this.isMarkdownTableText(body)
                ? this.parseCitationTableString(body)
                : null;

            return {
                retrieved_rank: retrievedHeader.rank,
                chunk: {
                    type: Array.isArray(parsedTable) ? 'table' : 'paragraph_block',
                    filename: retrievedHeader.filename,
                    filetype: retrievedHeader.filetype,
                    chunk_no: retrievedHeader.chunkNo,
                    total_chunks: retrievedHeader.totalChunks,
                    heading: retrievedHeader.heading || `Citation ${index + 1}`,
                    content: Array.isArray(parsedTable) ? parsedTable : body || block.trim(),
                }
            };
        }

        const oldHeader = headerLine.trim().match(/^\[Chunk\s+(\d+)\s+-\s+(.+?)\s+-\s+Section:\s*(.+?)\]$/);
        if (oldHeader) {
            const parsedTable = this.isMarkdownTableText(body)
                ? this.parseCitationTableString(body)
                : null;
            const normalizedType = Array.isArray(parsedTable)
                ? 'table'
                : this.normalizeCitationType(oldHeader[2].trim());

            return {
                chunk: {
                    type: normalizedType,
                    heading: oldHeader[3].trim(),
                    content: Array.isArray(parsedTable) ? parsedTable : body || block.trim(),
                }
            };
        }

        return {
            chunk: {
                type: this.isMarkdownTableText(block) ? 'table' : 'paragraph_block',
                heading: `Citation ${index + 1}`,
                content: this.isMarkdownTableText(block)
                    ? this.parseCitationTableString(block)
                    : block.trim(),
            }
        };
    }

    private parseRetrievedCitationHeader(headerLine: string): {
        rank?: number;
        filename?: string;
        filetype?: string;
        chunkNo?: number;
        totalChunks?: number;
        heading?: string;
    } | null {
        const match = headerLine.trim().match(/^\[Retrieved\s+(\d+)\s*\|\s*(.+?)\]$/);

        if (!match) {
            return null;
        }

        const metadata: Record<string, string> = {};

        for (const segment of match[2].split('|')) {
            const [rawKey, ...rawValue] = segment.split(':');
            const key = rawKey?.trim().toLowerCase();
            const value = rawValue.join(':').trim();

            if (key && value) {
                metadata[key] = value;
            }
        }

        const chunkMatch = metadata['chunk']?.match(/^(\d+)(?:\s*\/\s*(\d+))?$/);

        return {
            rank: Number(match[1]),
            filename: metadata['file'],
            filetype: metadata['type'],
            chunkNo: chunkMatch ? Number(chunkMatch[1]) : undefined,
            totalChunks: chunkMatch?.[2] ? Number(chunkMatch[2]) : undefined,
            heading: metadata['section'],
        };
    }

    private parseCitationBlock(block: string, index: number): RagCitation {
        const [headerLine = '', ...bodyLines] = block.split(/\r?\n/);
        const body = bodyLines.join('\n').trim();
        const headerMatch = headerLine.trim().match(/^\[Chunk\s+(\d+)\s+[—-]\s+(.+?)\s+[—-]\s+Section:\s*(.+?)\]$/);

        if (!headerMatch) {
            return {
                chunk: {
                    type: 'paragraph_block',
                    heading: `Citation ${index + 1}`,
                    content: block.trim(),
                }
            };
        }

        const rawType = headerMatch[2].trim();
        const normalizedType = this.normalizeCitationType(rawType);

        return {
            chunk: {
                type: normalizedType,
                heading: headerMatch[3].trim(),
                content: normalizedType === 'table'
                    ? this.parseCitationTableString(body)
                    : body || block.trim(),
            }
        };
    }

    private normalizeCitationType(rawType: string): string {
        const normalized = rawType.toLowerCase().trim();

        if (normalized === 'table') {
            return 'table';
        }

        if (normalized.includes('paragraph')) {
            return 'paragraph_block';
        }

        return normalized.replace(/\s+/g, '_');
    }

    private parseCitationTableString(body: string): RagCitationTable | string {
        const lines = body
            .split(/\r?\n/)
            .map(line => line.trim())
            .filter(Boolean);

        if (lines.length === 0) {
            return body;
        }

        const tableLines = this.stripMarkdownTableSeparator(lines);
        const rows = tableLines.map(line => this.splitCitationTableLine(line));
        const width = Math.max(...rows.map(row => row.length), 0);

        if (width <= 1) {
            return body;
        }

        return rows.map(row => this.normalizeCitationRow(row, width));
    }

    private isMarkdownTableText(text: string): boolean {
        const lines = text
            .split(/\r?\n/)
            .map(line => line.trim())
            .filter(Boolean);

        return lines.length >= 2
            && lines[0].includes('|')
            && this.isMarkdownTableSeparator(lines[1]);
    }

    private stripMarkdownTableSeparator(lines: string[]): string[] {
        if (lines.length >= 2 && this.isMarkdownTableSeparator(lines[1])) {
            return [lines[0], ...lines.slice(2)];
        }

        return lines;
    }

    private splitCitationTableLine(line: string): string[] {
        if (!line.includes('|')) {
            return [line];
        }

        return line
            .split('|')
            .map(cell => cell.trim())
            .filter((cell, idx, all) => !(
                all.length > 1
                && cell === ''
                && (idx === 0 || idx === all.length - 1)
            ));
    }

    private parseMarkdownHeading(line: string): string | null {
        const match = line.trim().match(/^#{1,6}\s+(.+?)\s*$/);
        return match ? match[1].trim() : null;
    }

    private parseSourceLine(line: string): string | null {
        const stripped = line.trim().replace(/^[*_]+|[*_]+$/g, '').trim();
        if (!/^source\s*:/i.test(stripped)) {
            return null;
        }

        return stripped;
    }

    private toDownloadFileName(title: string): string {
        const value = title
            .toLowerCase()
            .replace(/[^a-z0-9]+/g, '-')
            .replace(/^-+|-+$/g, '');

        return value || 'visualization';
    }

    private parseScenarioLabel(line: string): string | null {
        const stripped = line.trim();
        const match = stripped.match(/^\(\s*(scenario\s+\d+)\s*\)$/i);
        return match ? match[1].replace(/\s+/g, ' ').trim() : null;
    }

    private isMarkdownTableStart(lines: string[], index: number): boolean {
        if (index + 1 >= lines.length) {
            return false;
        }

        const header = lines[index].trim();
        const separator = lines[index + 1].trim();

        return header.includes('|') && this.isMarkdownTableSeparator(separator);
    }

    private isMarkdownTableSeparator(line: string): boolean {
        return /^\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?$/.test(line);
    }

    private parseMarkdownTable(
        lines: string[],
        startIndex: number,
        pendingHeading: string | null,
        pendingTableLabel: string | null,
        pendingSource: string | null,
        tableIndex: number
    ): { table: RenderableRagTable; nextIndex: number } {
        const headers = this.splitMarkdownRow(lines[startIndex]);
        const normalizedHeaders = this.normalizeCitationRow(headers, headers.length);
        const rows: string[][] = [];

        let index = startIndex + 2;
        while (index < lines.length) {
            const line = lines[index].trim();
            if (!line || !line.includes('|')) {
                break;
            }

            rows.push(this.normalizeCitationRow(this.splitMarkdownRow(lines[index]), normalizedHeaders.length));
            index += 1;
        }

        return {
            table: {
                title: pendingTableLabel?.trim() || pendingHeading?.trim() || `Retrieved Table ${tableIndex}`,
                source: pendingSource || undefined,
                headers: normalizedHeaders,
                rows,
            },
            nextIndex: index,
        };
    }

    private splitMarkdownRow(line: string): string[] {
        return line
            .trim()
            .replace(/^\|/, '')
            .replace(/\|$/, '')
            .split('|')
            .map(cell => cell.trim());
    }

    private normalizeNarrativeText(text: string): string {
        return text
            .replace(/\n{3,}/g, '\n\n')
            .trim();
    }

    ngAfterViewChecked(): void {
        this.renderSavedVisualizations();

        if (this.scrollOnNewMessage && !this.userHasScrolledUp) {
            this.scrollToBottom();
        }
    }

    onScroll(): void {
        const el = this.scrollContainer?.nativeElement;
        if (!el) return;
        const threshold = 100;
        const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
        this.showScrollToBottom = distanceFromBottom > threshold;
        this.userHasScrolledUp = distanceFromBottom > threshold;
    }

    scrollToBottom(): void {
        try {
            const el = this.scrollContainer?.nativeElement;
            if (el) {
                el.scrollTop = el.scrollHeight;
            }
        } catch { }
    }

    trackMsg(index: number, msg: ChatMessage): string {
        return msg.id;
    }

    resetScrollState(): void {
        this.userHasScrolledUp = false;
        this.showScrollToBottom = false;
        if (!this.messages?.length) {
            if (this.scrollContainer?.nativeElement) {
                this.scrollContainer.nativeElement.scrollTop = 0;
            }
            return;
        }
        setTimeout(() => this.scrollToBottom(), 50);
    }
}


