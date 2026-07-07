/**
 * Adapters to map DMS v2 types to legacy shapes for existing UI components.
 */
import type { Entity, SearchResult, DmsDocument } from '../types/dms';

export function entityToCompanyInfo(e: Entity) {
  const attrs = e.attributes || {};
  return {
    id: e.id, name: e.name,
    legal_person: (attrs.legal_person as string) || null,
    credit_code: (attrs.credit_code as string) || null,
    address: (attrs.address as string) || null,
    created_at: e.created_at, updated_at: e.updated_at,
    document_count: (e as any).document_count || 0,
    material_count: (e as any).document_count || 0,
  };
}

export function entityToPersonInfo(e: Entity) {
  const attrs = e.attributes || {};
  return {
    id: e.id, name: e.name,
    id_number: (attrs.id_number as string) || null,
    education: (attrs.education as string) || null,
    position: (attrs.position as string) || null,
    company_id: null, created_at: e.created_at, updated_at: e.updated_at,
    material_count: (e as any).document_count || 0,
  };
}

export function searchResultToMaterialInfo(r: SearchResult): any {
  return {
    id: r.id,
    document_id: r.id,
    title: r.title,
    section: r.folder?.name || '',
    heading_level: 1,
    image_filename: '',
    image_path: '',
    image_url: r.thumbnail_url || '',
    file_size: 0,
    file_hash: '',
    expiry_date: r.expiry_date,
    is_expired: r.expiry_date ? new Date(r.expiry_date) < new Date() : null,
    material_type: r.doc_type?.code || null,
    ocr_text: r.snippet || null,
    extracted_data: null,
    ocr_status: null,
    ocr_error: null,
    ocr_processed_at: null,
    created_at: r.created_at,
    company_id: null,
    person_id: null,
    source_filename: '',
  };
}

export function docToMaterialInfo(doc: DmsDocument): any {
  const meta = doc.metadata || {};
  const curRev = doc.current_revision;
  const firstFile = curRev?.files?.[0];
  return {
    id: doc.id, document_id: doc.id,
    title: doc.title,
    section: doc.folder?.name || '',
    heading_level: 1,
    image_filename: firstFile?.filename || '',
    image_path: firstFile?.storage_path || '',
    image_url: firstFile?.url || '',
    file_size: firstFile?.file_size || 0,
    file_hash: firstFile?.file_hash || '',
    expiry_date: doc.expiry_date,
    is_expired: doc.expiry_date ? new Date(doc.expiry_date) < new Date() : null,
    material_type: meta.material_type || null,
    ocr_text: (meta._legacy_ocr as any)?.text || null,
    extracted_data: meta.extracted_data || null,
    ocr_status: null, ocr_error: null, ocr_processed_at: null,
    created_at: doc.created_at,
    company_id: null, person_id: null,
    source_filename: firstFile?.filename || '',
  };
}
