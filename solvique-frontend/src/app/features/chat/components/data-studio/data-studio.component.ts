import {
    Component,
    Input,
    Output,
    EventEmitter,
    OnInit,
    OnChanges,
    OnDestroy,
    SimpleChanges,
    ElementRef,
    ViewChild,
    ChangeDetectorRef
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import {
    LucideAngularModule,
    BarChart3,
    LineChart,
    PieChart,
    TrendingUp,
    Download,
    Table,
    Search,
    Maximize2,
    RefreshCw,
    Sparkles,
    Layers,
    FileSpreadsheet,
    FileCode,
    Info,
    ArrowRight
} from 'lucide-angular';
import Plotly from 'plotly.js-dist-min';
import { Subscription } from 'rxjs';

import { ThemeService } from '../../../../core/services/theme.service';
import { ChatService } from '../../services/chat.service';
import {
    ChatMessage,
    ChatResultRow,
    ChartSpec,
    VisualizationOption
} from '../../../../shared/interfaces/chat.interface';

export interface StudioDataset {
    id: string;
    messageId: string;
    title: string;
    queryPrompt?: string;
    sourceTool: 'sql_tool' | 'ml_tool';
    sourceToolLabel: string;
    data: ChatResultRow[];
    columns: string[];
    chartSpecs?: ChartSpec[];
    options: VisualizationOption[];
    selectedChartType?: string;
}

@Component({
    selector: 'app-data-studio',
    standalone: true,
    imports: [CommonModule, FormsModule, LucideAngularModule],
    templateUrl: './data-studio.component.html',
    styleUrls: ['./data-studio.component.scss']
})
export class DataStudioComponent implements OnInit, OnChanges, OnDestroy {
    readonly BarChart3 = BarChart3;
    readonly LineChart = LineChart;
    readonly PieChart = PieChart;
    readonly TrendingUp = TrendingUp;
    readonly Download = Download;
    readonly Table = Table;
    readonly Search = Search;
    readonly Maximize2 = Maximize2;
    readonly RefreshCw = RefreshCw;
    readonly Sparkles = Sparkles;
    readonly Layers = Layers;
    readonly FileSpreadsheet = FileSpreadsheet;
    readonly FileCode = FileCode;
    readonly Info = Info;
    readonly ArrowRight = ArrowRight;

    @Input() messages: ChatMessage[] = [];
    @Input() conversationId?: string;
    @Output() suggestionSelected = new EventEmitter<string>();

    @ViewChild('chartContainer') chartContainer?: ElementRef<HTMLDivElement>;

    datasets: StudioDataset[] = [];
    activeDataset: StudioDataset | null = null;
    activeTab: 'visual' | 'table' | 'json' = 'visual';

    tableSearchTerm = '';
    isGeneratingChart = false;
    currentFigure: any = null;

    private themeSub?: Subscription;

    constructor(
        public themeService: ThemeService,
        private chatService: ChatService,
        private cdRef: ChangeDetectorRef
    ) {}

    ngOnInit(): void {
        this.extractDatasets();
        this.themeSub = this.themeService.isDark$.subscribe(() => {
            if (this.currentFigure && this.chartContainer?.nativeElement) {
                this.renderPlotlyChart(this.currentFigure);
            }
        });
    }

    ngOnChanges(changes: SimpleChanges): void {
        if (changes['messages']) {
            this.extractDatasets();
        }
    }

    ngOnDestroy(): void {
        this.themeSub?.unsubscribe();
    }

    extractDatasets(): void {
        const found: StudioDataset[] = [];

        for (let i = 0; i < this.messages.length; i++) {
            const msg = this.messages[i];
            if (msg.sender !== 'assistant') continue;

            // Check primary results
            if (Array.isArray(msg.results) && msg.results.length > 0 && typeof msg.results[0] === 'object') {
                const userPrompt = this.findUserPromptBefore(i);
                const toolName = msg.tool === 'ml_tool' ? 'ml_tool' : 'sql_tool';
                const toolLabel = toolName === 'ml_tool' ? 'Predictive Intelligence' : 'Database Analytics';
                const cols = Object.keys(msg.results[0]);

                found.push({
                    id: `ds-${msg.id}`,
                    messageId: msg.id,
                    title: userPrompt || `${toolLabel} Result`,
                    queryPrompt: userPrompt,
                    sourceTool: toolName,
                    sourceToolLabel: toolLabel,
                    data: msg.results,
                    columns: cols,
                    chartSpecs: msg.chartSpecs || (msg.primaryVisualizationChartSpec ? [msg.primaryVisualizationChartSpec] : []),
                    options: this.buildOptionsForData(msg.results, toolName),
                    selectedChartType: msg.primaryVisualizationChartSpec?.chart_type || (this.isForecastData(msg.results) ? 'line' : 'bar')
                });
            }

            // Check multi-tool results
            if (Array.isArray(msg.tool_results)) {
                for (let j = 0; j < msg.tool_results.length; j++) {
                    const patch = msg.tool_results[j];
                    if (Array.isArray(patch.results) && patch.results.length > 0 && typeof patch.results[0] === 'object') {
                        const userPrompt = this.findUserPromptBefore(i);
                        const toolName = patch.tool === 'ml_tool' ? 'ml_tool' : 'sql_tool';
                        const toolLabel = toolName === 'ml_tool' ? 'Predictive Forecast' : 'Database Analytics';
                        const cols = Object.keys(patch.results[0]);

                        found.push({
                            id: `ds-${msg.id}-${j}`,
                            messageId: msg.id,
                            title: `${userPrompt || 'Analysis'} (${toolLabel})`,
                            queryPrompt: userPrompt,
                            sourceTool: toolName,
                            sourceToolLabel: toolLabel,
                            data: patch.results,
                            columns: cols,
                            chartSpecs: patch.chart_specs || [],
                            options: this.buildOptionsForData(patch.results, toolName),
                            selectedChartType: this.isForecastData(patch.results) ? 'line' : 'bar'
                        });
                    }
                }
            }
        }

        this.datasets = found;
        if (!this.activeDataset && found.length > 0) {
            this.selectDataset(found[found.length - 1]);
        } else if (this.activeDataset) {
            // Keep active dataset up to date
            const refreshed = found.find(d => d.id === this.activeDataset?.id);
            if (refreshed) {
                this.activeDataset = refreshed;
            } else if (found.length > 0) {
                this.selectDataset(found[found.length - 1]);
            } else {
                this.activeDataset = null;
            }
        }
    }

    private findUserPromptBefore(assistantIndex: number): string | undefined {
        for (let i = assistantIndex - 1; i >= 0; i--) {
            if (this.messages[i].sender === 'user') {
                return this.messages[i].text;
            }
        }
        return undefined;
    }

    private isForecastData(data: ChatResultRow[]): boolean {
        if (!data || data.length === 0) return false;
        const keys = Object.keys(data[0]);
        return keys.includes('date') && keys.includes('yhat');
    }

    private buildOptionsForData(data: ChatResultRow[], tool: 'sql_tool' | 'ml_tool'): VisualizationOption[] {
        if (this.isForecastData(data)) {
            return [
                { id: 'opt_line', label: 'Trend Line', description: 'Forecast trajectory with confidence bounds', chart_type: 'line' },
                { id: 'opt_bar', label: 'Daily Bar', description: 'Date by date prediction comparison', chart_type: 'bar' },
                { id: 'opt_area', label: 'Volume Area', description: 'Cumulative predicted volume', chart_type: 'area' }
            ];
        }

        return [
            { id: 'opt_bar', label: 'Bar Chart', description: 'Comparative metric distribution', chart_type: 'bar' },
            { id: 'opt_line', label: 'Line Chart', description: 'Trend over sequence or dates', chart_type: 'line' },
            { id: 'opt_scatter', label: 'Scatter Plot', description: 'Metric correlation view', chart_type: 'scatter' }
        ];
    }

    selectDataset(ds: StudioDataset): void {
        this.activeDataset = ds;
        this.tableSearchTerm = '';
        this.cdRef.detectChanges();

        // Render chart if available or trigger generation
        setTimeout(() => {
            if (ds.chartSpecs && ds.chartSpecs.length > 0) {
                try {
                    const fig = JSON.parse(ds.chartSpecs[0].figure_json);
                    this.renderPlotlyChart(fig);
                } catch {
                    this.generateChartForType(ds.selectedChartType || 'bar');
                }
            } else {
                this.generateChartForType(ds.selectedChartType || (this.isForecastData(ds.data) ? 'line' : 'bar'));
            }
        }, 50);
    }

    async generateChartForType(chartType: string): Promise<void> {
        if (!this.activeDataset) return;
        this.activeDataset.selectedChartType = chartType;
        this.isGeneratingChart = true;
        this.cdRef.detectChanges();

        try {
            const resp = await this.chatService.generateVisualization(
                this.conversationId,
                this.activeDataset.sourceTool,
                this.activeDataset.data,
                { chartType }
            );

            if (resp.chart_specs && resp.chart_specs.length > 0) {
                this.activeDataset.chartSpecs = resp.chart_specs;
                const figure = JSON.parse(resp.chart_specs[0].figure_json);
                this.renderPlotlyChart(figure);
            }
        } catch (err) {
            console.error('Data Studio visualization error:', err);
        } finally {
            this.isGeneratingChart = false;
            this.cdRef.detectChanges();
        }
    }

    private renderPlotlyChart(figure: any): void {
        if (!this.chartContainer?.nativeElement) return;
        this.currentFigure = figure;

        const isDark = this.themeService.isDark;
        const textColor = isDark ? '#E6EDF7' : '#102235';
        const mutedTextColor = isDark ? '#94A3B8' : '#64748B';
        const gridColor = isDark ? '#29374B' : '#E5EDF4';
        const chartBg = isDark ? '#111C2E' : '#FFFFFF';

        const layout = {
            ...(figure.layout || {}),
            autosize: true,
            paper_bgcolor: chartBg,
            plot_bgcolor: chartBg,
            font: { family: 'Inter, sans-serif', color: textColor, size: 12 },
            margin: { l: 60, r: 30, t: 50, b: 60 },
            xaxis: {
                ...(figure.layout?.xaxis || {}),
                color: mutedTextColor,
                gridcolor: gridColor,
                linecolor: gridColor,
                tickfont: { color: mutedTextColor, size: 11 },
                title: { font: { color: textColor, size: 12 } }
            },
            yaxis: {
                ...(figure.layout?.yaxis || {}),
                color: mutedTextColor,
                gridcolor: gridColor,
                linecolor: gridColor,
                tickfont: { color: mutedTextColor, size: 11 },
                title: { font: { color: textColor, size: 12 } }
            }
        };

        const config = {
            responsive: true,
            displayModeBar: false,
            displaylogo: false,
            modeBarButtonsToRemove: ['sendDataToCloud', 'lasso2d', 'select2d']
        };

        Plotly.react(this.chartContainer.nativeElement, figure.data || [], layout, config);
    }

    downloadChartPng(): void {
        if (!this.chartContainer?.nativeElement || !this.activeDataset) return;
        Plotly.downloadImage(this.chartContainer.nativeElement, {
            format: 'png',
            width: 1200,
            height: 700,
            filename: `solvique-chart-${this.activeDataset.selectedChartType || 'plot'}`
        });
    }

    downloadCsv(): void {
        if (!this.activeDataset || !this.activeDataset.data.length) return;
        const data = this.activeDataset.data;
        const cols = this.activeDataset.columns;

        const csvRows = [cols.join(',')];
        for (const row of data) {
            const values = cols.map(c => {
                const val = row[c] ?? '';
                const escaped = ('' + val).replace(/"/g, '""');
                return `"${escaped}"`;
            });
            csvRows.push(values.join(','));
        }

        const blob = new Blob([csvRows.join('\n')], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `solvique-data-${this.activeDataset.id}.csv`;
        link.click();
        URL.revokeObjectURL(url);
    }

    get filteredTableData(): ChatResultRow[] {
        if (!this.activeDataset) return [];
        if (!this.tableSearchTerm.trim()) return this.activeDataset.data;
        const term = this.tableSearchTerm.toLowerCase();
        return this.activeDataset.data.filter(row =>
            Object.values(row).some(v => String(v).toLowerCase().includes(term))
        );
    }

    get datasetStats(): { totalRows: number; columnCount: number; numericCols: number } {
        if (!this.activeDataset) return { totalRows: 0, columnCount: 0, numericCols: 0 };
        const rows = this.activeDataset.data;
        const cols = this.activeDataset.columns;
        let numCols = 0;
        if (rows.length > 0) {
            for (const c of cols) {
                if (typeof rows[0][c] === 'number') numCols++;
            }
        }
        return {
            totalRows: rows.length,
            columnCount: cols.length,
            numericCols: numCols
        };
    }
}
