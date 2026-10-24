import { Injectable } from '@angular/core';
import { BehaviorSubject } from 'rxjs';

@Injectable({
    providedIn: 'root'
})
export class ThemeService {
    private readonly STORAGE_KEY = 'solvique-theme';
    private _isDark = false;
    readonly isDark$ = new BehaviorSubject<boolean>(false);

    get isDark(): boolean {
        return this._isDark;
    }

    constructor() {
        const stored = localStorage.getItem(this.STORAGE_KEY) || localStorage.getItem('uqe-theme');
        if (stored === 'dark') {
            this._isDark = true;
        } else if (stored === 'light') {
            this._isDark = false;
        } else {
            this._isDark = true;
        }
        this.isDark$.next(this._isDark);
        this.applyTheme();
    }

    toggle(): void {
        this._isDark = !this._isDark;
        this.isDark$.next(this._isDark);
        localStorage.setItem(this.STORAGE_KEY, this._isDark ? 'dark' : 'light');

        document.body.classList.add('theme-transitioning');
        this.applyTheme();
        requestAnimationFrame(() => {
            requestAnimationFrame(() => {
                document.body.classList.remove('theme-transitioning');
            });
        });
    }

    private applyTheme(): void {
        if (this._isDark) {
            document.body.classList.add('dark');
            document.documentElement.setAttribute('data-theme', 'dark');
        } else {
            document.body.classList.remove('dark');
            document.documentElement.setAttribute('data-theme', 'light');
        }
    }
}
