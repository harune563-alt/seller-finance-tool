import { useMemo } from "react";
import { formatUsd } from "@/components/FxStatus";
import { pct, roasFmt, num } from "./ppcFormat";

const group = (rows, keyOf) => {
  const map = {};
  for (const r of rows) {
    const k = keyOf(r) || "—";
    const b = map[k] || (map[k] = { key: k, spend: 0, sales: 0, clicks: 0, impressions: 0, orders: 0, skus: new Set() });
    b.spend += r.ad_spend_usd || 0; b.sales += r.ppc_sales_usd || 0;
    b.clicks += r.clicks || 0; b.impressions += r.impressions || 0; b.orders += r.orders || 0;
    if (r.sku) b.skus.add(r.sku);
  }
  return Object.values(map).sort((a, b) => b.spend - a.spend);
};

const Table = ({ title, label, items, testId }) => (
  <div className="rounded-2xl bg-white border border-slate-200 overflow-hidden" data-testid={testId}>
    <div className="px-5 py-4 border-b border-slate-100"><h2 className="font-display text-lg font-bold text-slate-900">{title}</h2></div>
    <div className="overflow-x-auto">
      <table className="w-full text-sm min-w-[800px]">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wider text-slate-500 border-b border-slate-100">
            <th className="px-5 py-3">{label}</th><th className="px-3 py-3 text-right">Dağıtılan Harcama</th><th className="px-3 py-3 text-right">PPC Satış</th>
            <th className="px-3 py-3 text-right">Tık.</th><th className="px-3 py-3 text-right">Gös.</th><th className="px-3 py-3 text-right">Sip.</th>
            <th className="px-3 py-3 text-right">CTR</th><th className="px-3 py-3 text-right">ACoS</th><th className="px-3 py-3 text-right">ROAS</th>
          </tr>
        </thead>
        <tbody>
          {items.length === 0 && <tr><td colSpan={9} className="px-5 py-6 text-center text-slate-400">Veri yok</td></tr>}
          {items.map(b => (
            <tr key={b.key} className="border-b border-slate-50" data-testid={`${testId}-row-${b.key}`}>
              <td className="px-5 py-2.5 font-medium text-slate-800">{b.key}{b.skus.size > 0 && <span className="block text-xs text-slate-400 font-mono">{[...b.skus].join(", ")}</span>}</td>
              <td className="px-3 py-2.5 text-right font-mono-num text-amber-700">{formatUsd(b.spend)}</td>
              <td className="px-3 py-2.5 text-right font-mono-num text-emerald-700">{formatUsd(b.sales)}</td>
              <td className="px-3 py-2.5 text-right font-mono-num">{num(b.clicks)}</td>
              <td className="px-3 py-2.5 text-right font-mono-num">{num(b.impressions)}</td>
              <td className="px-3 py-2.5 text-right font-mono-num">{num(b.orders)}</td>
              <td className="px-3 py-2.5 text-right font-mono-num">{pct(b.impressions ? b.clicks / b.impressions * 100 : null)}</td>
              <td className="px-3 py-2.5 text-right font-mono-num">{pct(b.sales ? b.spend / b.sales * 100 : null)}</td>
              <td className="px-3 py-2.5 text-right font-mono-num">{roasFmt(b.spend ? b.sales / b.spend : null)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  </div>
);

export const PpcBreakdown = ({ rows }) => {
  const byAsin = useMemo(() => group(rows, r => r.asin), [rows]);
  const byCampaign = useMemo(() => group(rows, r => r.campaign), [rows]);
  return (
    <div className="space-y-6" data-testid="ppc-breakdown">
      <Table title="ASIN Dağılımı" label="ASIN" items={byAsin} testId="ppc-by-asin" />
      <Table title="Kampanya Dağılımı" label="Kampanya" items={byCampaign} testId="ppc-by-campaign" />
    </div>
  );
};
