import { ApplicationConfig } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideAnimations } from '@angular/platform-browser/animations';
import { provideHttpClient } from '@angular/common/http';
import { provideToastr } from 'ngx-toastr';

import { routes } from './app.routes';

export const appConfig: ApplicationConfig = {
    providers: [
        provideRouter(routes),
        provideAnimations(),
        provideHttpClient(),
        provideToastr({
            positionClass: 'toast-top-right',
            timeOut: 3000,
            closeButton: true,
            preventDuplicates: true,
        }),
    ]
};
