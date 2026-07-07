import { useState, useCallback } from 'react';
import { searchDocuments } from '../services/api-v2';
import { searchResultToMaterialInfo } from '../services/adapters';

export function useMaterials() {
  const [materials, setMaterials] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const search = useCallback(async (params: {
    q?: string;
    status?: string;
    entity_id?: number;
    folder_id?: number;
    doc_type_id?: number;
  }) => {
    setLoading(true);
    setError(null);
    try {
      const data = await searchDocuments({ ...params, limit: 100 });
      setMaterials(data.results.map(searchResultToMaterialInfo));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Search failed');
    } finally {
      setLoading(false);
    }
  }, []);

  const remove = useCallback(async (id: number) => {
    try {
      const { deleteDocument } = await import('../services/api-v2');
      await deleteDocument(id);
      setMaterials(prev => prev.filter(m => m.id !== id));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Delete failed');
    }
  }, []);

  return { materials, loading, error, search, remove };
}
