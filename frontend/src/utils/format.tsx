import React from 'react';

/** Render any extracted data value as JSX — nested objects expanded, arrays as tables. */
export function RenderValue({ value }: { value: unknown }): React.ReactNode {
  if (value === null || value === undefined) return <span className="text-cp-dim">-</span>;

  // Array of objects → mini table
  if (Array.isArray(value) && value.length > 0 && typeof value[0] === 'object' && value[0] !== null) {
    const keys = Array.from(new Set(value.flatMap(item => Object.keys(item as object))));
    return (
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr className="border-b border-cp-border">
            {keys.map(k => (
              <th key={k} className="text-left py-1 pr-2 text-cp-muted font-medium whitespace-nowrap">{labelMap[k] || k}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {value.map((item, i) => (
            <tr key={i} className="border-b border-cp-border/30">
              {keys.map(k => (
                <td key={k} className="py-1 pr-2 text-cp-text">{formatPrimitive((item as any)[k])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    );
  }

  // Array of primitives → list
  if (Array.isArray(value)) {
    return (
      <div className="space-y-0.5">
        {value.map((item, i) => (
          <div key={i} className="text-cp-text">{formatPrimitive(item)}</div>
        ))}
      </div>
    );
  }

  // Object → key-value rows
  if (typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>);
    return (
      <div className="space-y-1">
        {entries.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3 text-xs">
            <span className="text-cp-muted shrink-0">{labelMap[k] || k}</span>
            <span className="text-cp-text text-right">{formatPrimitive(v)}</span>
          </div>
        ))}
      </div>
    );
  }

  return <span className="text-cp-text">{String(value)}</span>;
}

function formatPrimitive(v: unknown): string {
  if (v === null || v === undefined) return '-';
  if (typeof v === 'number') {
    // Format as 2 decimal places if it looks like currency
    return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(2);
  }
  return String(v);
}

/** Chinese labels for common field names */
const labelMap: Record<string, string> = {
  tax_category: '税种',
  tax_period: '所属期',
  payment_date: '缴纳日期',
  amount: '金额',
  total_assets_wan_yuan: '总资产(万元)',
  net_assets_wan_yuan: '净资产(万元)',
  net_profit_wan_yuan: '净利润(万元)',
  main_business_revenue_wan_yuan: '主营业务收入(万元)',
  asset_liability_ratio_percent: '资产负债率(%)',
  total_revenue_wan_yuan: '总收入(万元)',
  total_cost_wan_yuan: '总成本(万元)',
  tax_amount_wan_yuan: '纳税额(万元)',
  employee_count: '员工人数',
};

/** String-only fallback for non-JSX contexts */
export function formatValue(v: unknown): string {
  if (v === null || v === undefined) return '-';
  if (typeof v === 'object') return JSON.stringify(v, null, 2);
  return String(v);
}
