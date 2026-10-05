import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { MP_BY_CODE, formatMoney } from "@/constants/marketplaces";
import { FinanceSummary } from "@/components/FinanceSummary";
import { FinanceCurrency } from "@/components/FinanceCurrency";
import { MissingFxAlert } from "@/components/FxStatus";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Download } from "lucide-react";

const iso = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const presets = [
  { id: "month", label: "Bu Ay", get: () => { const n = new Date(); return [new Date(n.getFullYear(), n.getMonth(), 1), n]; } },
  { id: "30-days", label: "Son 30 Gün", get: () => { const n = new Date(); const s = new Date(); s.setDate(s.getDate() - 30); return [s, n]; } },
  { id: "90-days", label: "Son 90 Gün", get: () => { const n = new Date(); const s = new Date(); s.setDate(s.getDate() - 90); return [s, n]; } },
  { id: "year", label: "Bu Yıl", get: () => { const n = new Date(); return [new Date(n.getFullYear(), 0, 1), n]; } },
];

export default function Report() {
  const { activeStoreId, activeMarketplace } = useStore();
  const [start, setStart] = useState(() => iso(new Date(new Date().getFullYear(), 0, 1)));
  const [end, setEnd] = useState(() => iso(new Date()));
  const [data, setData] = useState(null);
  const [currency, setCurrency] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => { setCurrency(""); }, [activeStoreId, activeMarketplace]);
  useEffect(() => {
    let current = true; setData(null); setError("");
    if (!activeStoreId) return;
    if (!start || !end || start > end) { setError("Geçerli bir tarih aralığı seçin."); setLoading(false); return; }
    setLoading(true);
    api.get("/dashboard/summary", { params: { store_id: activeStoreId, marketplace: activeMarketplace, start_date: start, end_date: end, ...(currency ? { currency } : {}) } })
      .then(r => { if (current) setData(r.data); }).catch(() => { if (current) setError("Rapor yüklenemedi."); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [activeStoreId, activeMarketplace, start, end, currency]);
  const exportCsv = () => {
    if (!data || data.incomplete_count) return;
    const rows = [["Pazar Yeri", "Para Birimi", "Gelir", "Gider", "Net Kar", "Kar/Zarar %"],
      ...data.by_marketplace.map(m => [m.marketplace, data.currency, m.revenue, m.expenses, m.net, m.revenue > 0 ? (m.net / m.revenue * 100).toFixed(2) : ""]),
      ["TOPLAM", data.currency, data.revenue, data.expenses, data.net_profit, data.margin], [], ["Gider / Geri Kazanim", "Para Birimi", "Tutar"],
      ...data.by_category.map(c => [c.category, data.currency, c.amount])];
    const csv = rows.map(r => r.map(v => `"${String(v).replaceAll('"', '""')}"`).join(",")).join("\r\n");
    const url = URL.createObjectURL(new Blob(["\ufeff", csv], { type: "text/csv;charset=utf-8;" }));
    const a = document.createElement("a"); a.href = url; a.download = `kar-zarar-${data.currency}-${start}-${end}.csv`; a.click(); URL.revokeObjectURL(url);
  };
  return <div className="space-y-6" data-testid="report-page">
    <div className="flex items-end justify-between flex-wrap gap-3"><h1 className="font-display text-3xl sm:text-4xl font-extrabold">Kâr-Zarar Raporu · USD</h1><Button onClick={exportCsv} disabled={!data || loading || data.incomplete_count > 0} variant="outline" className="bg-white" data-testid="export-csv-btn"><Download className="w-4 h-4 mr-2" />CSV İndir</Button></div>
    <div className="border-y border-slate-200 bg-white py-5 px-4 flex flex-wrap items-end gap-3">
      <div><Label htmlFor="report-start">Başlangıç</Label><Input id="report-start" type="date" value={start} onChange={e => setStart(e.target.value)} data-testid="start-date" className="mt-2 w-44" /></div>
      <div><Label htmlFor="report-end">Bitiş</Label><Input id="report-end" type="date" value={end} onChange={e => setEnd(e.target.value)} data-testid="end-date" className="mt-2 w-44" /></div>
      <div className="flex gap-2 flex-wrap">{presets.map(p => <Button key={p.id} variant="outline" size="sm" data-testid={`preset-${p.id}`} onClick={() => { const [s, e] = p.get(); setStart(iso(s)); setEnd(iso(e)); }}>{p.label}</Button>)}</div>
    </div>
    <FinanceCurrency summary={data} value={currency} onChange={setCurrency} prefix="report" />
    <MissingFxAlert summary={data} prefix="report" />
    {error && <p role="alert" data-testid="report-error" className="text-sm text-rose-600">{error}</p>}
    <FinanceSummary summary={data} currency={data?.currency} prefix="report" loading={loading} />
    <section className="space-y-4"><div className="flex flex-wrap justify-between gap-3"><h2 className="font-display text-lg font-bold">Pazar Yeri Karşılaştırması</h2><span className="text-sm text-slate-500" data-testid="report-margin">Kâr marjı: {data?.revenue > 0 ? `${data.margin.toFixed(2)}%` : "—"}</span></div>
      {!loading && !data?.by_marketplace.length && <p className="text-sm text-slate-500" data-testid="report-empty">Bu aralıkta veri yok.</p>}
      {data?.by_marketplace.map(m => <div key={m.marketplace} className="border-b border-slate-200 py-4 grid grid-cols-2 lg:grid-cols-5 gap-4" data-testid={`report-marketplace-${m.marketplace.toLowerCase()}`}>
        <strong className="text-sm col-span-2 lg:col-span-1">{MP_BY_CODE[m.marketplace]?.flag} {MP_BY_CODE[m.marketplace]?.name}</strong>
        {[ ["Gelir", m.revenue], ["Gider", m.expenses], ["Net Kâr / Zarar", m.net] ].map(([label, val], i) => <div key={label}><p className="text-xs text-slate-500">{label}</p><strong className={`font-mono-num text-sm break-all ${i === 2 ? val < 0 ? "text-rose-700" : "text-emerald-700" : ""}`} data-testid={`report-${m.marketplace.toLowerCase()}-${i}`}>{formatMoney(val, data.currency)}</strong></div>)}
        <div><p className="text-xs text-slate-500">Marj</p><strong className="font-mono-num text-sm" data-testid={`report-margin-${m.marketplace.toLowerCase()}`}>{m.revenue > 0 ? `${(m.net / m.revenue * 100).toFixed(2)}%` : "—"}</strong></div>
      </div>)}
    </section>
    <section className="space-y-4"><h2 className="font-display text-lg font-bold">Giderler ve Geri Kazanımlar</h2><div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-x-8 gap-y-4">{data?.by_category.map((c, i) => <div key={c.category} className="border-b border-slate-200 py-3 flex flex-wrap justify-between gap-3" data-testid={`report-category-${i}`}><span className="text-sm">{c.category}</span><strong className={`font-mono-num text-sm ${c.amount < 0 ? "text-emerald-700" : "text-rose-600"}`}>{formatMoney(c.amount, data.currency)}</strong></div>)}</div></section>
  </div>;
}