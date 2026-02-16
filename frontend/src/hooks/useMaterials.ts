import { useState, useCallback } from 'react';
import type { MaterialInfo, DocumentInfo, ExpiryStatus } from '../types';
import * as api from '../services/api';

export function useMaterials() {
  const [materials, setMaterials] = useState<MaterialInfo[]>([]);
  const [documents, setDocuments] = useState<DocumentInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadDocuments = useCallback(async () => {
    try {
      const docs = await api.listDocuments();
      setDocuments(docs);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load documents');
    }
  }, []);

  const search = useCallback(
    async (params: { q?: string; document_id?: number; status?: ExpiryStatus }) => {
      setLoading(true);
      setError(null);
      try {
        const results = await api.searchMaterials(params);
        setMaterials(results);
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Search failed');
      } finally {
        setLoading(false);
      }
    },
    []
  );

  const updateExpiry = useCallback(
    async (id: number, expiry_date: string) => {
      try {
        const updated = await api.updateMaterial(id, { expiry_date });
        setMaterials((prev) =>
          prev.map((m) => (m.id === id ? updated : m))
        );
        return updated;
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Update failed');
        return null;
      }
    },
    []
  );

  const remove = useCallback(async (id: number) => {
    try {
      await api.deleteMaterial(id);
      setMaterials((prev) => prev.filter((m) => m.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delete failed');
    }
  }, []);

  const removeDocument = useCallback(
    async (id: number) => {
      try {
        await api.deleteDocument(id);
        setDocuments((prev) => prev.filter((d) => d.id !== id));
        setMaterials((prev) => prev.filter((m) => m.document_id !== id));
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Delete failed');
      }
    },
    []
  );

  return {
    materials,
    documents,
    loading,
    error,
    loadDocuments,
    search,
    updateExpiry,
    remove,
    removeDocument,
  };
}
