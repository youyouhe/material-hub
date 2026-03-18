// DMS v2 API TypeScript types

export interface Folder {
  id: number;
  name: string;
  parent_id: number | null;
  path: string;
  description: string | null;
  sort_order: number;
  created_at: string | null;
  updated_at: string | null;
  children?: FolderTreeNode[];
}

export interface FolderTreeNode extends Folder {
  children: FolderTreeNode[];
  doc_count?: number;
}

export interface DocType {
  id: number;
  name: string;
  code: string;
  category: string; // company | personnel | project | bid | general
  metadata_schema: Record<string, unknown> | null;
  icon: string | null;
  description: string | null;
  is_system: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface DmsFile {
  id: number;
  revision_id: number;
  file_type: string; // original | thumbnail | extracted_page | ocr_result
  filename: string;
  storage_path: string;
  mime_type: string | null;
  file_size: number;
  file_hash: string | null;
  page_number: number | null;
  url: string;
  created_at: string | null;
}

export interface Revision {
  id: number;
  document_id: number;
  version_number: number;
  is_current: boolean;
  change_note: string | null;
  created_by: number | null;
  created_at: string | null;
  files: DmsFile[];
}

export interface DocumentEntity {
  id: number;
  document_id: number;
  entity_id: number;
  entity_name: string | null;
  entity_type: string; // org | person
  role: string; // owner | issuer | subject | related
  created_at: string | null;
}

export interface DocumentTag {
  tag_id: number;
  tag_name: string | null;
  tag_color: string | null;
}

export interface DocumentLock {
  locked_by: number | null;
  locked_at: string | null;
  is_locked: boolean;
}

export interface DmsDocument {
  id: number;
  folder_id: number | null;
  doc_type_id: number | null;
  title: string;
  description: string | null;
  status: string; // draft | active | expired | archived | superseded
  metadata: Record<string, unknown> | null;
  expiry_date: string | null;
  created_by: number | null;
  created_at: string | null;
  updated_at: string | null;
  current_revision?: Revision | null;
  folder?: { id: number; name: string; path: string } | null;
  doc_type?: { id: number; name: string; code: string } | null;
  entities?: DocumentEntity[];
  tags?: DocumentTag[];
  lock?: DocumentLock;
}

export interface Entity {
  id: number;
  entity_type: string; // org | person
  name: string;
  attributes: Record<string, unknown> | null;
  parent_id: number | null;
  created_at: string | null;
  updated_at: string | null;
  document_count?: number;
  children?: { id: number; name: string; entity_type: string }[];
}

export interface Tag {
  id: number;
  name: string;
  color: string | null;
  created_at: string | null;
  document_count?: number;
}

export interface AuditLog {
  id: number;
  user_id: number | null;
  action: string;
  target_type: string;
  target_id: number | null;
  target_title: string | null;
  details: Record<string, unknown> | null;
  ip_address: string | null;
  created_at: string | null;
}

export interface AdminUser {
  id: number;
  username: string;
  role: string; // admin | editor | viewer
  created_at?: string | null;
  last_login?: string | null;
  folder_ids?: number[];
}

// API Agent types
export interface ApiAgent {
  id: number;
  name: string;
  token?: string;         // Full token only on creation
  token_preview?: string; // Masked token for display
  role: string;
  is_active: boolean;
  description: string | null;
  folder_ids: number[];
  created_at: string | null;
  updated_at: string | null;
  last_used_at: string | null;
}

// Bid types
export interface BidProject {
  id: number;
  name: string;
  bid_number: string | null;
  buyer: string | null;
  folder_id: number | null;
  status: string; // planning | active | submitted | won | lost | cancelled
  budget: string | null;
  deadline: string | null;
  description: string | null;
  result: string | null;
  created_by: number | null;
  created_at: string | null;
  updated_at: string | null;
  team_members?: BidTeamMember[];
  requirements_summary?: RequirementsSummary;
}

export interface RequirementsSummary {
  total: number;
  fulfilled: number;
  missing: number;
}

export interface BidRequirement {
  id: number;
  bid_project_id: number;
  doc_type_id: number | null;
  title: string;
  description: string | null;
  is_required: boolean;
  sort_order: number;
  created_at: string | null;
  updated_at: string | null;
  linked_documents?: BidDocument[];
  fulfilled?: boolean;
}

export interface BidTeamMember {
  id: number;
  bid_project_id: number;
  entity_id: number;
  entity_name?: string;
  entity_type?: string;
  role: string;
  created_at: string | null;
}

export interface BidDocument {
  id: number;
  bid_requirement_id: number;
  document_id: number;
  document_title?: string | null;
  status: string; // linked | verified
  linked_by: number | null;
  linked_at: string | null;
  notes: string | null;
  document_exists?: boolean;
  document_status?: string;
}

export interface ChecklistItem {
  id: number;
  title: string;
  is_required: boolean;
  doc_type: { id: number; name: string } | null;
  linked_documents: {
    document_id: number;
    document_title: string | null;
    link_status: string;
    document_exists: boolean;
  }[];
  status: string; // fulfilled | missing
}

export interface ChecklistResponse {
  bid_project_id: number;
  total: number;
  fulfilled: number;
  missing: number;
  percentage: number;
  items: ChecklistItem[];
}

export interface DocumentSuggestion {
  id: number;
  title: string;
  status: string;
  doc_type: { id: number; name: string; code: string } | null;
  expiry_date: string | null;
  updated_at: string | null;
}

// Expiry types
export interface ExpirySummary {
  expiring_30d: number;
  expiring_60d: number;
  expiring_90d: number;
  expired: number;
  by_doc_type: {
    doc_type_id: number;
    doc_type_name: string;
    doc_type_code: string;
    total_with_expiry: number;
    expired: number;
    expiring_30d: number;
  }[];
}

export interface ExpiringDocument {
  id: number;
  title: string;
  status: string;
  doc_type: { id: number; name: string; code: string } | null;
  folder: { id: number; name: string; path: string } | null;
  expiry_date: string | null;
  days_until_expiry: number | null;
  entity_names: string[];
}

// Search result type
export interface SearchResult {
  id: number;
  title: string;
  status: string;
  doc_type: { id: number; name: string; code: string } | null;
  folder: { id: number; name: string; path: string } | null;
  entity_names: string[];
  expiry_date: string | null;
  thumbnail_url: string | null;
  snippet: string | null;
  created_at: string | null;
  updated_at: string | null;
}

// Upload queue types
export interface UploadQueueItem {
  id: number;
  title: string;
  status: string;
  doc_type: { id: number; name: string; code: string } | null;
  folder: { id: number; name: string; path: string } | null;
  processing_status: string;
  processing_error: string | null;
  thumbnail_url: string | null;
  created_at: string | null;
}

// Processing flow types
export interface PageInfo {
  page_num: number;
  has_text: boolean;
  text_length: number;
  needs_ocr: boolean;
  ocr_text?: string | null;
  thumbnail_url: string | null;
}

export interface ProcessingStatus {
  document_id: number;
  title: string;
  status: string;
  processing_status: string | null;
  processing_error: string | null;
  total_pages: number;
  file_type: string | null;
  pages: PageInfo[];
  text_pages: number[];
  ocr_pages: number[];
  suggested_ocr_pages: number[];
  ocr_text: string | null;
  material_type: string | null;
  confidence: number | null;
  extracted_data: Record<string, unknown> | null;
  summary: string | null;
  suggested_doc_type: { id: number; name: string; code: string } | null;
  suggested_folder: { id: number; name: string; path: string } | null;
  doc_type: { id: number; name: string; code: string } | null;
  folder: { id: number; name: string; path: string } | null;
}

// Migration types
export interface MigrationStatus {
  companies: { legacy: number; migrated: number };
  persons: { legacy: number; migrated: number };
  materials: { legacy: number; migrated: number };
}

// System settings
export interface SystemSettingInfo {
  value: string;
  description: string;
  default: string;
  sensitive: boolean;
}

export type SystemSettings = Record<string, SystemSettingInfo>;

// Paginated response wrapper
export interface PaginatedResponse<T> {
  results: T[];
  total: number;
  limit: number;
  offset: number;
}
