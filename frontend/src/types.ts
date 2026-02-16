export interface DocumentInfo {
  id: number;
  filename: string;
  upload_time: string | null;
  section_count: number;
  image_count: number;
}

export interface MaterialInfo {
  id: number;
  document_id: number;
  source_filename: string | null;
  section: string;
  title: string;
  heading_level: number;
  image_filename: string;
  image_url: string;
  file_size: number;
  expiry_date: string | null;
  is_expired: boolean | null;
  created_at: string | null;
}

export interface ExtractionResult {
  document_id: number;
  filename: string;
  section_count: number;
  image_count: number;
  materials: MaterialInfo[];
}

export type ExpiryStatus = 'valid' | 'expired' | 'all';
