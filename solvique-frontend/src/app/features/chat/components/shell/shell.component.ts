import { Component, HostListener, ViewChild, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
    LucideAngularModule,
    ArrowDown,
    FileText,
    MessageSquare,
    BarChart3,
    Sparkles,
    Download,
    History,
    Plus
} from 'lucide-angular';
import { animate, style, transition, trigger } from '@angular/animations';
import { ToastrService } from 'ngx-toastr';

import { SidebarComponent } from '../sidebar/sidebar.component';
import { ChatComponent } from '../chat/chat.component';
import { ChatInputComponent } from '../chat-input/chat-input.component';
import { DataStudioComponent } from '../data-studio/data-studio.component';
import { ReportCenterComponent } from '../report-center/report-center.component';
import { LoadingOverlayComponent } from '../../../../shared/components/loading-overlay/loading-overlay.component';

import { ChatService } from '../../services/chat.service';
import {
    ChatSession,
    ChatSummary,
    ChatMessage,
    ChatSendPayload,
    ChatResponse,
    SolviqueView
} from '../../../../shared/interfaces/chat.interface';

@Component({
    selector: 'app-shell',
    standalone: true,
    imports: [
        CommonModule,
        SidebarComponent,
        ChatComponent,
        ChatInputComponent,
        DataStudioComponent,
        ReportCenterComponent,
        LucideAngularModule,
        LoadingOverlayComponent
    ],
    templateUrl: './shell.component.html',
    styleUrls: ['./shell.component.scss'],
    animations: [
        trigger('fade', [
            transition(':enter', [
                style({ opacity: 0, transform: 'translateY(10px)' }),
                animate('200ms ease-out', style({ opacity: 1, transform: 'translateY(0)' }))
            ]),
            transition(':leave', [
                animate('200ms ease-in', style({ opacity: 0, transform: 'translateY(10px)' }))
            ])
        ])
    ]
})
export class ShellComponent implements OnInit {
    readonly ArrowDown = ArrowDown;
    readonly FileText = FileText;
    readonly MessageSquare = MessageSquare;
    readonly BarChart3 = BarChart3;
    readonly Sparkles = Sparkles;
    readonly Download = Download;
    readonly History = History;
    readonly Plus = Plus;

    activeView: SolviqueView = 'assistant';

    get datasetCount(): number {
        if (!this.currentChat?.messages) return 0;
        return this.currentChat.messages.filter(
            m => m.sender === 'assistant' && (
                (Array.isArray(m.results) && m.results.length > 0) ||
                (Array.isArray(m.tool_results) && m.tool_results.some(p => Array.isArray(p.results) && p.results.length > 0))
            )
        ).length;
    }

    setView(view: SolviqueView): void {
        this.activeView = view;
        this.cdRef.detectChanges();
    }

    prefillText = '';

    onSuggestionSelected(text: string): void {
        this.activeView = 'assistant';
        Promise.resolve().then(() => {
            this.prefillText = '';
            this.cdRef.detectChanges();
            Promise.resolve().then(() => {
                this.prefillText = text;
                this.cdRef.detectChanges();
            });
        });
    }
    private readonly MOBILE_BREAK = 768;

    isMobileView = false;
    mobileOpen = false;
    isCollapsed = true;
    isLoadingReply = false;
    isWaitingForApi = false;
    isAppendingNewMessage = false;
    isLoadingSessions = true;
    isReportLoading = false;

    sidebarChats: ChatSummary[] = [];
    currentChat: ChatSession | null = null;

    private allSessions: { [id: string]: ChatSession } = {};

    _searchTerm: string | null = null;
    get searchTerm(): string | null { return this._searchTerm; }
    set searchTerm(value: string | null) {
        if (this._searchTerm !== value) {
            this._searchTerm = value;
            this.updateSidebar();
        }
    }

    // Tab visibility tracking for typing skip
    private tabWasHidden = false;
    private onVisibilityChange = () => {
        if (document.hidden) this.tabWasHidden = true;
    };

    @ViewChild('chatComp') chatComponent!: ChatComponent;

    constructor(
        private cdRef: ChangeDetectorRef,
        private chatService: ChatService,
        private toastr: ToastrService
    ) {}

    ngOnInit(): void {
        this.updateViewMode();
        document.addEventListener('visibilitychange', this.onVisibilityChange);
        this.initSessions();
    }

    ngOnDestroy(): void {
        document.removeEventListener('visibilitychange', this.onVisibilityChange);
    }

    /* ─── Load sessions from backend ────────────────────── */
    private async initSessions(): Promise<void> {
        this.isLoadingSessions = true;
        try {
            const convs = await this.chatService.getConversations();
            this.allSessions = {};

            for (const conv of convs) {
                this.allSessions[conv.id] = {
                    id: conv.id,
                    title: conv.title || 'New Chat',
                    createdAt: new Date(conv.created),
                    messages: [],
                    isTyping: false
                };
            }

            // Pick most recent chat
            const ids = Object.keys(this.allSessions);
            if (ids.length > 0) {
                const newest = ids.sort((a, b) =>
                    this.allSessions[b].createdAt.getTime() - this.allSessions[a].createdAt.getTime()
                )[0];
                this.currentChat = this.allSessions[newest];

                // Lazy-load messages for initial chat
                if (this.currentChat.messages.length === 0) {
                    const detail = await this.chatService.getConversation(this.currentChat.id);
                    if (detail) {
                        this.currentChat.messages = this.chatService.mapStoredMessages(detail.messages, detail.id);
                        this.allSessions[detail.id] = this.currentChat;
                    }
                }
            } else {
                this.onNewChat();
            }

            this.updateSidebar();
            if (this.currentChat?.messages.length) {
                setTimeout(() => this.chatComponent?.scrollToBottom(), 150);
            }
        } catch (err) {
            console.warn('Failed to load sessions', err);
            this.onNewChat();
        } finally {
            this.isLoadingSessions = false;
        }
    }

    /* ─── Sidebar management ────────────────────────────── */
    private updateSidebar(): void {
        const sessions = Object.values(this.allSessions);
        const lower = this._searchTerm?.trim()?.toLowerCase();

        const filtered = lower
            ? sessions.filter(s =>
                s.title.toLowerCase().includes(lower) ||
                s.messages.some(m => m.text?.toLowerCase().includes(lower))
            )
            : sessions;

        this.sidebarChats = filtered
            .map(s => ({
                id: s.id,
                title: s.title || 'New Chat',
                lastMessageAt: s.createdAt.toISOString(),
                selected: this.currentChat?.id === s.id
            }))
            .sort((a, b) => new Date(b.lastMessageAt).getTime() - new Date(a.lastMessageAt).getTime());
    }

    /* ─── New Chat ──────────────────────────────────────── */
    private isCreatingChat = false;

    onNewChat(): void {
        if (this.isCreatingChat) return;
        this.isCreatingChat = true;

        const id = 'conv-' + Date.now();
        const session: ChatSession = {
            id,
            title: 'New Chat',
            createdAt: new Date(),
            messages: [],
            isTyping: false
        };

        this.allSessions[id] = session;
        this.currentChat = session;
        this.updateSidebar();
        if (this.isMobileView) this.mobileOpen = false;
        setTimeout(() => this.chatComponent?.resetScrollState(), 0);
        setTimeout(() => this.isCreatingChat = false, 300);
    }

    /* ─── Select Chat ───────────────────────────────────── */
    async onSelectChat(id: string): Promise<void> {
        if (this.currentChat?.id === id) return;

        const session = this.allSessions[id];
        if (!session) return;

        // Lazy-load messages
        if (session.messages.length === 0) {
            this.isWaitingForApi = true;
            try {
                const detail = await this.chatService.getConversation(id);
                if (detail) {
                    session.messages = this.chatService.mapStoredMessages(detail.messages, detail.id);
                    this.allSessions[id] = session;
                }
            } finally {
                this.isWaitingForApi = false;
            }
        }

        this.currentChat = session;
        this.updateSidebar();
        if (this.isMobileView) this.mobileOpen = false;
        setTimeout(() => this.chatComponent?.resetScrollState(), 0);
    }

    /* ─── Delete Chat ───────────────────────────────────── */
    async handleDeleteChat(chatId: string): Promise<void> {
        if (!chatId) return;

        this.isWaitingForApi = true;
        try {
            const deleted = await this.chatService.deleteConversation(chatId);
            if (!deleted) {
                this.toastr.error('Failed to delete chat.', 'Error');
                return;
            }

            delete this.allSessions[chatId];

            if (this.currentChat?.id === chatId) {
                this.currentChat = null;
                const remaining = Object.keys(this.allSessions);
                if (remaining.length > 0) {
                    this.currentChat = this.allSessions[remaining[0]];
                } else {
                    this.onNewChat();
                    return;
                }
            }

            this.updateSidebar();
        } finally {
            this.isWaitingForApi = false;
        }
    }

    /* ─── Send Message ──────────────────────────────────── */
    async onMessageSend(payload: ChatSendPayload): Promise<void> {
        if (!this.currentChat) this.onNewChat();
        if (!this.currentChat) return;

        this.isAppendingNewMessage = true;
        const genId = () => `${Date.now()}-${Math.floor(Math.random() * 100000)}`;

        const userMsg: ChatMessage = {
            id: genId(),
            conversationId: this.currentChat.id,
            sender: 'user',
            text: payload.text,
            timestamp: new Date(),
            renderComplete: true
        };

        if (this.currentChat.messages.length === 0) {
            this.currentChat.title = payload.text.substring(0, 60);
        }
        this.currentChat.messages.push(userMsg);

        const botMsg: ChatMessage = {
            id: genId(),
            conversationId: this.currentChat.id,
            sender: 'assistant',
            text: '',
            timestamp: new Date(),
            isTyping: true,
            renderComplete: false
        };
        this.currentChat.messages.push(botMsg);
        this.currentChat.isTyping = true;
        this.isLoadingReply = true;
        this.updateSidebar();

        try {
            const responses = await this.chatService.sendMessage(
                payload.text,
                this.currentChat.id
            );

            if (responses.length === 0) {
                throw new Error('Server returned an empty response.');
            }

            this.updateConversationId(
                responses.find(response => response.conversation_id)?.conversation_id
            );

            const placeholderIndex = this.currentChat.messages.lastIndexOf(botMsg);
            if (placeholderIndex >= 0) {
                this.currentChat.messages.splice(placeholderIndex, 1);
            }

            await this.renderAssistantResponses(responses, genId);
            this.updateSidebar();

            setTimeout(() => {
                if (this.isAppendingNewMessage && !this.chatComponent?.userHasScrolledUp) {
                    this.chatComponent?.scrollToBottom();
                }
                this.isAppendingNewMessage = false;
            }, 100);

        } catch (err: any) {
            const idx = this.currentChat.messages.lastIndexOf(botMsg);
            if (idx >= 0) this.currentChat.messages.splice(idx, 1);
            this.toastr.error(err?.message || 'Server error. Please try again.', 'Error');
        } finally {
            if (this.currentChat) {
                this.currentChat.isTyping = false;
                this.isLoadingReply = false;
            }
        }
    }

    private async renderAssistantResponses(
        responses: ChatResponse[],
        genId: () => string
    ): Promise<void> {
        if (!this.currentChat) return;

        for (const response of responses) {
            const assistantMsg = this.createAssistantMessage(response, genId());
            this.currentChat.messages.push(assistantMsg);
            this.cdRef.detectChanges();

            if (this.chatComponent?.hasDisplayTables(assistantMsg)) {
                this.chatComponent.expandedTable.add(assistantMsg.id);
            }

            const fullText = assistantMsg.rawText || '';
            const displayText = this.chatComponent?.shouldExtractTablesFromTool(assistantMsg.tool)
                ? (this.chatComponent?.getNarrativeTextForDisplay(fullText) ?? fullText)
                : fullText;

            if (displayText) {
                assistantMsg.isTyping = true;
                await this.typeText(assistantMsg, displayText);
                assistantMsg.isTyping = false;
            }

            assistantMsg.renderComplete = true;
            this.cdRef.detectChanges();
        }
    }

    private createAssistantMessage(response: ChatResponse, id: string): ChatMessage {
        const fullText = this.getResponseDisplayText(response);
        const messageId = response.message_id || id;

        return {
            id: messageId,
            conversationId: response.conversation_id || this.currentChat?.id,
            sender: 'assistant',
            text: '',
            rawText: fullText || undefined,
            timestamp: new Date(),
            tool: this.normalizeTool(response.tool),
            sqlQuery: response.sql_query || undefined,
            results: response.results || undefined,
            citations: response.citations || undefined,
            doc_citations: response.doc_citations || undefined,   // ← add
            web_citations: response.web_citations || undefined,   // ← add
            tool_results: response.tool_results || response.metadata?.['tool_results'] || [],
            metadata: response.metadata || undefined,
            error: response.error || undefined,
            isTyping: false,
            renderComplete: !fullText
        };
    }

    private getResponseDisplayText(response: ChatResponse): string {
        if (response.explanation !== undefined && response.explanation !== null) {
            return this.normalizeResponseText(response.explanation);
        }

        if (typeof response.results === 'string') {
            return this.normalizeResponseText(response.results);
        }

        if (response.tool === 'rag_tool' && response.error) {
            return `I couldn't generate an answer for this retrieval request. ${response.error} Please try again.`;
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
        // Handles payloads like:
        // [{'type': 'text', 'text': '...summary...', 'extras': {...}}]
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

        // Guard against partial/truncated captures from malformed structured payloads.
        if (value.includes(`'text'`) || value.includes(`"text"`)) {
            const minExpectedLength = Math.max(40, Math.floor(value.length * 0.08));
            if (joined.length < minExpectedLength) {
                return '';
            }
        }

        return joined;
    }

    private normalizeTool(tool?: ChatResponse['tool']): ChatMessage['tool'] {
        if (tool === 'rag_tools') {
            return 'rag_tool';
        }

        return tool === 'error' || tool === 'out_of_scope' ? undefined : tool;
    }

    private updateConversationId(conversationId?: string): void {
        if (!conversationId || !this.currentChat || conversationId === this.currentChat.id) {
            return;
        }

        const oldId = this.currentChat.id;
        this.currentChat.id = conversationId;
        delete this.allSessions[oldId];
        this.allSessions[conversationId] = this.currentChat;
    }

    /* ─── Typing animation ──────────────────────────────── */
    private async typeText(message: ChatMessage, fullText: string, delayPerChar = 4): Promise<void> {
        message.text = '';
        this.tabWasHidden = false;

        for (let i = 0; i <= fullText.length; i++) {
            if (this.tabWasHidden) {
                message.text = fullText;
                this.cdRef.detectChanges();
                break;
            }
            message.text = fullText.slice(0, i);
            this.cdRef.detectChanges();

            if (i % 50 === 0 || i === fullText.length) {
                if (!this.chatComponent?.userHasScrolledUp) {
                    this.chatComponent?.scrollToBottom();
                }
            }
            await new Promise(r => setTimeout(r, delayPerChar));
        }
    }

    /* ─── Responsive layout ─────────────────────────────── */
    @HostListener('window:resize')
    onResize(): void {
        this.updateViewMode();
    }

    private updateViewMode(): void {
        const wasMobile = this.isMobileView;
        this.isMobileView = window.innerWidth <= this.MOBILE_BREAK;
        if (wasMobile && !this.isMobileView) this.mobileOpen = false;
    }

    toggleCollapseRequest(): void {
        if (this.isMobileView) {
            this.mobileOpen = !this.mobileOpen;
        } else {
            this.isCollapsed = !this.isCollapsed;
        }
    }

    @HostListener('document:click', ['$event'])
    closeHistoryOnOutsideClick(event: MouseEvent): void {
        if (this.isMobileView || this.isCollapsed) return;

        const target = event.target;
        if (!(target instanceof Element)) return;
        if (target.closest('app-sidebar, .rail-history')) return;

        this.isCollapsed = true;
    }

    onBackdropClick(): void {
        this.mobileOpen = false;
    }

    downloadReportDocx(): void {
        if (!this.currentChat?.id || this.currentChat.messages.length === 0 || this.isReportLoading) {
            return;
        }

        this.isReportLoading = true;
        try {
            window.open(this.chatService.getReportDownloadUrl(this.currentChat.id), '_blank', 'noopener');
            this.toastr.success('Your Solvique Executive Report (.docx) is downloading.', 'Report Export');
        } catch (err: any) {
            this.toastr.error(err?.message || 'Failed to start report download.', 'Report Error');
        } finally {
            window.setTimeout(() => {
                this.isReportLoading = false;
                this.cdRef.detectChanges();
            }, 1200);
        }
    }

    // Backwards compatibility alias
    downloadReportPdf(): void {
        this.downloadReportDocx();
    }

    canOpenReport(): boolean {
        return !!this.currentChat?.id && this.currentChat.messages.length > 0;
    }
}

