import { useEffect, useState } from "react";
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, CartesianGrid, Cell, ReferenceLine } from "recharts";
import api from "@/lib/api";
import { FinanceSummary } from "@/components/FinanceSummary";
import { MissingFxAlert, formatUsd } from "@/components/FxStatus";
import { DateRange, datePreset } from "./DateRange";
import { FormError } from "@/components/company/Fields";

export const PortfolioPanel = () => {
  const [[start, end], setDates] = useState(() => datePreset("month"));
  const [data, setData] = useState(null), [loading, setLoading] = useState(true), [error, setError] = useState("");
  useEffect(() => {
    let current = true; setData(null); setError("");
    if (!start || !end || start > end) { setError("Geçerli bir tarih aralığı seçin."); setLoading(false); return; }
    setLoading(true);
    api.get("/portfolio/summary", { params: { start_date: start, end_date: end } }).then(r => { if (current) setData(r.data); }).catch(() => { if (current) setError("Mağaza karşılaştırması yüklenemedi."); }).finally(() => { if (current) setLoading(false); });
    return () => { current = false; };
  }, [start, end]);
  const chartData = (data?.by_store || []).filter(s => s.net_profit != null);
  return <section className="space-y-5 border-y border-slate-200 py-6" data-testid="portfolio-panel"><div><p className="text-xs font-semibold uppercase text-emerald-700">Tüm Mağazalar · USD</p><h2 className="font-display text-lg font-bold mt-1">Mağazaların Kârlılık Karşılaştırması</h2></div>
    <DateRange start={start} end={end} onChange={(s, e) => setDates([s, e])} prefix="portfolio" /><FormError error={error} id="portfolio-error" /><MissingFxAlert summary={data} prefix="portfolio" />
    <FinanceSummary summary={data} loading={loading} prefix="portfolio" />
    {!loading && !error && !data?.incomplete_count && <div className="min-w-0" data-testid="portfolio-chart" style={{ height: Math.max(240, Math.min(560, chartData.length * 55 + 50)) }}>
      {chartData.length ? <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{ width: 320, height: 240 }}><BarChart data={chartData} layout="vertical" margin={{ top: 10, right: 25, bottom: 10, left: 0 }}><CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" horizontal={false} /><XAxis type="number" fontSize={11} tickFormatter={v => new Intl.NumberFormat("tr-TR", { notation: "compact" }).format(v)} /><YAxis type="category" dataKey="store_name" width={95} fontSize={11} tickFormatter={v => v.length > 13 ? v.slice(0, 13) + "…" : v} /><Tooltip formatter={value => [formatUsd(value), "Net Kâr / Zarar"]} /><ReferenceLine x={0} stroke="#94a3b8" /><Bar dataKey="net_profit" name="Net Kâr / Zarar" barSize={26} radius={[0, 4, 4, 0]}>{chartData.map(s => <Cell key={s.store_id} fill={s.net_profit < 0 ? "#e11d48" : "#059669"} />)}</Bar></BarChart></ResponsiveContainer> : <p className="text-sm text-slate-500" data-testid="portfolio-empty">Mağaza kaydı yok.</p>}
    </div>}
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-x-6 gap-y-3">{data?.by_store.map(s => <div key={s.store_id} className="flex flex-wrap justify-between gap-2 text-sm border-b border-slate-200 pb-3" data-testid={`portfolio-store-${s.store_id}`}><span className="break-words">{s.store_name}</span><strong className={`font-mono-num ${s.net_profit < 0 ? "text-rose-600" : "text-emerald-700"}`} data-testid={`portfolio-profit-${s.store_id}`}>{formatUsd(s.net_profit)}</strong></div>)}</div>
  </section>;
};