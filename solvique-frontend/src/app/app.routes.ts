import { Routes } from '@angular/router';

export const routes: Routes = [
    {
        path: '',
        loadComponent: () =>
            import('./features/chat/components/shell/shell.component').then(m => m.ShellComponent)
    },
    {
        path: '**',
        redirectTo: '',
        pathMatch: 'full'
    }
];
