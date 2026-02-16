import type { DocumentInfo, MaterialInfo, ExtractionResult, ExpiryStatus } from '../types';

const BASE = '/api';

async function request<T>(url: string, options?: RequestInit): Promise<T> {
  const res = await fetch(url, options);
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

// --- Documents ---

export async function uploadDocument(file: File): Promise<ExtractionResult> {
  const form = new FormData();
  form.append('file', file);
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

export async function searchMaterials(params: {
  q?: string;
  document_id?: number;
  status?: ExpiryStatus;
}): Promise<MaterialInfo[]> {
  const sp = new URLSearchParams();
  if (params.q) sp.set('q', params.q);
  if (params.document_id) sp.set('document_id', String(params.document_id));
  if (params.status) sp.set('status', params.status);
  const data = await request<{ results: MaterialInfo[] }>(
    `${BASE}/materials?${sp.toString()}`
  );
  return data.results;
}

export async function updateMaterial(
  id: number,
  update: { title?: string; section?: string; expiry_date?: string }
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
