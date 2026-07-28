/**
 * Status badge color palettes — driven by CSS classes defined in index.css.
 *
 * Uses custom .badge-* classes (not Tailwind palette utilities) because the
 * project's build only reliably generates cp-* variable-backed classes.
 * Each .badge-* class has light/dark variants via [data-theme] in index.css.
 *
 * Usage: <span className={clsx('badge px-2 py-0.5 text-xs rounded-full', docStatusBadge[doc.status])} />
 */

/** Base badge class — applies shared layout; pair with a color class below. */

/** Document lifecycle status. */
export const docStatusBadge: Record<string, string> = {
  active:     'badge-active',
  draft:      'badge-draft',
  archived:   'badge-archived',
  expired:    'badge-expired',
  superseded: 'badge-superseded',
};

/** Bid project status. */
export const bidStatusBadge: Record<string, string> = {
  planning:   'badge-archived',
  active:     'badge-purple',
  submitted:  'badge-draft',
  won:        'badge-active',
  lost:       'badge-expired',
  cancelled:  'badge-muted',
};

/** User/agent role badge. */
export const roleBadge: Record<string, string> = {
  admin:  'badge-expired',
  editor: 'badge-purple',
  viewer: 'badge-archived',
};

/** DocType category badge. */
export const categoryBadge: Record<string, string> = {
  company:   'badge-blue',
  personnel: 'badge-active',
  project:   'badge-draft',
  bid:       'badge-purple',
  general:   'badge-archived',
};

/** Processing pipeline status. */
export const processingBadge: Record<string, string> = {
  pending:        'badge-archived',
  analyzing:      'badge-blue',
  ocr_running:    'badge-blue',
  asr_running:    'badge-blue',
  word_extracted: 'badge-blue',
  deconstructing: 'badge-purple',
  deconstructed:  'badge-purple',
  classified:     'badge-draft',
  processing:     'badge-blue',
  completed:      'badge-active',
  analysis_done:  'badge-blue',
  failed:         'badge-expired',
};

/** Generic fallback for unknown status. */
export const fallbackBadge = 'badge-archived';
