import { Component, EventEmitter, Input, Output, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LucideAngularModule, Plus, Search, Trash2, Menu, X, Sun, Moon, MessageSquare } from 'lucide-angular';
import { ThemeService } from '../../../../core/services/theme.service';
import { ChatSummary } from '../../../../shared/interfaces/chat.interface';

@Component({
    selector: 'app-sidebar',
    standalone: true,
    imports: [CommonModule, FormsModule, LucideAngularModule],
    templateUrl: './sidebar.component.html',
    styleUrls: ['./sidebar.component.scss']
})
export class SidebarComponent {
    readonly Plus = Plus;
    readonly Search = Search;
    readonly Trash2 = Trash2;
    readonly Menu = Menu;
    readonly X = X;
    readonly Sun = Sun;
    readonly Moon = Moon;
    readonly MessageSquare = MessageSquare;

    themeService = inject(ThemeService);

    @Input() isCollapsed = false;
    @Input() isMobile = false;
    @Input() mobileOpen = false;
    @Input() chats: ChatSummary[] = [];
    @Input() isLoading = false;

    @Output() mobileOpenChange = new EventEmitter<boolean>();
    @Output() requestToggle = new EventEmitter<void>();
    @Output() newChat = new EventEmitter<void>();
    @Output() selectChatEvent = new EventEmitter<string>();
    @Output() deleteChatEvent = new EventEmitter<string>();
    @Output() searchChange = new EventEmitter<string | null>();

    searchTerm = '';

    onSearchInput(): void {
        this.searchChange.emit(this.searchTerm.trim() || null);
    }

    clearSearch(): void {
        this.searchTerm = '';
        this.searchChange.emit(null);
    }

    onDeleteChat(event: MouseEvent, chatId: string): void {
        event.stopPropagation();
        this.deleteChatEvent.emit(chatId);
    }

    toggleTheme(): void {
        this.themeService.toggle();
    }
}
