import { getToken, clearToken } from './auth';
import type {
  FolderTreeNode, Folder, DmsDocument, Revision, Entity, Tag, DocType,
  KbSearchResponse, KbStatus, KbSyncResult, KbEvent, KbGraphEntity, KbGraphResponse,
  BidProject, BidRequirement, BidTeamMember, BidDocument, ChecklistResponse,
  DocumentSuggestion, AuditLog, AdminUser, ApiAgent, SearchResult, UploadQueueItem,
  ExpirySummary, ExpiringDocument, MigrationStatus, PaginatedResponse,
  SystemSettings, ProcessingStatus,
} from '../types/dms';

const BASE = '/api/v2';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options?.headers as Record<string, string> || {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const res = await fetch(url, { ...options, headers });

  if (res.status === 401) {
    clearToken();
    window.location.href = '/';
    throw new Error('Session expired. Please login again.');
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

function jsonBody(data: unknown): RequestInit {
  return {
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  };
}

// ============================================================
// Folders
// ============================================================

export async function getFolderTree(): Promise<FolderTreeNode[]> {
  const data = await request<{ tree: FolderTreeNode[] }>(`${BASE}/folders/tree`);
  return data.tree;
}

export async function createFolder(data: { name: string; parent_id?: number | null; description?: string }): Promise<Folder> {
  return request<Folder>(`${BASE}/folders/`, { method: 'POST', ...jsonBody(data) });
}

export async function updateFolder(id: number, data: { name?: string; description?: string }): Promise<Folder> {
  return request<Folder>(`${BASE}/folders/${id}`, { method: 'PATCH', ...jsonBody(data) });
}

export async function deleteFolder(id: number): Promise<{ success: boolean }> {
  return request(`${BASE}/folders/${id}`, { method: 'DELETE' });
}

export async function reorderFolders(parentId: number | null, order: number[]): Promise<{ success: boolean }> {
  return request(`${BASE}/folders/reorder`, { method: 'POST', ...jsonBody({ parent_id: parentId, order }) });
}

// ============================================================
// Documents
// ============================================================

export async function listDocuments(params?: {
  folder_id?: number;
  doc_type_id?: number;
  status?: string;
  entity_id?: number;
  tag_id?: number;
  q?: string;
  limit?: number;
  offset?: number;
}): Promise<PaginatedResponse<DmsDocument>> {
  const sp = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) sp.set(k, String(v));
    });
  }
  return request(`${BASE}/documents/?${sp.toString()}`);
}

export async function getDocument(id: number): Promise<DmsDocument> {
  return request(`${BASE}/documents/${id}`);
}

export async function createDocument(data: {
  title: string;
  folder_id?: number;
  doc_type_id?: number;
  description?: string;
  status?: string;
  expiry_date?: string;
}): Promise<DmsDocument> {
  return request(`${BASE}/documents/`, { method: 'POST', ...jsonBody(data) });
}

export async function updateDocument(id: number, data: Record<string, unknown>): Promise<DmsDocument> {
  return request(`${BASE}/documents/${id}`, { method: 'PATCH', ...jsonBody(data) });
}

export async function deleteDocument(id: number): Promise<{ success: boolean }> {
  return request(`${BASE}/documents/${id}`, { method: 'DELETE' });
}

export async function lockDocument(id: number): Promise<{ success: boolean }> {
  return request(`${BASE}/documents/${id}/lock`, { method: 'POST' });
}

export async function unlockDocument(id: number): Promise<{ success: boolean }> {
  return request(`${BASE}/documents/${id}/unlock`, { method: 'POST' });
}

export async function listRevisions(docId: number): Promise<{ revisions: Revision[] }> {
  return request(`${BASE}/documents/${docId}/revisions/`);
}

export async function linkEntity(docId: number, data: { entity_id: number; role: string }): Promise<unknown> {
  return request(`${BASE}/documents/${docId}/entities/`, { method: 'POST', ...jsonBody(data) });
}

export async function unlinkEntity(docId: number, entityId: number): Promise<{ success: boolean }> {
  return request(`${BASE}/documents/${docId}/entities/${entityId}`, { method: 'DELETE' });
}

export async function addTag(docId: number, data: { tag_id: number }): Promise<unknown> {
  return request(`${BASE}/documents/${docId}/tags/`, { method: 'POST', ...jsonBody(data) });
}

export async function removeTag(docId: number, tagId: number): Promise<{ success: boolean }> {
  return request(`${BASE}/documents/${docId}/tags/${tagId}`, { method: 'DELETE' });
}

// ============================================================
// Entities
// ============================================================

export async function listEntities(params?: {
  type?: string;
  parent_id?: number;
  q?: string;
}): Promise<{ results: Entity[]; total: number }> {
  const sp = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) sp.set(k, String(v));
    });
  }
  return request(`${BASE}/entities/?${sp.toString()}`);
}

export async function getEntity(id: number): Promise<Entity> {
  return request(`${BASE}/entities/${id}`);
}

export async function createEntity(data: { entity_type: string; name: string; parent_id?: number; attributes?: Record<string, unknown> }): Promise<Entity> {
  return request(`${BASE}/entities/`, { method: 'POST', ...jsonBody(data) });
}

// ============================================================
// Tags
// ============================================================

export async function listTags(): Promise<{ tags: Tag[]; total: number }> {
  return request(`${BASE}/tags/`);
}

export async function createTag(data: { name: string; color?: string }): Promise<Tag> {
  return request(`${BASE}/tags/`, { method: 'POST', ...jsonBody(data) });
}

// ============================================================
// Doc Types
// ============================================================

export async function listDocTypes(category?: string): Promise<{ doc_types: Record<string, DocType[]>; total: number }> {
  const sp = category ? `?category=${category}` : '';
  return request(`${BASE}/doc-types/${sp}`);
}

export async function createDocType(data: { name: string; code: string; category: string; description?: string; icon?: string }): Promise<DocType> {
  return request(`${BASE}/doc-types/`, { method: 'POST', ...jsonBody(data) });
}

export async function updateDocType(id: number, data: { name?: string; category?: string; description?: string; icon?: string }): Promise<DocType> {
  return request(`${BASE}/doc-types/${id}`, { method: 'PATCH', ...jsonBody(data) });
}

export async function deleteDocType(id: number): Promise<{ success: boolean }> {
  return request(`${BASE}/doc-types/${id}`, { method: 'DELETE' });
}

// ============================================================
// Search
// ============================================================

export async function searchDocuments(params: {
  q?: string;
  folder_id?: number;
  doc_type_id?: number;
  entity_id?: number;
  tag_id?: number;
  status?: string;
  sort?: string;
  limit?: number;
  offset?: number;
}): Promise<PaginatedResponse<SearchResult>> {
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null) sp.set(k, String(v));
  });
  return request(`${BASE}/search?${sp.toString()}`);
}

// ============================================================
// Knowledge Base (Phase 4)
// ============================================================

export async function kbSearch(params: {
  q: string;
  mode?: string;
  top_k?: number;
}): Promise<KbSearchResponse> {
  const sp = new URLSearchParams({ q: params.q });
  if (params.mode) sp.set('mode', params.mode);
  if (params.top_k) sp.set('top_k', String(params.top_k));
  return request(`${BASE}/kb/search?${sp.toString()}`);
}

export async function kbMultihopSearch(params: {
  q: string;
  top_k?: number;
  max_hops?: number;
  explain?: boolean;
}): Promise<KbSearchResponse> {
  const sp = new URLSearchParams({ q: params.q });
  if (params.top_k) sp.set('top_k', String(params.top_k));
  if (params.max_hops) sp.set('max_hops', String(params.max_hops));
  if (params.explain) sp.set('explain', 'true');
  return request(`${BASE}/kb/search/multihop?${sp.toString()}`);
}

export async function kbGetStatus(): Promise<KbStatus> {
  return request(`${BASE}/kb/status`);
}

export async function kbSync(): Promise<KbSyncResult> {
  return request(`${BASE}/kb/sync`, { method: 'POST' });
}

export async function kbReindex(): Promise<{ reindex: Record<string, unknown> }> {
  return request(`${BASE}/kb/reindex`, { method: 'POST' });
}

export async function kbGetEvents(docId: number): Promise<{ doc_id: number; events: KbEvent[]; total: number }> {
  return request(`${BASE}/kb/documents/${docId}/events`);
}

export async function kbSearchEntities(q: string, limit = 20): Promise<{ entities: KbGraphEntity[]; total: number }> {
  const sp = new URLSearchParams({ q, limit: String(limit) });
  return request(`${BASE}/kb/entities/search?${sp.toString()}`);
}

export async function kbGetEntityGraph(entityName: string, depth = 1): Promise<KbGraphResponse> {
  const sp = new URLSearchParams({ depth: String(depth) });
  return request(`${BASE}/kb/entities/${encodeURIComponent(entityName)}/graph?${sp.toString()}`);
}

export async function kbGetEventDetail(eventId: number): Promise<{ event: KbEvent }> {
  return request(`${BASE}/kb/events/${eventId}`);
}

export async function kbGetBatchRelations(names: string[]): Promise<{
  relations: Array<{ from_name: string; from_type: string; to_name: string; to_type: string; relation: string }>;
}> {
  const sp = new URLSearchParams({ names: names.join(',') });
  return request(`${BASE}/kb/entities/relations/batch?${sp.toString()}`);
}

// ============================================================
// Upload
// ============================================================

export interface DuplicateInfo {
  code: string;
  message: string;
  existing_document: {
    id: number;
    title: string;
    status: string;
    folder: string | null;
    doc_type: string | null;
    created_at: string | null;
  };
}

export async function uploadFile(file: File, data?: {
  title?: string;
  folder_id?: number;
  doc_type_id?: number;
  force?: boolean;
}): Promise<{ document_id: number; revision_id: number; status: string }> {
  const form = new FormData();
  form.append('file', file);
  if (data?.title) form.append('title', data.title);
  if (data?.folder_id) form.append('folder_id', String(data.folder_id));
  if (data?.doc_type_id) form.append('doc_type_id', String(data.doc_type_id));
  if (data?.force) form.append('force', 'true');

  const token = getToken();
  const headers: Record<string, string> = {};
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`${BASE}/upload/`, { method: 'POST', body: form, headers });

  if (res.status === 401) {
    clearToken();
    window.location.href = '/';
    throw new Error('Session expired. Please login again.');
  }

  if (res.status === 409) {
    const body = await res.json().catch(() => ({ detail: '' }));
    const detail = body.detail || '';
    try {
      const dupInfo: DuplicateInfo = typeof detail === 'string' ? JSON.parse(detail) : detail;
      if (dupInfo.code === 'DUPLICATE_FILE') {
        const err = new Error(dupInfo.message) as Error & { duplicateInfo: DuplicateInfo };
        err.duplicateInfo = dupInfo;
        throw err;
      }
    } catch (e) {
      if ((e as Error & { duplicateInfo?: unknown }).duplicateInfo) throw e;
    }
    throw new Error(detail || 'Conflict');
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

export async function getUploadQueue(params?: {
  limit?: number;
  offset?: number;
}): Promise<PaginatedResponse<UploadQueueItem>> {
  const sp = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) sp.set(k, String(v));
    });
  }
  return request(`${BASE}/upload/queue?${sp.toString()}`);
}

export async function approveUpload(docId: number, data: {
  title?: string;
  folder_id?: number;
  doc_type_id?: number;
  kb_index?: boolean;
}): Promise<DmsDocument> {
  return request(`${BASE}/upload/queue/${docId}/approve`, { method: 'POST', ...jsonBody(data) });
}

export async function getApproveSuggestions(docId: number): Promise<{
  doc_type: { id: number; name: string; code: string } | null;
  folder: { id: number; name: string; path: string } | null;
}> {
  return request(`${BASE}/upload/queue/${docId}/suggestions`);
}

export async function rejectUpload(docId: number, del?: boolean): Promise<{ status: string; document_id: number }> {
  const sp = del ? '?delete=true' : '';
  return request(`${BASE}/upload/queue/${docId}/reject${sp}`, { method: 'POST' });
}

// Processing pipeline
export async function getProcessingStatus(docId: number): Promise<ProcessingStatus> {
  return request(`${BASE}/upload/process/${docId}`);
}

export async function triggerOcr(docId: number, pageNumbers: number[], ocrProvider?: string): Promise<{ status: string; pages: number[] }> {
  const body: Record<string, unknown> = { page_numbers: pageNumbers };
  if (ocrProvider) body.ocr_provider = ocrProvider;
  return request(`${BASE}/upload/process/${docId}/ocr`, { method: 'POST', ...jsonBody(body) });
}

export async function triggerClassify(docId: number): Promise<{ status: string }> {
  return request(`${BASE}/upload/process/${docId}/classify`, { method: 'POST' });
}

export async function updateProcessingMetadata(docId: number, data: {
  title?: string;
  material_type?: string;
  doc_type_id?: number;
  folder_id?: number;
  extracted_data?: Record<string, unknown>;
  notes?: string;
}): Promise<{ success: boolean; document_id: number }> {
  return request(`${BASE}/upload/process/${docId}/metadata`, { method: 'PUT', ...jsonBody(data) });
}

export async function finalizeDocument(docId: number, data?: {
  title?: string;
  doc_type_id?: number;
  folder_id?: number;
  notes?: string;
}): Promise<{ status: string; document_id: number }> {
  return request(`${BASE}/upload/process/${docId}/finalize`, { method: 'POST', ...jsonBody(data || {}) });
}

// ============================================================
// Expiry
// ============================================================

export async function getExpirySummary(): Promise<ExpirySummary> {
  return request(`${BASE}/expiry/summary`);
}

export async function getExpiringDocuments(days?: number, limit?: number, offset?: number): Promise<PaginatedResponse<ExpiringDocument> & { days: number }> {
  const sp = new URLSearchParams();
  if (days !== undefined) sp.set('days', String(days));
  if (limit !== undefined) sp.set('limit', String(limit));
  if (offset !== undefined) sp.set('offset', String(offset));
  return request(`${BASE}/expiry/expiring?${sp.toString()}`);
}

export async function getExpiredDocuments(limit?: number, offset?: number): Promise<PaginatedResponse<ExpiringDocument>> {
  const sp = new URLSearchParams();
  if (limit !== undefined) sp.set('limit', String(limit));
  if (offset !== undefined) sp.set('offset', String(offset));
  return request(`${BASE}/expiry/expired?${sp.toString()}`);
}

// ============================================================
// Bids
// ============================================================

export async function listBids(params?: {
  status?: string;
  buyer?: string;
  q?: string;
  limit?: number;
  offset?: number;
}): Promise<PaginatedResponse<BidProject>> {
  const sp = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) sp.set(k, String(v));
    });
  }
  return request(`${BASE}/bids/?${sp.toString()}`);
}

export async function getBid(id: number): Promise<BidProject> {
  return request(`${BASE}/bids/${id}`);
}

export async function createBid(data: {
  name: string;
  bid_number?: string;
  buyer?: string;
  budget?: string;
  deadline?: string;
  description?: string;
}): Promise<BidProject> {
  return request(`${BASE}/bids/`, { method: 'POST', ...jsonBody(data) });
}

export async function updateBid(id: number, data: Record<string, unknown>): Promise<BidProject> {
  return request(`${BASE}/bids/${id}`, { method: 'PATCH', ...jsonBody(data) });
}

export async function updateBidStatus(id: number, data: { status: string; result?: string }): Promise<BidProject> {
  return request(`${BASE}/bids/${id}/status`, { method: 'PATCH', ...jsonBody(data) });
}

export async function deleteBid(id: number): Promise<{ success: boolean }> {
  return request(`${BASE}/bids/${id}`, { method: 'DELETE' });
}

// Bid team
export async function listTeamMembers(bidId: number): Promise<{ team_members: BidTeamMember[] }> {
  return request(`${BASE}/bids/${bidId}/team`);
}

export async function addTeamMember(bidId: number, data: { entity_id: number; role: string }): Promise<BidTeamMember> {
  return request(`${BASE}/bids/${bidId}/team`, { method: 'POST', ...jsonBody(data) });
}

export async function removeTeamMember(bidId: number, memberId: number): Promise<{ success: boolean }> {
  return request(`${BASE}/bids/${bidId}/team/${memberId}`, { method: 'DELETE' });
}

// Bid requirements
export async function listRequirements(bidId: number): Promise<{ requirements: BidRequirement[]; total: number }> {
  return request(`${BASE}/bids/${bidId}/requirements`);
}

export async function createRequirement(bidId: number, data: {
  title: string;
  doc_type_id?: number;
  description?: string;
  is_required?: boolean;
  sort_order?: number;
}): Promise<BidRequirement> {
  return request(`${BASE}/bids/${bidId}/requirements`, { method: 'POST', ...jsonBody(data) });
}

export async function updateRequirement(bidId: number, reqId: number, data: Record<string, unknown>): Promise<BidRequirement> {
  return request(`${BASE}/bids/${bidId}/requirements/${reqId}`, { method: 'PATCH', ...jsonBody(data) });
}

export async function deleteRequirement(bidId: number, reqId: number): Promise<{ success: boolean }> {
  return request(`${BASE}/bids/${bidId}/requirements/${reqId}`, { method: 'DELETE' });
}

export async function createRequirementsFromCategory(bidId: number, category: string): Promise<{ created: BidRequirement[]; skipped: number; total: number }> {
  return request(`${BASE}/bids/${bidId}/requirements/from-category`, { method: 'POST', ...jsonBody({ category }) });
}

// Bid document linking
export async function linkBidDocument(bidId: number, reqId: number, data: { document_id: number; notes?: string }): Promise<BidDocument> {
  return request(`${BASE}/bids/${bidId}/requirements/${reqId}/documents`, { method: 'POST', ...jsonBody(data) });
}

export async function unlinkBidDocument(bidId: number, reqId: number, docId: number): Promise<{ success: boolean }> {
  return request(`${BASE}/bids/${bidId}/requirements/${reqId}/documents/${docId}`, { method: 'DELETE' });
}

export async function getSuggestions(bidId: number, reqId: number): Promise<{ suggestions: DocumentSuggestion[] }> {
  return request(`${BASE}/bids/${bidId}/requirements/${reqId}/suggestions`);
}

export async function getChecklist(bidId: number): Promise<ChecklistResponse> {
  return request(`${BASE}/bids/${bidId}/checklist`);
}

// ============================================================
// Admin
// ============================================================

export async function listUsers(): Promise<{ users: AdminUser[] }> {
  return request(`${BASE}/admin/users`);
}

export async function createUser(data: { username: string; password: string; role?: string }): Promise<AdminUser> {
  return request(`${BASE}/admin/users`, { method: 'POST', ...jsonBody(data) });
}

export async function updateUserRole(userId: number, role: string): Promise<AdminUser> {
  return request(`${BASE}/admin/users/${userId}/role`, { method: 'PUT', ...jsonBody({ role }) });
}

export async function resetUserPassword(userId: number, password: string): Promise<{ success: boolean }> {
  return request(`${BASE}/admin/users/${userId}/password`, { method: 'PUT', ...jsonBody({ new_password: password }) });
}

export async function getUserFolders(userId: number): Promise<{ folder_ids: number[] }> {
  return request(`${BASE}/admin/users/${userId}/folders`);
}

export async function setUserFolders(userId: number, folderIds: number[]): Promise<{ success: boolean; folder_ids: number[] }> {
  return request(`${BASE}/admin/users/${userId}/folders`, { method: 'PUT', ...jsonBody({ folder_ids: folderIds }) });
}

// ============================================================
// API Agents
// ============================================================

export async function listAgents(): Promise<{ agents: ApiAgent[] }> {
  return request(`${BASE}/admin/agents/`);
}

export async function createAgent(data: { name: string; role?: string; description?: string; folder_ids?: number[] }): Promise<ApiAgent> {
  return request(`${BASE}/admin/agents/`, { method: 'POST', ...jsonBody(data) });
}

export async function updateAgent(agentId: number, data: { name?: string; role?: string; description?: string; is_active?: boolean }): Promise<ApiAgent> {
  return request(`${BASE}/admin/agents/${agentId}`, { method: 'PUT', ...jsonBody(data) });
}

export async function deleteAgent(agentId: number): Promise<{ success: boolean }> {
  return request(`${BASE}/admin/agents/${agentId}`, { method: 'DELETE' });
}

export async function regenerateAgentToken(agentId: number): Promise<{ token: string }> {
  return request(`${BASE}/admin/agents/${agentId}/regenerate-token`, { method: 'POST' });
}

export async function setAgentFolders(agentId: number, folderIds: number[]): Promise<{ success: boolean; folder_ids: number[] }> {
  return request(`${BASE}/admin/agents/${agentId}/folders`, { method: 'PUT', ...jsonBody({ folder_ids: folderIds }) });
}

// ============================================================
// Audit
// ============================================================

export async function listAuditLogs(params?: {
  user_id?: number;
  action?: string;
  target_type?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
}): Promise<PaginatedResponse<AuditLog>> {
  const sp = new URLSearchParams();
  if (params) {
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null) sp.set(k, String(v));
    });
  }
  return request(`${BASE}/audit/logs?${sp.toString()}`);
}

// ============================================================
// Migration
// ============================================================

export async function getMigrationStatus(): Promise<MigrationStatus> {
  return request(`${BASE}/admin/migrate/status`);
}

export async function migrateCompanies(): Promise<{ created: number; skipped: number; total: number }> {
  return request(`${BASE}/admin/migrate/companies`, { method: 'POST' });
}

export async function migratePersons(): Promise<{ created: number; skipped: number; total: number }> {
  return request(`${BASE}/admin/migrate/persons`, { method: 'POST' });
}

export async function migrateMaterials(): Promise<{ created: number; skipped: number; total: number; warnings?: string[] }> {
  return request(`${BASE}/admin/migrate/materials`, { method: 'POST' });
}

// ============================================================
// Settings
// ============================================================

export async function getSettings(): Promise<{ settings: SystemSettings }> {
  return request(`${BASE}/settings/`);
}

export async function updateSetting(key: string, value: string): Promise<{ key: string; value: string; success: boolean }> {
  return request(`${BASE}/settings/${key}`, { method: 'PUT', ...jsonBody({ value }) });
}

export async function batchUpdateSettings(settings: Record<string, string>): Promise<{ updated: string[]; success: boolean }> {
  return request(`${BASE}/settings/batch`, { method: 'PUT', ...jsonBody({ settings }) });
}

export async function testOcr(): Promise<{ provider: string; available: boolean; message: string }> {
  return request(`${BASE}/settings/ocr/test`, { method: 'POST' });
}

export async function testLlm(): Promise<{ provider: string; available: boolean; message: string; response?: string }> {
  return request(`${BASE}/settings/llm/test`, { method: 'POST' });
}

// ============================================================
// Reprocess (OCR + LLM re-extraction)
// ============================================================

export interface ReprocessCheckItem {
  id: number;
  title: string;
  doc_type: string | null;
  has_metadata: boolean;
  metadata_fields: string[];
  has_file: boolean;
  summary: string;
}

export async function reprocessCheck(docIds: number[]): Promise<{ documents: ReprocessCheckItem[] }> {
  return request(`${BASE}/documents/actions/reprocess-check`, {
    method: 'POST',
    ...jsonBody({ doc_ids: docIds }),
  });
}

export async function reprocessDocuments(docIds: number[], force: boolean): Promise<{
  queued: number;
  skipped: number;
  queued_ids: number[];
  skipped_details: { id: number; reason: string }[];
}> {
  return request(`${BASE}/documents/actions/reprocess`, {
    method: 'POST',
    ...jsonBody({ doc_ids: docIds, force }),
  });
}

// ============================================================
// Chat
// ============================================================

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
}

export async function chatWithLLM(
  messages: ChatMessage[],
  folderId: number | null,
): Promise<{ reply?: string; error?: string }> {
  return request(`${BASE}/chat`, {
    method: 'POST',
    ...jsonBody({ messages, folder_id: folderId }),
  });
}

export interface ChatSession {
  id: number; title: string; message_count: number;
  created_at: string; updated_at: string;
}

export async function listChatSessions(): Promise<{ sessions: ChatSession[] }> {
  return request(`${BASE}/chat/history`);
}

export async function loadChatHistory(sessionId?: number): Promise<{ messages: ChatMessage[]; session_id?: number; title?: string }> {
  if (sessionId) {
    return request(`${BASE}/chat/history/${sessionId}`);
  }
  // Auto-load latest session
  const data = await request<{ sessions: ChatSession[] }>(`${BASE}/chat/history`);
  if (data.sessions && data.sessions.length > 0) {
    return request(`${BASE}/chat/history/${data.sessions[0].id}`);
  }
  return { messages: [] };
}

export async function newChatSession(): Promise<{ session_id: number }> {
  return request(`${BASE}/chat/history/new`, { method: 'POST' });
}

export async function saveChatHistory(messages: ChatMessage[], sessionId?: number): Promise<{ ok: boolean; session_id?: number }> {
  return request(`${BASE}/chat/history`, {
    method: 'PUT',
    ...jsonBody({ messages, session_id: sessionId }),
  });
}

export async function deleteChatSession(sessionId: number): Promise<void> {
  await request(`${BASE}/chat/history/${sessionId}`, { method: 'DELETE' });
}

export interface ToolUseEvent {
  tool: string;
  label: string;
  args: Record<string, unknown>;
}

export async function chatStreamWithLLM(
  messages: ChatMessage[],
  folderId: number | null,
  onChunk: (text: string) => void,
  onDone: () => void,
  onError: (err: string) => void,
  onToolsUsed?: (tools: ToolUseEvent[]) => void,
): Promise<void> {
  const token = getToken();
  const res = await fetch(`${BASE}/chat/stream`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ messages, folder_id: folderId }),
  });

  if (!res.ok || !res.body) {
    onError(`HTTP ${res.status}`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop() || '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const data = line.slice(6).trim();
      if (data === '[DONE]') {
        onDone();
        return;
      }
      try {
        const parsed = JSON.parse(data);
        if (parsed.error) {
          onError(parsed.error);
          return;
        }
        if (parsed.tools_used && onToolsUsed) {
          onToolsUsed(parsed.tools_used);
        }
        if (parsed.content) {
          onChunk(parsed.content);
        }
      } catch {
        // skip malformed
      }
    }
  }
  onDone();
}

// ============================================================
// Auth (v2)
// ============================================================

export interface V2LoginResponse {
  token: string;
  user: { id: number; username: string; role: string };
  expires_at: string;
}

export async function loginV2(username: string, password: string): Promise<V2LoginResponse> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || 'Login failed');
  }

  return res.json();
}

export async function logoutV2(): Promise<void> {
  await request(`${BASE}/auth/logout`, { method: 'POST' });
}

export async function checkAuthV2(): Promise<boolean> {
  try {
    const result = await request<{ valid: boolean }>(`${BASE}/auth/check`);
    return result.valid;
  } catch {
    return false;
  }
}

// ============================================================
// Upload & Processing (v2 pipeline)
// ============================================================

export interface V2UploadResult {
  document_id: number;
  revision_id: number;
  status: string;
}

export interface V2BatchUploadResult {
  total: number;
  succeeded: number;
  failed: number;
  results: Array<{
    filename: string;
    success: boolean;
    document_id?: number;
    status?: string;
    error?: string;
  }>;
}

export interface V2ProcessingStatus {
  document_id: number;
  title: string;
  status: string;
  processing_status: string | null;
  processing_error: string | null;
  total_pages: number;
  file_type: string | null;
  pages: Array<{
    page_num: number;
    has_text: boolean;
    text_length: number;
    needs_ocr: boolean;
    ocr_text: string | null;
    thumbnail_url: string | null;
  }>;
  text_pages: number[];
  ocr_pages: number[];
  suggested_ocr_pages: number[];
  material_type: string | null;
  confidence: number | null;
  extracted_data: Record<string, unknown> | null;
  summary: string | null;
  ocr_text: string | null;
  suggested_doc_type: { id: number; name: string; code: string } | null;
  suggested_folder: { id: number; name: string; path: string } | null;
  doc_type: { id: number; name: string; code: string } | null;
  folder: { id: number; name: string; path: string } | null;
}

export async function uploadFileV2(
  file: File,
  opts?: { title?: string; folder_id?: number; doc_type_id?: number; notes?: string; force?: boolean }
): Promise<V2UploadResult> {
  const form = new FormData();
  form.append('file', file);
  if (opts?.title) form.append('title', opts.title);
  if (opts?.folder_id) form.append('folder_id', String(opts.folder_id));
  if (opts?.doc_type_id) form.append('doc_type_id', String(opts.doc_type_id));
  if (opts?.notes) form.append('notes', opts.notes);
  if (opts?.force) form.append('force', 'true');

  const res = await fetch(`${BASE}/upload/`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${getToken()}` },
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `Upload failed: ${res.status}`);
  }
  return res.json();
}

export async function uploadBatchV2(
  files: File[],
  opts?: { folder_id?: number; doc_type_id?: number }
): Promise<V2BatchUploadResult> {
  const form = new FormData();
  files.forEach(f => form.append('files', f));
  if (opts?.folder_id) form.append('folder_id', String(opts.folder_id));
  if (opts?.doc_type_id) form.append('doc_type_id', String(opts.doc_type_id));

  const res = await fetch(`${BASE}/upload/batch`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${getToken()}` },
    body: form,
  });
  if (!res.ok) throw new Error(`Batch upload failed: ${res.status}`);
  return res.json();
}

export async function rotatePdfV2(docId: number, direction: 'left' | 'right') {
  return request(`${BASE}/upload/process/${docId}/rotate`, {
    method: 'POST',
    ...jsonBody({ direction }),
  });
}

export function getPageThumbnailUrlV2(docId: number, pageNum: number, rotation?: number): string {
  const token = getToken();
  const rotParam = rotation ? `&rotation=${rotation}` : '';
  return `${BASE}/upload/process/${docId}/page/${pageNum}/thumb?token=${token}${rotParam}`;
}

// V2QueueItem is in types/dms.ts as UploadQueueItem

export async function batchQueueAction(action: 'approve' | 'reject', documentIds: number[]) {
  return request(`${BASE}/upload/queue/batch`, {
    method: 'POST',
    ...jsonBody({ action, document_ids: documentIds }),
  });
}

export async function confirmMerge(docId: number, action: 'confirm' | 'reject') {
  return request(`${BASE}/upload/process/${docId}/merge-confirm`, {
    method: 'POST',
    ...jsonBody({ action }),
  });
}

// ============================================================
// Roles & Permissions
// ============================================================

export interface DmsRoleInfo {
  id: number; name: string; description: string | null;
  is_system: boolean; folder_count: number; user_count: number;
}

export interface FolderPermission {
  id: number; role_id: number; folder_id: number;
  folder_name: string; folder_path: string; permission: string;
}

export interface UserRoleAssignment {
  id: number; user_id: number; username: string;
  role_id: number; role_name: string;
}

export async function listRoles(): Promise<{ roles: DmsRoleInfo[] }> {
  return request(`${BASE}/admin/roles/`);
}

export async function createRole(data: { name: string; description?: string }): Promise<DmsRoleInfo> {
  return request(`${BASE}/admin/roles/`, { method: 'POST', ...jsonBody(data) });
}

export async function updateRole(id: number, data: { name?: string; description?: string }): Promise<DmsRoleInfo> {
  return request(`${BASE}/admin/roles/${id}`, { method: 'PATCH', ...jsonBody(data) });
}

export async function deleteRole(id: number): Promise<{ success: boolean }> {
  return request(`${BASE}/admin/roles/${id}`, { method: 'DELETE' });
}

export async function getRoleFolderPermissions(roleId: number): Promise<{ folder_permissions: FolderPermission[] }> {
  return request(`${BASE}/admin/roles/${roleId}/folders`);
}

export async function setRoleFolderPermissions(roleId: number, folderIds: number[], permission: string) {
  return request(`${BASE}/admin/roles/${roleId}/folders`, {
    method: 'PUT', ...jsonBody({ folder_ids: folderIds, permission }),
  });
}

export async function setSingleFolderPermission(roleId: number, folderId: number, permission: string) {
  return request(`${BASE}/admin/roles/${roleId}/folders/${folderId}?permission=${permission}`, {
    method: 'PUT',
  });
}

export async function getUserRoles(userId: number): Promise<{ roles: UserRoleAssignment[] }> {
  return request(`${BASE}/admin/roles/users/${userId}`);
}

export async function assignUserRole(userId: number, roleId: number) {
  return request(`${BASE}/admin/roles/users/assign`, {
    method: 'POST', ...jsonBody({ user_id: userId, role_id: roleId }),
  });
}

export async function removeUserRole(userId: number, roleId: number) {
  return request(`${BASE}/admin/roles/users/${userId}/roles/${roleId}`, { method: 'DELETE' });
}

export async function syncRoleAgents(): Promise<{ synced: number }> {
  return request(`${BASE}/admin/roles/sync-agents`, { method: 'POST' });
}

export async function getMyPermissions(): Promise<{ is_admin: boolean; folders: Array<{ folder_id: number; permission: string }> }> {
  return request(`${BASE}/admin/roles/me/effective`);
}
