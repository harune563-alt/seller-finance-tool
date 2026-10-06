import { useMemo, useState } from "react";
import { Download, FileSpreadsheet } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { useCompanyResource } from "@/hooks/useCompanyResource";
import { FinanceSummary } from "@/components/FinanceSummary";
import { FinanceCurrency } from "@/components/FinanceCurrency";
import { MissingFxAlert, formatUsd } from "@/components/FxStatus";
import { SelectField, FormError } from "@/components/company/Fields";
import { DateRange, datePreset } from "@/components/reports/DateRange";
import { DetailedOrders } from "@/components/reports/DetailedOrders";
import { MarketplaceReport } from "@/components/reports/MarketplaceReport";
import { Button } from "@/components/ui/button";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { MP_BY_CODE } from "@/constants/marketplaces";

const download = (content, filename) => { const url = URL.createObjectURL(content); const a = document.createElement("a"); a.href = url; a.download = filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); };
export default function Report() {
  const { stores } = useStore();
  const [[start, end], setDates] = useState(() => datePreset("year"));
  const [storeId, setStoreId] = useState("ALL"), [marketplace, setMarketplace] = useState("ALL"), [currency, setCurrency] = useState("ALL");
  const [downloading, setDownloading] = useState(false), [downloadError, setDownloadError] = useState("");
  const invalid = !start || !end || start > end;
  const query = useMemo(() => invalid ? "" : new URLSearchParams({ start_date: start, end_date: end, store_id: storeId, marketplace, currency }).toString(), [start, end, storeId, marketplace, currency, invalid]);
  const report = useCompanyResource(query ? `/portfolio/summary?${query}` : null);
  const data = report.data;
  const markets = [...new Set(stores.filter(s => storeId === "ALL" || s.id === storeId).flatMap(s => s.marketplaces))];
  const excel = async () => {
    setDownloading(true); setDownloadError("");
    try { const res = await api.get(`/reports/excel?${query}`, { responseType: "blob" }); download(res.data, `kar-zarar-${start}-${end}.xlsx`); toast.success("Excel raporu hazır"); }
    catch (err) { let message = "Excel raporu hazırlanamadı."; try { const body = JSON.parse(await err.response.data.text()); if (typeof body.detail === "string") message = body.detail; } catch {} setDownloadError(message); }
    finally { setDownloading(false); }
  };
  const csv = () => {
    if (!data || data.incomplete_count) return;
    const rows = [["Mağaza", "Döviz", "Gelir", "Gider", "Net Kâr", "Marj %"], ...data.by_store.map(s => [s.store_name, "USD", s.revenue, s.expenses, s.net_profit, s.margin]), ["TOPLAM", "USD", data.revenue, data.expenses, data.net_profit, data.margin]];
    const cell = v => { let text = String(v ?? ""); if (typeof v === "string" && /^[=+@-]/.test(text.trimStart())) text = "'" + text; return `"${text.replaceAll('"', '""')}"`; };
    download(new Blob(["\ufeff", rows.map(r => r.map(cell).join(",")).join("\r\n")], { type: "text/csv;charset=utf-8;" }), `kar-zarar-${start}-${end}.csv`);
  };
  const disabled = !data || report.loading || data.incomplete_count > 0 || invalid;
  return <div className="space-y-6" data-testid="report-page">
    <div className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs text-emerald-700 font-semibold mb-2">MAĞAZA & SİPARİŞ ANALİZİ</p><h1 className="font-display text-3xl sm:text-4xl font-extrabold">Kâr-Zarar Raporu</h1></div><div className="flex flex-wrap gap-2"><Button onClick={csv} disabled={disabled} variant="outline" data-testid="export-csv-btn"><Download className="w-4 h-4 mr-2" />Özet CSV</Button><Button onClick={excel} disabled={disabled || downloading} className="bg-emerald-700 hover:bg-emerald-800 text-white" data-testid="download-excel-report-button"><FileSpreadsheet className="w-4 h-4 mr-2" />{downloading ? "Hazırlanıyor…" : "Ayrıntılı Excel İndir"}</Button></div></div>
    <div className="border-y border-slate-200 bg-white p-4 sm:p-5 space-y-5"><DateRange start={start} end={end} onChange={(s, e) => setDates([s, e])} prefix="report" /><div className="grid grid-cols-1 sm:grid-cols-2 gap-4"><SelectField label="Mağaza" id="report-store" value={storeId} onChange={v => { setStoreId(v); setMarketplace("ALL"); setCurrency("ALL"); }} options={[{ value: "ALL", label: "Tüm Mağazalar" }, ...stores.map(s => ({ value: s.id, label: s.name }))]} /><SelectField label="Pazar Yeri" id="report-marketplace" value={marketplace} onChange={v => { setMarketplace(v); setCurrency("ALL"); }} options={[{ value: "ALL", label: "Tüm Pazarlar" }, ...markets.map(c => ({ value: c, label: `${MP_BY_CODE[c]?.flag || ""} ${MP_BY_CODE[c]?.name || c}` }))]} /></div></div>
    <FinanceCurrency summary={data} value={currency} onChange={setCurrency} prefix="report" /><FormError error={invalid ? "Geçerli tarih aralığı seçin." : report.error || downloadError} id="report-error" /><MissingFxAlert summary={data} prefix="report" />
    <FinanceSummary summary={data} prefix="report" loading={report.loading} />
    <div className="text-xs text-slate-500 flex flex-wrap justify-between gap-2" data-testid="report-scope"><span>Rapor ve sipariş özetleri seçili tarih aralığındaki hareketleri içerir.</span><span>{data?.order_count ?? "—"} sipariş/kayıt · {data?.transaction_count ?? "—"} hareket</span></div>
    <Tabs defaultValue="summary"><TabsList data-testid="report-tabs"><TabsTrigger value="summary" data-testid="report-summary-tab">Özet</TabsTrigger><TabsTrigger value="orders" data-testid="report-orders-tab">Sipariş Ayrıntıları</TabsTrigger></TabsList>
      <TabsContent value="summary" className="space-y-7 pt-4"><section><h2 className="font-display text-lg font-bold mb-4">Mağaza Karşılaştırması · USD</h2><div className="space-y-3">{data?.by_store.map(s => <div key={s.store_id} className="grid grid-cols-2 lg:grid-cols-5 gap-4 border-b border-slate-200 py-4" data-testid={`report-store-row-${s.store_id}`}><strong className="text-sm break-words col-span-2 lg:col-span-1">{s.store_name}</strong>{[["Gelir", s.revenue], ["Gider", s.expenses], ["Net Kâr/Zarar", s.net_profit]].map(([label, value], i) => <div key={label}><p className="text-xs text-slate-500">{label}</p><strong className={`text-sm font-mono-num break-all ${i === 2 ? value < 0 ? "text-rose-700" : "text-emerald-700" : ""}`} data-testid={`report-store-${s.store_id}-${i}`}>{formatUsd(value)}</strong></div>)}<div><p className="text-xs text-slate-500">Marj</p><strong className="text-sm">{s.revenue > 0 && s.margin != null ? `${s.margin.toFixed(2)}%` : "—"}</strong></div></div>)}</div></section>
        <MarketplaceReport data={data} />
        <section><h2 className="font-display text-lg font-bold mb-4">Giderler ve Geri Kazanımlar</h2><div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">{data?.by_category.map((c, i) => <div key={c.category} className="flex flex-wrap justify-between gap-2 border-b border-slate-200 pb-3 text-sm" data-testid={`report-category-${i}`}><span>{c.category}</span><strong className={c.amount < 0 ? "text-emerald-700" : "text-rose-600"}>{formatUsd(c.amount)}</strong></div>)}</div></section>
      </TabsContent><TabsContent value="orders" className="pt-4"><DetailedOrders query={query} /></TabsContent>
    </Tabs>
  </div>;
}