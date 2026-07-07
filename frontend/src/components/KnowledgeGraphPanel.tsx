import { useEffect, useRef, useState } from 'react';
import { Network, DataSet } from 'vis-network/standalone';
import { RefreshCw, X, Maximize2, Minimize2 } from 'lucide-react';
import { kbGetEntityGraph, kbSearchEntities, kbGetBatchRelations } from '../services/api-v2';
import type { KbGraphResponse } from '../types/dms';

interface EntityItem {
  entity_name: string;
  entity_type?: string;
  role?: string;
}

interface Props {
  entityName: string;
  /** Additional entity names — renders a document-centric graph with all entities */
  entities?: EntityItem[];
  onClose?: () => void;
  onSelectDocument?: (docId: number) => void;
  compact?: boolean;
}

// Color palette matching cp-* design system
const COLORS: Record<string, { bg: string; border: string; highlight: string }> = {
  org:         { bg: '#06b6d4', border: '#0891b2', highlight: '#22d3ee' },  // cp-cyan
  person:      { bg: '#22c55e', border: '#16a34a', highlight: '#4ade80' },  // cp-green
  project:     { bg: '#f59e0b', border: '#d97706', highlight: '#fbbf24' },  // amber
  product:     { bg: '#3b82f6', border: '#2563eb', highlight: '#60a5fa' },  // blue
  certificate: { bg: '#ef4444', border: '#dc2626', highlight: '#f87171' },  // red
  topic:       { bg: '#8b5cf6', border: '#7c3aed', highlight: '#a78bfa' },  // violet
  location:    { bg: '#ec4899', border: '#db2777', highlight: '#f472b6' },  // pink
  concept:     { bg: '#6366f1', border: '#4f46e5', highlight: '#818cf8' },  // indigo
  event:       { bg: '#a855f7', border: '#9333ea', highlight: '#c084fc' },  // cp-purple
  document:    { bg: '#6b7280', border: '#4b5563', highlight: '#9ca3af' },  // cp-muted
  default:     { bg: '#475569', border: '#334155', highlight: '#64748b' },  // slate
};

function getNodeStyle(type: string) {
  return COLORS[type] || COLORS.default;
}

function getShape(type: string): string {
  if (type === 'event') return 'diamond';
  if (type === 'document') return 'square';
  if (type === 'project') return 'hexagon';
  return 'dot'; // org, person, product, topic, etc.
}

export default function KnowledgeGraphPanel({ entityName, entities, onClose, onSelectDocument, compact }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);
  const networkRef = useRef<Network | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState(!compact);
  const [error, setError] = useState('');
  const [data, setData] = useState<KbGraphResponse | null>(null);
  const [showLegend, setShowLegend] = useState(false);
  const [selectedInfo, setSelectedInfo] = useState('');

  // Load graph data
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError('');

    // Document-centric mode: skip API call, render directly from entities prop
    if (entities && entities.length > 0) {
      setData(null); // Signal doc-centric mode
      setLoading(false);
      return;
    }

    // Entity-centric mode: call graph API
    kbGetEntityGraph(entityName, 2)
      .then(d => {
        if (!cancelled) {
          if ((d as any).error || !d.entity) {
            setError((d as any).error?.message || `未找到实体: ${entityName}`);
            setLoading(false);
          } else {
            setData(d);
            setLoading(false);
          }
        }
      })
      .catch(e => {
        if (!cancelled) { setError(e.message || 'Failed to load graph'); setLoading(false); }
      });
    return () => { cancelled = true; };
  }, [entityName]);

  // Build and render vis-network
  useEffect(() => {
    if (loading) return;
    if (!containerRef.current) return;

    // ── Document-centric mode: multiple entities around doc node ──
    if (!data && entities && entities.length > 0) {
      const nodes: any[] = [];
      const edges: any[] = [];

      // Center: document node
      const docId = 'doc-center';
      nodes.push({
        id: docId, label: entityName.length > 20 ? entityName.slice(0, 20) + '...' : entityName,
        shape: 'square', color: COLORS.document,
        font: { size: 16, color: '#e2e8f0', bold: { color: '#f1f5f9' } },
        size: 30, title: `<b>${entityName}</b>`,
      });

      // Entity nodes surrounding the document
      const entityNodeIds: string[] = [];
      (entities || []).forEach((e, i) => {
        const eid = `e-${i}`;
        entityNodeIds.push(eid);
        const etype = e.entity_type || 'topic';
        const style = getNodeStyle(etype);
        nodes.push({
          id: eid,
          label: (e.entity_name || '').length > 15 ? (e.entity_name || '').slice(0, 15) + '...' : (e.entity_name || ''),
          shape: getShape(etype),
          color: style,
          font: { size: 13, color: '#cbd5e1' },
          size: 25,
          title: `<b>${e.entity_name}</b><br/>${etype}${e.role ? '<br/>role: ' + e.role : ''}`,
        });
        // Document → entity edge
        edges.push({
          from: docId, to: eid,
          color: { color: style.border, highlight: style.highlight, opacity: 0.7 },
          width: 2, smooth: { type: 'curvedCW', roundness: 0.2 },
        });
      });

      // Entity-to-entity mesh: connect same-type entities (e.g. all persons, all concepts)
      // This creates a natural cluster structure
      const byType = new Map<string, string[]>();
      entityNodeIds.forEach((eid, i) => {
        const t = (entities || [])[i]?.entity_type || 'topic';
        if (!byType.has(t)) byType.set(t, []);
        byType.get(t)!.push(eid);
      });
      byType.forEach((group, etype) => {
        if (group.length < 2) return;
        const style = getNodeStyle(etype);
        for (let i = 0; i < group.length; i++) {
          for (let j = i + 1; j < group.length; j++) {
            // Skip if group is large — just connect neighbors
            if (group.length > 6 && j - i > 2) continue;
            edges.push({
              from: group[i], to: group[j],
              color: { color: style.border, highlight: style.highlight, opacity: 0.25 },
              width: 0.4, dashes: true,
              title: `同类型实体共现 (${etype})`,
              smooth: { type: 'curvedCW', roundness: 0.4 },
            });
          }
        }
      });

      // Fetch entity-to-entity relations (2nd layer)
      const entityNames = (entities || []).map(e => e.entity_name).filter(Boolean) as string[];
      if (entityNames.length >= 2) {
        kbGetBatchRelations(entityNames).then(({ relations }) => {
          if (relations && relations.length > 0 && networkRef.current) {
            const nodeIdx = new Map<string, string>();
            (entities || []).forEach((e, i) => { nodeIdx.set(e.entity_name, `e-${i}`); });
            const addedEdges: any[] = [];
            relations.forEach(r => {
              const fromId = nodeIdx.get(r.from_name);
              const toId = nodeIdx.get(r.to_name);
              if (fromId && toId && fromId !== toId) {
                addedEdges.push({
                  from: fromId, to: toId,
                  label: r.relation,
                  title: `<b>${r.relation}</b><br/>${r.from_name} → ${r.to_name}`,
                  arrows: 'to',
                  color: { color: '#a855f7', highlight: '#c084fc' },
                  width: 2,
                  smooth: { type: 'curvedCW', roundness: 0.3 },
                });
              }
            });
            if (addedEdges.length > 0) {
              try {
                const ds = (networkRef.current as any).body.data;
                ds.edges.add(addedEdges);
                networkRef.current!.fit({ animation: { duration: 300 } });
              } catch {}
            }
          }
        }).catch(() => {});
      }

      // Destroy previous
      if (networkRef.current) { networkRef.current.destroy(); networkRef.current = null; }

      const network = new Network(containerRef.current!, { nodes: new DataSet(nodes), edges: new DataSet(edges) }, {
        physics: { solver: 'forceAtlas2Based', forceAtlas2Based: { gravitationalConstant: -50, centralGravity: 0.01, springLength: 180, springConstant: 0.05 } },
        interaction: { hover: true, tooltipDelay: 200, zoomView: true, dragView: true },
        nodes: { borderWidth: 2, shadow: { enabled: true, color: 'rgba(0,0,0,0.3)', size: 5 } },
        edges: { font: { align: 'middle' } },
        layout: { improvedLayout: true },
      });
      // Click: select node/edge to show info
      network.on('click', (params: any) => {
        if (params.nodes.length > 0) {
          const nid = params.nodes[0];
          const node = nodes.find(n => n.id === nid);
          if (node) { setSelectedInfo(node.title || ''); return; }
        }
        if (params.edges.length > 0) {
          const eid = params.edges[0];
          const edge = edges.find(e => e.id === eid);
          if (edge && edge.label) { setSelectedInfo(`边: ${edge.label}`); return; }
          if (edge && edge.title) { setSelectedInfo(edge.title); return; }
          setSelectedInfo('同文档共现（弱关联）');
          return;
        }
        setSelectedInfo('');
      });

      networkRef.current = network;
      // Fit after layout settles, then on window resize
      const fit = () => { try { network?.fit({ animation: { duration: 400 } }); } catch {} };
      setTimeout(fit, 300);
      setTimeout(fit, 800);  // Double-fire for slow renders
      window.addEventListener('resize', fit);
      return () => {
        window.removeEventListener('resize', fit);
        if (networkRef.current) { networkRef.current.destroy(); networkRef.current = null; }
      };
    }

    // ── Entity-centric mode: graph API data ──
    if (!data || !containerRef.current) return;

    const nodes: any[] = [];
    const edges: any[] = [];
    const nodeIds = new Set<number>();

    // Center entity
    const center = data.entity;
    nodeIds.add(center.id);
    nodes.push({
      id: center.id,
      label: center.name,
      shape: getShape(center.entity_type || 'org'),
      color: getNodeStyle(center.entity_type || 'org'),
      font: { size: 16, color: '#e2e8f0', bold: { color: '#f1f5f9' } },
      size: 35,
      title: `<b>${center.name}</b><br/>${center.entity_type || ''}`,
    });

    // Related entities
    (data.related_entities || []).forEach(e => {
      if (nodeIds.has(e.id)) return;
      nodeIds.add(e.id);
      nodes.push({
        id: e.id,
        label: e.name,
        shape: getShape(e.entity_type || 'org'),
        color: getNodeStyle(e.entity_type || 'org'),
        font: { size: 13, color: '#cbd5e1' },
        size: 25,
        title: `<b>${e.name}</b><br/>${e.entity_type || ''}`,
      });
    });

    // Events
    (data.events || []).forEach(e => {
      const evtId = `evt-${e.id}`;
      nodeIds.add(evtId as any);
      nodes.push({
        id: evtId,
        label: e.title.length > 15 ? e.title.slice(0, 15) + '...' : e.title,
        shape: 'diamond',
        color: getNodeStyle('event'),
        font: { size: 11, color: '#94a3b8' },
        size: 18,
        title: `<b>${e.title}</b><br/>${e.event_type || ''}${e.event_date ? '<br/>' + e.event_date : ''}`,
      });
    });

    // Relations as edges
    (data.relations || []).forEach(r => {
      const from = r.from_id || r.source_id;
      const to = r.to_id || r.target_id;
      if (from && to) {
        edges.push({
          from,
          to,
          label: r.relation,
          arrows: 'to',
          color: { color: '#475569', highlight: '#64748b' },
          font: { size: 10, color: '#64748b', strokeWidth: 0 },
          width: 1.5,
          smooth: { type: 'curvedCW', roundness: 0.2 },
        });
      }
    });

    // Event → entity links
    (data.events || []).forEach(e => {
      const evtId = `evt-${e.id}`;
      // Link to related entities that are in our nodes
      (data.related_entities || []).slice(0, 3).forEach(re => {
        edges.push({
          from: evtId,
          to: re.id,
          dashes: true,
          color: { color: '#a855f7', highlight: '#c084fc', opacity: 0.5 },
          width: 0.8,
          smooth: { type: 'curvedCW', roundness: 0.3 },
        });
      });
    });

    // Depth-2 entities
    (data.depth2_entities || []).slice(0, 8).forEach(e => {
      if (nodeIds.has(e.id)) return;
      nodeIds.add(e.id);
      nodes.push({
        id: e.id,
        label: e.name,
        shape: 'dot',
        color: { bg: '#334155', border: '#475569', highlight: '#64748b' },
        font: { size: 10, color: '#64748b' },
        size: 15,
        title: `<b>${e.name}</b><br/>${e.entity_type || ''} (depth-2)`,
      });
    });

    // Destroy previous network
    if (networkRef.current) {
      networkRef.current.destroy();
      networkRef.current = null;
    }

    const network = new Network(containerRef.current!, { nodes: new DataSet(nodes), edges: new DataSet(edges) }, {
      physics: {
        solver: 'forceAtlas2Based',
        forceAtlas2Based: { gravitationalConstant: -40, centralGravity: 0.005, springLength: 150, springConstant: 0.08 },
      },
      interaction: {
        hover: true,
        tooltipDelay: 200,
        zoomView: true,
        dragView: true,
      },
      nodes: {
        borderWidth: 2,
        shadow: { enabled: true, color: 'rgba(0,0,0,0.3)', size: 5 },
      },
      edges: {
        font: { align: 'middle' },
      },
      layout: { improvedLayout: true },
    });

    // Click handler: expand on node click
    network.on('doubleClick', (params: any) => {
      if (params.nodes.length > 0) {
        const nodeId = params.nodes[0];
        const node = nodes.find(n => n.id === nodeId);
        if (node && typeof nodeId === 'number') {
          // Refresh with clicked entity as center
          setData(null);
          setLoading(true);
          kbGetEntityGraph(node.label || String(nodeId), 2)
            .then(d => { setData(d); setLoading(false); })
            .catch(e => { setError(e.message || 'Failed'); setLoading(false); });
        }
      }
    });

    networkRef.current = network;

    // Fit after a short delay
    setTimeout(() => {
      try { network.fit({ animation: { duration: 500, easingFunction: 'easeInOutQuad' } }); } catch {}
    }, 300);

    return () => {
      if (networkRef.current) {
        networkRef.current.destroy();
        networkRef.current = null;
      }
    };
  }, [data, loading]);

  const height = compact ? (expanded ? 'h-[400px]' : 'h-[300px]') : 'h-full min-h-0';

  return (
    <div className={`bg-cp-card border border-cp-divider overflow-hidden flex flex-col ${height}`} style={compact ? {} : { height: '100vh' }}>
      {/* Header */}
      <div className="flex items-center justify-between px-3 py-2 bg-cp-bg/50 border-b border-cp-divider shrink-0">
        <div className="flex items-center gap-2">
          <span className="text-sm font-medium text-cp-text">🔗 知识图谱</span>
          {!compact && <span className="text-xs text-cp-muted">双击节点展开关系 · 滚轮缩放 · 拖拽平移</span>}
          {compact && data && <span className="text-xs text-cp-muted">{data.entity.name}</span>}
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => setShowLegend(!showLegend)}
            className="p-1 rounded hover:bg-cp-purple/10 text-cp-muted hover:text-cp-purple-light text-xs"
            title="图例">
            {showLegend ? '隐藏图例' : '图例'}
          </button>
          {compact && (
            <button onClick={() => setExpanded(!expanded)}
              className="p-1 rounded hover:bg-cp-purple/10 text-cp-muted hover:text-cp-purple-light"
              title={expanded ? '缩小' : '放大'}>
              {expanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
            </button>
          )}
          {onClose && (
            <button onClick={onClose}
              className="p-1 rounded hover:bg-cp-rose/10 text-cp-muted hover:text-cp-rose"
              title="关闭">
              <X className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Legend */}
      {showLegend && (
        <div className="px-3 py-2 bg-cp-bg/30 border-b border-cp-divider text-xs text-cp-muted flex flex-wrap gap-x-4 gap-y-1">
          <span>🔗 实线 = 显式关系</span>
          <span>┅ 虚线 = 同类型实体共现</span>
          <span>🟢 绿 = 人物</span>
          <span>🟡 黄 = 项目</span>
          <span>🟣 紫 = 主题</span>
          <span>🔵 蓝 = 产品/系统</span>
          <span>🩷 粉 = 地点</span>
          <span>💜 靛蓝 = 概念</span>
          <span>📄 灰 = 文档</span>
          <span className="text-cp-dim ml-auto">点击节点/边查看详情 · 双击节点展开</span>
        </div>
      )}

      {/* Selected info */}
      {selectedInfo && (
        <div className="px-3 py-1.5 bg-cp-purple/10 border-b border-cp-purple/20 text-xs text-cp-purple-light truncate"
             dangerouslySetInnerHTML={{ __html: selectedInfo }} />
      )}

      {/* Content */}
      {loading && (
        <div className="flex items-center justify-center flex-1 text-cp-muted gap-2">
          <RefreshCw className="w-5 h-5 animate-spin" />
          <span className="text-sm">加载图谱...</span>
        </div>
      )}
      {error && (
        <div className="flex items-center justify-center flex-1 text-cp-rose text-sm">{error}</div>
      )}
      {!loading && !error && (
        <div ref={containerRef} className="w-full flex-1" />
      )}
    </div>
  );
}
