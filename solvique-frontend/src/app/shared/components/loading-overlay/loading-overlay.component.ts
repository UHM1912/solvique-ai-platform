import { Component, Input } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
    selector: 'app-loading-overlay',
    standalone: true,
    imports: [CommonModule],
    template: `
        <div class="overlay" *ngIf="show">
            <div class="spinner-container">
                <div class="spinner"></div>
                <p class="loading-text">Processing…</p>
            </div>
        </div>
    `,
    styles: [`
        .overlay {
            position: fixed;
            inset: 0;
            z-index: 9000;
            display: flex;
            align-items: center;
            justify-content: center;
            background: rgba(0, 0, 0, 0.35);
            backdrop-filter: blur(6px);
            animation: fadeIn 0.2s ease-out;
        }

        .spinner-container {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 1rem;
        }

        .spinner {
            width: 40px;
            height: 40px;
            border: 3px solid rgba(255, 255, 255, 0.2);
            border-top-color: var(--color-primary, #6366f1);
            border-radius: 50%;
            animation: spin 0.8s linear infinite;
        }

        .loading-text {
            color: #ffffff;
            font-size: 0.9rem;
            font-weight: 500;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        @keyframes fadeIn {
            from { opacity: 0; }
            to { opacity: 1; }
        }
    `]
})
export class LoadingOverlayComponent {
    @Input() show = false;
}
