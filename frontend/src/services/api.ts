import type { DocumentInfo, MaterialInfo, ExtractionResult, ExpiryStatus, CompanyInfo, PersonInfo, LoginResponse } from '../types';
import { getToken, clearToken } from './auth';

const BASE = '/api';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  // Add Authorization header if token exists
  const token = getToken();
  const headers = {
    ...options?.headers,
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };

  const res = await fetch(url, { ...options, headers });

  // Handle 401 Unauthorized - clear token and redirect to login
  if (res.status === 401) {
    clearToken();
    // Only redirect if not already on login/auth pages
    if (!window.location.pathname.includes('/auth')) {
      window.location.href = '/';
    }
    throw new Error('Session expired. Please login again.');
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

// --- Documents ---

export async function uploadDocument(file: File, companyId?: number): Promise<ExtractionResult> {
  const form = new FormData();
  form.append('file', file);
  if (companyId) {
    form.append('company_id', String(companyId));
  }
  return request<ExtractionResult>(`${BASE}/documents`, {
    method: 'POST',
    body: form,
  });
}

export async function listDocuments(): Promise<DocumentInfo[]> {
  const data = await request<{ documents: DocumentInfo[] }>(`${BASE}/documents`);
  return data.documents;
}

export async function deleteDocument(id: number): Promise<void> {
  await request(`${BASE}/documents/${id}`, { method: 'DELETE' });
}

// --- Materials ---

export async function uploadSingleImage(
  file: File,
  title?: string,
  section?: string,
  companyId?: number
): Promise<MaterialInfo> {
  const form = new FormData();
  form.append('image', file);
  if (title) form.append('title', title);
  if (section) form.append('section', section);
  if (companyId) form.append('company_id', String(companyId));

  return request<MaterialInfo>(`${BASE}/materials/upload`, {
    method: 'POST',
    body: form,
  });
}

export async function searchMaterials(params: {
  q?: string;
  document_id?: number;
  status?: ExpiryStatus;
  linked_status?: 'all' | 'company' | 'person' | 'unlinked';
  source_type?: 'all' | 'docx' | 'manual';
  company_id?: number;
}): Promise<MaterialInfo[]> {
  const sp = new URLSearchParams();
  if (params.q) sp.set('q', params.q);
  if (params.document_id) sp.set('document_id', String(params.document_id));
  if (params.status) sp.set('status', params.status);
  if (params.linked_status) sp.set('linked_status', params.linked_status);
  if (params.source_type) sp.set('source_type', params.source_type);
  if (params.company_id) sp.set('company_id', String(params.company_id));
  const data = await request<{ results: MaterialInfo[] }>(
    `${BASE}/materials?${sp.toString()}`
  );
  return data.results;
}

export async function updateMaterial(
  id: number,
  update: {
    title?: string;
    section?: string;
    expiry_date?: string;
    company_id?: number | null;
    person_id?: number | null;
  }
): Promise<MaterialInfo> {
  return request<MaterialInfo>(`${BASE}/materials/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(update),
  });
}

export async function deleteMaterial(id: number): Promise<void> {
  await request(`${BASE}/materials/${id}`, { method: 'DELETE' });
}

// Material linking helpers
export async function linkMaterialToCompany(
  materialId: number,
  companyId: number
): Promise<MaterialInfo> {
  return updateMaterial(materialId, { company_id: companyId });
}

export async function unlinkMaterialFromCompany(
  materialId: number
): Promise<MaterialInfo> {
  return updateMaterial(materialId, { company_id: null });
}

export async function linkMaterialToPerson(
  materialId: number,
  personId: number
): Promise<MaterialInfo> {
  return updateMaterial(materialId, { person_id: personId });
}

export async function unlinkMaterialFromPerson(
  materialId: number
): Promise<MaterialInfo> {
  return updateMaterial(materialId, { person_id: null });
}

// --- Companies ---

export async function listCompanies(): Promise<CompanyInfo[]> {
  const data = await request<{ companies: CompanyInfo[] }>(`${BASE}/companies`);
  return data.companies;
}

export async function getCompany(id: number): Promise<CompanyInfo> {
  return request<CompanyInfo>(`${BASE}/companies/${id}`);
}

export async function getCompanyMaterials(id: number): Promise<{ company: CompanyInfo; materials: MaterialInfo[] }> {
  return request(`${BASE}/companies/${id}/materials`);
}

// --- Persons ---

export async function listPersons(companyId?: number): Promise<PersonInfo[]> {
  const sp = new URLSearchParams();
  if (companyId) sp.set('company_id', String(companyId));
  const data = await request<{ persons: PersonInfo[] }>(`${BASE}/persons?${sp.toString()}`);
  return data.persons;
}

export async function getPerson(id: number): Promise<PersonInfo> {
  return request<PersonInfo>(`${BASE}/persons/${id}`);
}

export async function getPersonMaterials(id: number): Promise<{ person: PersonInfo; materials: MaterialInfo[] }> {
  return request(`${BASE}/persons/${id}/materials`);
}

export async function updatePerson(
  id: number,
  update: {
    name?: string;
    id_number?: string;
    education?: string;
    position?: string;
    company_id?: number | null;
  }
): Promise<PersonInfo> {
  return request<PersonInfo>(`${BASE}/persons/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(update),
  });
}

// --- OCR ---

export async function triggerOCR(materialId: number): Promise<{ status: string; message: string; material_id: number }> {
  return request<{ status: string; message: string; material_id: number }>(`${BASE}/materials/${materialId}/ocr`, {
    method: 'POST',
  });
}

export async function getOCRResult(materialId: number): Promise<import('../types').OCRResult> {
  return request<import('../types').OCRResult>(`${BASE}/materials/${materialId}/ocr`);
}

// --- Authentication ---

export async function login(username: string, password: string): Promise<LoginResponse> {
  // Don't use request() helper to avoid adding Authorization header
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

export async function logout(): Promise<void> {
  await request(`${BASE}/auth/logout`, { method: 'POST' });
}

export async function checkAuth(): Promise<boolean> {
  try {
    const result = await request<{ valid: boolean }>(`${BASE}/auth/check`);
    return result.valid;
  } catch {
    return false;
  }
}

// --- Smart Import ---

export async function smartImportBatch(files: File[]): Promise<{
  total: number;
  auto_archived: number;
  pending_review: number;
  failed: number;
  items: any[];
}> {
  const formData = new FormData();
  files.forEach(file => {
    formData.append('files', file);
  });

  return request(`${BASE}/smart-import/batch`, {
    method: 'POST',
    body: formData,
  });
}

export async function getPendingReviews(status: string = 'pending', limit: number = 50): Promise<{
  total: number;
  items: any[];
}> {
  return request(`${BASE}/smart-import/pending-reviews?status=${status}&limit=${limit}`);
}

export async function getPendingReview(id: number): Promise<any> {
  return request(`${BASE}/smart-import/pending-reviews/${id}`);
}

export function getPendingReviewPreviewUrl(id: number): string {
  const token = getToken();
  return `${BASE}/smart-import/pending-reviews/${id}/preview?token=${token}`;
}

export async function approvePendingReview(id: number, corrections?: any): Promise<{
  status: string;
  message: string;
  material_id?: number;
}> {
  return request(`${BASE}/smart-import/pending-reviews/${id}/approve`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(corrections || {}),
  });
}

export async function rejectPendingReview(id: number, reason: string = ''): Promise<{
  status: string;
  message: string;
}> {
  return request(`${BASE}/smart-import/pending-reviews/${id}/reject`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ reason }),
  });
}

export async function reanalyzePendingReview(id: number): Promise<{
  status: string;
  message?: string;
  pending_id?: number;
  material_id?: number;
}> {
  return request(`${BASE}/smart-import/pending-reviews/${id}/reanalyze`, {
    method: 'POST',
  });
}

export async function deletePendingReview(id: number): Promise<{
  status: string;
  message: string;
}> {
  return request(`${BASE}/smart-import/pending-reviews/${id}`, {
    method: 'DELETE',
  });
}

export async function getSmartImportStats(): Promise<{
  pending: number;
  approved: number;
  rejected: number;
  total: number;
}> {
  return request(`${BASE}/smart-import/stats`);
}

export async function getPendingReviewProgress(id: number): Promise<{
  status: string;
  progress?: {
    stage: string;
    message: string;
    current_page: number;
    total_pages: number;
    ocr_results?: Array<{
      page: number;
      chars: number;
      preview: string;
      status: string;
    }>;
  };
}> {
  return request(`${BASE}/smart-import/pending-reviews/${id}/progress`);
}
