import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { MP_BY_CODE, formatMoney } from "@/constants/marketplaces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { FileBarChart2, Download } from "lucide-react";

const presets = [
  { label: "Bu Ay", get: () => { const n = new Date(); return [new Date(n.getFullYear(), n.getMonth(), 1), n]; } },
  { label: "Son 30 Gün", get: () => { const n = new Date(); const s = new Date(); s.setDate(s.getDate() - 30); return [s, n]; } },
  { label: "Son 90 Gün", get: () => { const n = new Date(); const s = new Date(); s.setDate(s.getDate() - 90); return [s, n]; } },
  { label: "Bu Yıl", get: () => { const n = new Date(); return [new Date(n.getFullYear(), 0, 1), n]; } },
];

const iso = (d) => d.toISOString().slice(0, 10);

export default function Report() {
  const { activeStore, activeStoreId } = useStore();
  const [start, setStart] = useState(() => iso(new Date(new Date().getFullYear(), 0, 1)));
  const [end, setEnd] = useState(() => iso(new Date()));
  const [data, setData] = useState(null);

  const fetchReport = async () => {
    if (!activeStoreId) return;
    const { data } = await api.get("/dashboard/summary", {
      params: { store_id: activeStoreId, start_date: start, end_date: end },
    });
    setData(data);
  };

  useEffect(() => { fetchReport(); /* eslint-disable-next-line */ }, [activeStoreId, start, end]);

  const applyPreset = (p) => {
    const [s, e] = p.get();
    setStart(iso(s)); setEnd(iso(e));
  };

  const currency = activeStore?.default_currency || "USD";
  const marketplaceRows = (data?.by_marketplace || []).sort((a, b) => b.revenue - a.revenue);

  const exportCsv = () => {
    const rows = [
      ["Pazar Yeri", "Gelir", "Gider", "Net Kar"],
      ...marketplaceRows.map((m) => [m.marketplace, m.revenue, m.expenses, m.net]),
      ["TOPLAM", data?.revenue || 0, data?.expenses || 0, data?.net_profit || 0],
    ];
    const csv = rows.map((r) => r.join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `kar-zarar-${start}-${end}.csv`; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6" data-testid="report-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="font-display text-3xl font-extrabold text-slate-900">Kar-Zarar Raporu</h1>
          <p className="text-sm text-slate-500 mt-1">Belirlenen tarih aralığında konsolide P&L raporu.</p>
        </div>
        <Button onClick={exportCsv} variant="outline" className="rounded-xl bg-white" data-testid="export-csv-btn">
          <Download className="w-4 h-4 mr-2" /> CSV İndir
        </Button>
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl p-5 flex flex-wrap items-end gap-3">
        <div>
          <Label className="text-xs font-semibold uppercase tracking-wider text-slate-600">Başlangıç</Label>
          <Input type="date" value={start} onChange={(e) => setStart(e.target.value)}
                 data-testid="start-date" className="mt-1 w-44" />
        </div>
        <div>
          <Label className="text-xs font-semibold uppercase tracking-wider text-slate-600">Bitiş</Label>
          <Input type="date" value={end} onChange={(e) => setEnd(e.target.value)}
                 data-testid="end-date" className="mt-1 w-44" />
        </div>
        <div className="flex gap-2 flex-wrap">
          {presets.map((p) => (
            <Button key={p.label} variant="outline" size="sm" onClick={() => applyPreset(p)}
                    data-testid={`preset-${p.label}`}
                    className="rounded-full bg-white border-slate-200 hover:bg-slate-900 hover:text-white hover:border-slate-900">
              {p.label}
            </Button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="kpi-card">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">Brüt Gelir</div>
          <div className="mt-2 font-mono-num text-2xl font-extrabold text-emerald-600">{formatMoney(data?.revenue || 0, currency)}</div>
        </div>
        <div className="kpi-card">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">Toplam Gider</div>
          <div className="mt-2 font-mono-num text-2xl font-extrabold text-rose-600">{formatMoney(data?.expenses || 0, currency)}</div>
        </div>
        <div className="kpi-card">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">Net Kar</div>
          <div className="mt-2 font-mono-num text-2xl font-extrabold text-indigo-600">{formatMoney(data?.net_profit || 0, currency)}</div>
        </div>
        <div className="kpi-card">
          <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">Kar Marjı</div>
          <div className="mt-2 font-mono-num text-2xl font-extrabold text-amber-600">{(data?.margin || 0).toFixed(1)}%</div>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex items-center gap-2">
          <FileBarChart2 className="w-5 h-5 text-slate-500" />
          <h2 className="font-display text-lg font-bold text-slate-900">Pazar Yeri Bazlı Karşılaştırma</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
              <tr>
                <th className="text-left px-6 py-3 font-semibold">Pazar</th>
                <th className="text-right px-4 py-3 font-semibold">Gelir</th>
                <th className="text-right px-4 py-3 font-semibold">Gider</th>
                <th className="text-right px-6 py-3 font-semibold">Net Kar</th>
                <th className="text-right px-6 py-3 font-semibold">Marj</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {marketplaceRows.length === 0 && (
                <tr><td colSpan={5} className="px-6 py-8 text-center text-slate-400">Bu aralıkta veri yok</td></tr>
              )}
              {marketplaceRows.map((m) => {
                const mp = MP_BY_CODE[m.marketplace];
                const margin = m.revenue > 0 ? (m.net / m.revenue * 100) : 0;
                return (
                  <tr key={m.marketplace} className="hover:bg-slate-50">
                    <td className="px-6 py-3 font-semibold text-slate-800">{mp?.flag} {mp?.name || m.marketplace}</td>
                    <td className="px-4 py-3 text-right font-mono-num text-emerald-600 font-semibold">{formatMoney(m.revenue, mp?.currency || currency)}</td>
                    <td className="px-4 py-3 text-right font-mono-num text-rose-600 font-semibold">{formatMoney(m.expenses, mp?.currency || currency)}</td>
                    <td className="px-6 py-3 text-right font-mono-num text-indigo-600 font-bold">{formatMoney(m.net, mp?.currency || currency)}</td>
                    <td className="px-6 py-3 text-right font-mono-num text-amber-600 font-semibold">{margin.toFixed(1)}%</td>
                  </tr>
                );
              })}
              {marketplaceRows.length > 0 && (
                <tr className="bg-slate-900 text-white">
                  <td className="px-6 py-3 font-bold">TOPLAM</td>
                  <td className="px-4 py-3 text-right font-mono-num font-bold">{formatMoney(data?.revenue || 0, currency)}</td>
                  <td className="px-4 py-3 text-right font-mono-num font-bold">{formatMoney(data?.expenses || 0, currency)}</td>
                  <td className="px-6 py-3 text-right font-mono-num font-bold">{formatMoney(data?.net_profit || 0, currency)}</td>
                  <td className="px-6 py-3 text-right font-mono-num font-bold">{(data?.margin || 0).toFixed(1)}%</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      <div className="bg-white border border-slate-200 rounded-2xl p-6">
        <h2 className="font-display text-lg font-bold text-slate-900 mb-4">Gider Kategorileri</h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {(data?.by_category || []).length === 0 && (
            <div className="col-span-full text-sm text-slate-400">Veri yok</div>
          )}
          {(data?.by_category || []).sort((a,b) => b.amount - a.amount).map((c) => (
            <div key={c.category} className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 flex items-center justify-between">
              <span className="text-sm font-medium text-slate-700">{c.category}</span>
              <span className="font-mono-num font-bold text-rose-600">{formatMoney(c.amount, currency)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
