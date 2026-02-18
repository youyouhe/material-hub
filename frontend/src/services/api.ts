import type { DocumentInfo, MaterialInfo, ExtractionResult, ExpiryStatus, CompanyInfo, PersonInfo } from '../types';

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

// --- OCR ---

export async function triggerOCR(materialId: number): Promise<{ status: string; message: string; material_id: number }> {
  return request<{ status: string; message: string; material_id: number }>(`${BASE}/materials/${materialId}/ocr`, {
    method: 'POST',
  });
}

export async function getOCRResult(materialId: number): Promise<import('../types').OCRResult> {
  return request<import('../types').OCRResult>(`${BASE}/materials/${materialId}/ocr`);
}
