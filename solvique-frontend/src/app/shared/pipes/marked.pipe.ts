import { Pipe, PipeTransform } from '@angular/core';
import { marked } from 'marked';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

@Pipe({
    name: 'marked',
    standalone: true
})
export class MarkedPipe implements PipeTransform {
    constructor(private sanitizer: DomSanitizer) {
        marked.setOptions({
            gfm: true,
            breaks: true,
        });
    }

    transform(value: string | null | undefined): SafeHtml {
        if (!value) return '';
        const html = marked.parse(value) as string;
        return this.sanitizer.bypassSecurityTrustHtml(html);
    }
}
