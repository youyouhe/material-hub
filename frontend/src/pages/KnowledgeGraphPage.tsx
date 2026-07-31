import { useEffect, useRef, useState, useMemo, useCallback } from 'react';
import { Network, DataSet } from 'vis-network/standalone';
import { RefreshCw, X } from 'lucide-react';
import clsx from 'clsx';
import toast from 'react-hot-toast';
import { listEntities, getEntityRelations } from '../services/api-v2';
import type { Entity, EntityRelation } from '../types/dms';

// 节点配色(与 KnowledgeGraphPanel 一致)
const COLORS: Record<string, { bg: string; border: string; highlight: string }> = {
  org:         { bg: '#06b6d4', border: '#0891b2', highlight: '#22d3ee' },
  person:      { bg: '#22c55e', border: '#16a34a', highlight: '#4ade80' },
  project:     { bg: '#f59e0b', border: '#d97706', highlight: '#fbbf24' },
  product:     { bg: '#3b82f6', border: '#2563eb', highlight: '#60a5fa' },
  certificate: { bg: '#ef4444', border: '#dc2626', highlight: '#f87171' },
  topic:       { bg: '#8b5cf6', border: '#7c3aed', highlight: '#a78bfa' },
  location:    { bg: '#ec4899', border: '#db2777', highlight: '#f472b6' },
  concept:     { bg: '#6366f1', border: '#4f46f5', highlight: '#818cf8' },
  default:     { bg: '#475569', border: '#334155', highlight: '#64748b' },
};
function getNodeStyle(type: string) { return COLORS[type] || COLORS.default; }
function getShape(type: string): string {
  if (type === 'project') return 'hexagon';
  return 'dot';
}

export default function KnowledgeGraphPage() {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const [loading, setLoading] = useState(true);
  const [entities, setEntities] = useState<Entity[]>([]);
  const [relations, setRelations] = useState<EntityRelation[]>([]);
  const [selected, setSelected] = useState<Entity | null>(null);
  const [typeFilter, setTypeFilter] = useState<Set<string>>(new Set());
  const [relFilter, setRelFilter] = useState<Set<string>>(new Set());
  const [searchText, setSearchText] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [ent, rel] = await Promise.all([listEntities(), getEntityRelations()]);
      setEntities(ent.results);
      setRelations(rel.results);
      setSelected(null);
    } catch {
      toast.error('加载知识图谱失败');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const entityTypes = useMemo(() => Array.from(new Set(entities.map(e => e.entity_type))), [entities]);
  const relationTypes = useMemo(() => Array.from(new Set(relations.map(r => r.relation))), [relations]);

  const toggle = (filter: Set<string>, setter: (s: Set<string>) => void, val: string) => {
    const next = new Set(filter);
    if (next.has(val)) next.delete(val); else next.add(val);
    setter(next);
  };

  // 构建/重建图谱
  useEffect(() => {
    if (loading || !containerRef.current) return;
    const searchLower = searchText.toLowerCase().trim();
    const nameMatches = searchLower ? entities.filter(e => e.name.toLowerCase().includes(searchLower)) : entities;
    const visibleEntities = nameMatches.filter(e => typeFilter.size === 0 || typeFilter.has(e.entity_type));
    const visibleIds = new Set(visibleEntities.map(e => e.id));
    const visibleRelations = relations.filter(r =>
      (relFilter.size === 0 || relFilter.has(r.relation)) && visibleIds.has(r.from_id) && visibleIds.has(r.to_id)
    );

    const nodes: any[] = visibleEntities.map(e => ({
      id: e.id,
      label: e.name.length > 12 ? e.name.slice(0, 12) + '…' : e.name,
      shape: getShape(e.entity_type),
      color: getNodeStyle(e.entity_type),
      font: { size: 13, color: '#cbd5e1' },
      size: 22,
      title: `<b>${e.name}</b><br/>类型: ${e.entity_type}${e.document_count ? `<br/>文档: ${e.document_count}` : ''}`,
    }));
    const edges: any[] = visibleRelations.map((r, i) => ({
      id: 'e' + i,
      from: r.from_id,
      to: r.to_id,
      label: r.relation,
      arrows: 'to',
      color: { color: '#475569', highlight: '#64748b' },
      font: { size: 10, color: '#64748b', strokeWidth: 0 },
      width: 1.5,
      title: `<b>${r.relation}</b><br/>${r.from_name} → ${r.to_name}`,
    }));

    if (networkRef.current) { networkRef.current.destroy(); networkRef.current = null; }
    const network = new Network(containerRef.current, { nodes: new DataSet(nodes), edges: new DataSet(edges) }, {
      physics: { solver: 'forceAtlas2Based', forceAtlas2Based: { gravitationalConstant: -40, centralGravity: 0.01, springLength: 160, springConstant: 0.05 } },
      interaction: { hover: true, tooltipDelay: 200, zoomView: true, dragView: true },
      nodes: { borderWidth: 2, shadow: { enabled: true, color: 'rgba(0,0,0,0.3)', size: 5 } },
      edges: { font: { align: 'middle' }, smooth: { enabled: true, type: 'curvedCW', roundness: 0.2 } },
    });
    network.on('click', (params: any) => {
      if (params.nodes.length > 0) {
        const ent = entities.find(e => e.id === params.nodes[0]);
        if (ent) setSelected(ent);
      } else {
        setSelected(null);
      }
    });
    networkRef.current = network;
    const fit = () => { try { network.fit({ animation: { duration: 400, easingFunction: 'easeInOutQuad' } }); } catch {} };
    setTimeout(fit, 300); setTimeout(fit, 800);
    return () => { if (networkRef.current) { networkRef.current.destroy(); networkRef.current = null; } };
  }, [loading, entities, relations, typeFilter, relFilter, searchText]);

  const selectedRelations = selected ? relations.filter(r => r.from_id === selected.id || r.to_id === selected.id) : [];

  return (
    <div className="flex flex-col h-full">
      {/* 工具栏 */}
      <div className="flex items-center gap-3 px-4 py-2 bg-cp-card border-b border-cp-border shrink-0 flex-wrap">
        <h2 className="text-base font-orbitron font-semibold text-cp-purple-light">🔗 知识图谱</h2>
        <span className="text-xs text-cp-muted">{entities.length} 实体 · {relations.length} 关系</span>
        <div className="flex-1" />
        {/* 搜索框 */}
        <div className="relative">
          <input
            type="text"
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
            placeholder="搜索实体..."
            className="cp-input w-40 text-xs py-1 px-2 pr-6 rounded"
          />
          {searchText && (
            <button
              onClick={() => setSearchText('')}
              className="absolute right-1 top-1/2 -translate-y-1/2 text-cp-dim hover:text-cp-text"
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
        {entityTypes.length > 0 && (
          <div className="flex items-center gap-1">
            <span className="text-xs text-cp-dim">类型:</span>
            {entityTypes.map(t => {
              const active = typeFilter.size === 0 || typeFilter.has(t);
              return (
                <button key={t} onClick={() => toggle(typeFilter, setTypeFilter, t)}
                  className={clsx('px-2 py-0.5 text-xs rounded border transition-all',
                    active
                      ? 'bg-cp-purple/20 text-cp-purple-light border-cp-purple/40'
                      : 'opacity-30 text-cp-muted border-cp-border hover:opacity-50')}>
                  <span className="inline-block w-2 h-2 rounded-full mr-1 align-middle"
                    style={{ background: getNodeStyle(t).bg, opacity: active ? 1 : 0.3 }} />{t}
                </button>
              );
            })}
          </div>
        )}
        {relationTypes.length > 0 && (
          <div className="flex items-center gap-1">
            <span className="text-xs text-cp-dim">关系:</span>
            {relationTypes.map(r => {
              const active = relFilter.size === 0 || relFilter.has(r);
              return (
                <button key={r} onClick={() => toggle(relFilter, setRelFilter, r)}
                  className={clsx('px-2 py-0.5 text-xs rounded border transition-all',
                    active
                      ? 'bg-cp-purple/20 text-cp-purple-light border-cp-purple/40'
                      : 'opacity-30 text-cp-muted border-cp-border hover:opacity-50')}>
                  {r}
                </button>
              );
            })}
          </div>
        )}
        <button onClick={load} title="刷新" className="p-1 rounded cp-hover text-cp-muted hover:text-cp-text">
          <RefreshCw className={clsx('w-4 h-4', loading && 'animate-spin')} />
        </button>
      </div>

      {/* 主体: 图谱 + 详情面板 */}
      <div className="flex-1 flex min-h-0">
        <div className="flex-1 relative bg-cp-bg/30">
          {loading && (
            <div className="absolute inset-0 flex items-center justify-center text-cp-muted gap-2 z-10">
              <RefreshCw className="w-5 h-5 animate-spin" /><span className="text-sm">加载图谱...</span>
            </div>
          )}
          {!loading && entities.length === 0 && (
            <div className="absolute inset-0 flex items-center justify-center text-cp-muted text-sm">暂无实体数据</div>
          )}
          <div ref={containerRef} className="w-full h-full" />
        </div>

        {selected && (
          <div className="w-72 border-l border-cp-border bg-cp-card p-3 overflow-y-auto shrink-0">
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <span className="inline-block w-3 h-3 rounded-full" style={{ background: getNodeStyle(selected.entity_type).bg }} />
                <span className="text-sm font-medium text-cp-text">{selected.name}</span>
              </div>
              <button onClick={() => setSelected(null)} className="text-cp-dim hover:text-cp-text"><X className="w-4 h-4" /></button>
            </div>
            <div className="space-y-1.5 text-xs">
              <div className="text-cp-muted">类型: <span className="text-cp-text">{selected.entity_type}</span></div>
              {selected.document_count !== undefined && (
                <div className="text-cp-muted">关联文档: <span className="text-cp-text">{selected.document_count}</span></div>
              )}
            </div>
            {selectedRelations.length > 0 && (
              <>
                <div className="text-xs text-cp-dim mt-3 mb-1 uppercase tracking-wider">关联关系</div>
                <div className="space-y-1">
                  {selectedRelations.map(r => (
                    <div key={r.id} className="text-xs text-cp-muted py-1 px-2 rounded bg-cp-bg/40">
                      {r.from_id === selected.id ? `→ ${r.relation} → ${r.to_name}` : `${r.from_name} → ${r.relation} →`}
                    </div>
                  ))}
                </div>
              </>
            )}
            {selected.attributes && Object.keys(selected.attributes).length > 0 && (
              <>
                <div className="text-xs text-cp-dim mt-3 mb-1 uppercase tracking-wider">属性</div>
                <div className="space-y-1">
                  {Object.entries(selected.attributes).map(([k, v]) => (
                    <div key={k} className="text-xs text-cp-muted"><span className="text-cp-dim">{k}:</span> {String(v)}</div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
