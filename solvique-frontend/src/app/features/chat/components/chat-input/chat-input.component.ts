import { Component, ElementRef, EventEmitter, Input, Output, ViewChild } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { LucideAngularModule, Send } from 'lucide-angular';
import { trigger, style, animate, transition } from '@angular/animations';
import { ChatSendPayload } from '../../../../shared/interfaces/chat.interface';

@Component({
    selector: 'app-chat-input',
    standalone: true,
    imports: [CommonModule, FormsModule, LucideAngularModule],
    templateUrl: './chat-input.component.html',
    styleUrls: ['./chat-input.component.scss'],
    animations: [
        trigger('slideUp', [
            transition(':enter', [
                style({ opacity: 0, transform: 'translateY(20px)' }),
                animate('300ms ease-out', style({ opacity: 1, transform: 'translateY(0)' })),
            ]),
        ]),
    ],
})
export class ChatInputComponent {
    readonly Send = Send;

    message = '';

    @Input() isLoading = false;
    @Input() set prefillText(val: string) {
    if (val) {
        this.message = val;
        setTimeout(() => {
            const el = this.textarea?.nativeElement;
            if (!el) return;
            el.style.height = 'auto';
            el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
            el.focus();
        }, 0);
    }
}
    @Output() send = new EventEmitter<ChatSendPayload>();
    @ViewChild('textarea') textarea!: ElementRef<HTMLTextAreaElement>;

    handleEnterKey(event: KeyboardEvent): void {
        if (event.shiftKey) return;  // Allow Shift+Enter for newlines
        event.preventDefault();
        if (this.isLoading) return;
        this.onSend();
    }

    onSend(): void {
        if (this.isLoading) return;
        const text = this.message.trim();
        if (!text) return;

        this.send.emit({ text });
        this.message = '';
        setTimeout(() => this.resetTextareaHeight(), 0);
    }

    autoResize(event: Event): void {
        const textarea = event.target as HTMLTextAreaElement;
        if (textarea) {
            textarea.style.height = 'auto';
            const maxHeight = 200;
            textarea.style.height = `${Math.min(textarea.scrollHeight, maxHeight)}px`;
        }
    }

    private resetTextareaHeight(): void {
        if (this.textarea) {
            this.textarea.nativeElement.style.height = 'auto';
        }
    }
}
