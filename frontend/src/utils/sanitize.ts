import DOMPurify from 'dompurify';

/** Sanitize HTML from untrusted sources (OCR text, LLM-extracted entities) before rendering. */
export function sanitizeHtml(html: string): string {
  return DOMPurify.sanitize(html, { ALLOWED_TAGS: ['b', 'br'], ALLOWED_ATTR: [] });
}
