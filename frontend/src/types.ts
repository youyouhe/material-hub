export interface CompanyInfo {
  id: number;
  name: string;
  legal_person: string | null;
  credit_code: string | null;
  address: string | null;
  created_at: string | null;
  updated_at: string | null;
  document_count?: number;
  material_count?: number;
}

export interface PersonInfo {
  id: number;
  name: string;
  id_number: string | null;
  education: string | null;
  position: string | null;
  company_id: number | null;
  created_at: string | null;
  updated_at: string | null;
  material_count?: number;
}

export interface DocumentInfo {
  id: number;
  filename: string;
  docx_path: string | null;
  company_id: number | null;
  company_name: string | null;
  upload_time: string | null;
  section_count: number;
  image_count: number;
}

export interface MaterialInfo {
  id: number;
  document_id: number;
  company_id: number | null;
  person_id: number | null;
  source_filename: string | null;
  section: string;
  title: string;
  heading_level: number;
  image_filename: string;
  image_url: string;
  file_size: number;
  expiry_date: string | null;
  is_expired: boolean | null;
  material_type: string | null;
  ocr_text: string | null;
  extracted_data: any | null;
  ocr_status: 'pending' | 'processing' | 'completed' | 'failed' | null;
  ocr_error: string | null;
  ocr_processed_at: string | null;
  created_at: string | null;
}

export interface OCRResult {
  status: 'pending' | 'processing' | 'completed' | 'failed';
  ocr_text: string | null;
  extracted_data: any | null;
  material_type: string | null;
  error: string | null;
  processed_at: string | null;
}

export interface ExtractionResult {
  document_id: number;
  filename: string;
  section_count: number;
  image_count: number;
  materials: MaterialInfo[];
}

export type ExpiryStatus = 'valid' | 'expired' | 'all';
