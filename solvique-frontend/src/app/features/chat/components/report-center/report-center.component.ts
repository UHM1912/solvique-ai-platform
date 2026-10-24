import {
    Component,
    Input,
    Output,
    EventEmitter,
    OnInit,
    OnChanges,
    SimpleChanges,
    ChangeDetectorRef
} from '@angular/core';
import { CommonModule } from '@angular/common';
import {
    LucideAngularModule,
    FileText,
    Download,
    RefreshCw,
    Sparkles,
    CheckCircle2,
    Calendar,
    Layers,
    Table,
    BarChart3,
    BookOpen,
    HelpCircle
} from 'lucide-angular';
import { ToastrService } from 'ngx-toastr';

import { ThemeService } from '../../../../core/services/theme.service';
import { ChatService } from '../../services/chat.service';
import {
    ChatMessage,
    ReportSection
} from '../../../../shared/interfaces/chat.interface';

@Component({
    selector: 'app-report-center',
    standalone: true,
    imports: [CommonModule, LucideAngularModule],
    templateUrl: './report-center.component.html',
    styleUrls: ['./report-center.component.scss']
})
export class ReportCenterComponent implements OnInit, OnChanges {
    readonly FileText = FileText;
    readonly Download = Download;
    readonly RefreshCw = RefreshCw;
    readonly Sparkles = Sparkles;
    readonly CheckCircle2 = CheckCircle2;
    readonly Calendar = Calendar;
    readonly Layers = Layers;
    readonly Table = Table;
    readonly BarChart3 = BarChart3;
    readonly BookOpen = BookOpen;
    readonly HelpCircle = HelpCircle;

    @Input() conversationId?: string;
    @Input() conversationTitle?: string;
    @Input() messages: ChatMessage[] = [];
    @Output() requestAssistant = new EventEmitter<void>();

    sections: ReportSection[] = [];
    isLoadingPreview = false;
    isDownloading = false;
    lastGeneratedAt: Date | null = null;

    constructor(
        public themeService: ThemeService,
        private chatService: ChatService,
        private toastr: ToastrService,
        private cdRef: ChangeDetectorRef
    ) {}

    ngOnInit(): void {
        if (this.conversationId && this.hasConversationContent) {
            this.loadReportPreview();
        }
    }

    ngOnChanges(changes: SimpleChanges): void {
        if (changes['conversationId'] || changes['messages']) {
            if (this.conversationId && this.hasConversationContent) {
                this.loadReportPreview();
            } else {
                this.sections = [];
            }
        }
    }

    get hasConversationContent(): boolean {
        return this.messages.some(m => m.sender === 'assistant');
    }

    get turnCount(): number {
        return this.messages.filter(m => m.sender === 'user').length;
    }

    get displayDate(): Date {
        if (this.lastGeneratedAt) return this.lastGeneratedAt;
        if (this.messages.length > 0) {
            return this.messages[this.messages.length - 1].timestamp;
        }
        return new Date();
    }

    async loadReportPreview(): Promise<void> {
        if (!this.conversationId || !this.hasConversationContent) return;

        this.isLoadingPreview = true;
        this.cdRef.detectChanges();

        try {
            const preview = await this.chatService.getReportPreview(this.conversationId);
            if (preview && preview.length > 0) {
                this.sections = preview;
                this.lastGeneratedAt = new Date();
            } else {
                this.sections = this.generateFallbackPreview();
                this.lastGeneratedAt = new Date();
            }
        } catch (err) {
            console.warn('Report preview fallback generated due to error:', err);
            this.sections = this.generateFallbackPreview();
            this.lastGeneratedAt = new Date();
        } finally {
            this.isLoadingPreview = false;
            this.cdRef.detectChanges();
        }
    }

    private generateFallbackPreview(): ReportSection[] {
        const result: ReportSection[] = [];
        const assistantMsgs = this.messages.filter(m => m.sender === 'assistant');

        result.push({
            heading: 'Executive Summary',
            body: `This analytical report synthesizes findings from ${this.turnCount} business inquiries across enterprise databases and predictive models. Key findings and supporting evidence are detailed in the sections below.`,
            kind: 'analysis'
        });

        let idx = 1;
        for (const msg of assistantMsgs) {
            if (msg.text) {
                result.push({
                    heading: `${idx}. Analytical Findings`,
                    body: msg.text,
                    kind: 'analysis'
                });
                idx++;
            }
        }

        return result;
    }

    downloadDocx(): void {
        if (!this.conversationId || !this.hasConversationContent || this.isDownloading) {
            return;
        }

        this.isDownloading = true;
        this.cdRef.detectChanges();

        try {
            const url = this.chatService.getReportDownloadUrl(this.conversationId);
            window.open(url, '_blank', 'noopener');
            this.toastr.success('Your Solvique Executive Report (.docx) is downloading.', 'Report Generated');
        } catch (err: any) {
            this.toastr.error('The report couldn’t be downloaded right now. Please try again shortly.', 'Export Error');
        } finally {
            setTimeout(() => {
                this.isDownloading = false;
                this.cdRef.detectChanges();
            }, 1800);
        }
    }

    getAssetImageUrl(assetId: string): string {
        return this.chatService.getReportAssetUrl(assetId);
    }
}
