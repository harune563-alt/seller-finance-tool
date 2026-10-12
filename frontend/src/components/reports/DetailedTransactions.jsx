import { useEffect, useMemo, useState } from "react";
import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Download, FileSpreadsheet, RotateCcw, Search } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useCompanyResource } from "@/hooks/useCompanyResource";
import { SelectField, TextField, FormError } from "@/components/company/Fields";
import { formatUsd } from "@/components/FxStatus";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";

const EMPTY = { direction: "ALL", category: "ALL", fulfillment: "ALL", source: "ALL", cost_source: "ALL", profitability: "ALL", order_id: "", sku: "", asin: "", product_name: "", order_item_id: "", min_amount: "", max_amount: "", q: "" };
const SORTS = [["date", "Tarih"], ["amount", "Tutar"], ["cost", "Maliyet"], ["net_profit", "Net Kâr"], ["margin", "Marj"], ["store", "Mağaza"], ["marketplace", "Pazar Yeri"]];
const dash = v => (v == null || v === "" ? "—" : v);
const usd = v => (v == null ? "—" : formatUsd(v));
const pct = v => (v == null ? "—" : `${Number(v).toFixed(2)}%`);
const money = (v, c) => { if (v == null) return "—"; try { return new Intl.NumberFormat("tr-TR", { style: "currency", currency: c || "USD", minimumFractionDigits: 2 }).format(v); } catch { return `${v} ${c || ""}`; } };
const download = (blob, filename) => { const url = URL.createObjectURL(blob); const a = document.createElement("a"); a.href = url; a.download = filename; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); };

const COLUMNS = [
  ["Tarih", r => r.date, "date"], ["Mağaza", r => r.store_name, "store"], ["Pazar", r => dash(r.marketplace), "marketplace"],
  ["Tür", r => <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-semibold ${r.type === "income" ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`}>{r.type === "income" ? "Gelir" : "Gider"}</span>],
  ["Kategori", r => dash(r.category)], ["Kaynak", r => r.source_label], ["Fulfillment", r => dash(r.fulfillment)],
  ["Order ID", r => <span className="font-mono-num">{dash(r.order_id)}</span>], ["Order Item ID", r => <span className="font-mono-num">{dash(r.order_item_ids.join(", "))}</span>],
  ["SKU", r => dash(r.sku)], ["ASIN", r => dash(r.asin)], ["Ürün Adı", r => <span className="block max-w-[200px] truncate" title={r.product_name}>{dash(r.product_name)}</span>],
  ["Adet", r => dash(r.quantity)], ["Döviz", r => dash(r.currency)], ["Orijinal Tutar", r => money(r.original_amount, r.currency), null, true],
  ["USD Tutar", r => usd(r.amount_usd), "amount", true], ["Ürün Maliyeti", r => usd(r.product_cost), null, true], ["Kargo Maliyeti", r => usd(r.shipping_cost), null, true],
  ["FBA Ürün Maliyeti", r => usd(r.fba_product_cost), null, true], ["FBA Inbound", r => usd(r.fba_inbound_cost), null, true], ["Ekstra Maliyet", r => usd(r.extra_cost), null, true],
  ["Toplam Efektif Maliyet", r => usd(r.total_cost), "cost", true],
  ["Net Kâr", r => <span className={r.net_profit < 0 ? "text-rose-700 font-semibold" : r.net_profit > 0 ? "text-emerald-700 font-semibold" : ""}>{usd(r.net_profit)}</span>, "net_profit", true],
  ["Marj %", r => pct(r.margin), "margin", true], ["Açıklama", r => <span className="block max-w-[220px] truncate" title={r.description}>{dash(r.description)}</span>],
];

const Kpi = ({ label, value, testId, tone }) => <div className="bg-white border border-slate-200 rounded-lg p-3 min-w-0" data-testid={testId}><p className="text-xs text-slate-500">{label}</p><strong className={`block text-sm font-mono-num break-all mt-1 ${tone || ""}`}>{value}</strong></div>;
const tone = v => (v == null ? "" : v < 0 ? "text-rose-700" : "text-emerald-700");

const DetailView = ({ id, onClose }) => {
  const res = useCompanyResource(id ? `/reports/transactions/${id}/detail` : null);
  const record = res.data?.record || {};
  const row = res.data?.row;
  const fmt = v => (v == null || v === "" ? "—" : typeof v === "object" ? JSON.stringify(v) : String(v));
  return <Dialog open={!!id} onOpenChange={o => { if (!o) onClose(); }}>
    <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto" data-testid="dtr-detail-dialog">
      <DialogHeader><DialogTitle>Hareket Detayı</DialogTitle><DialogDescription>Yalnızca görüntüleme · Kayıt bu rapordan değiştirilemez.</DialogDescription></DialogHeader>
      <FormError error={res.error} id="dtr-detail-error" />
      {res.loading ? <p className="text-sm">Yükleniyor…</p> : row && <div className="space-y-4 text-sm">
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">{[["Gelir/Gider", row.type === "income" ? "Gelir" : "Gider"], ["USD Tutar", usd(row.amount_usd)], ["Toplam Efektif Maliyet", usd(row.total_cost)], ["Net Kâr", usd(row.net_profit)], ["Marj", pct(row.margin)], ["Kaynak", row.source_label], ["Maliyet Kaynağı", row.cost_source_label], ["Fulfillment", row.fulfillment], ["Kaynak Etiketleri", row.source_tags.join(", ") || "—"]].map(([k, v]) => <div key={k}><p className="text-xs text-slate-500">{k}</p><strong className="break-all">{v}</strong></div>)}</div>
        <div><h3 className="font-semibold mb-2">Kayıtlı Alanlar</h3><dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1" data-testid="dtr-detail-fields">{Object.entries(record).map(([k, v]) => <div key={k} className="flex gap-2 border-b border-slate-100 py-1 min-w-0"><dt className="text-xs text-slate-500 w-40 shrink-0 break-all">{k}</dt><dd className="text-xs font-mono-num break-all min-w-0">{fmt(v)}</dd></div>)}</dl></div>
        {res.data.order_items.length > 0 && <div><h3 className="font-semibold mb-2">Sipariş Kalemleri ({res.data.order_items.length})</h3><div className="space-y-2">{res.data.order_items.map(it => <div key={it.order_item_id} className="text-xs border rounded p-2 break-all">{it.order_item_id} · {it.sku || "—"} · {it.asin || "—"} · {it.product_name || "—"} · Adet {it.quantity ?? "—"} · {it.resolved_fulfillment || "—"}</div>)}</div></div>}
      </div>}
    </DialogContent>
  </Dialog>;
};

export const DetailedTransactions = ({ baseQuery }) => {
  const [filters, setFilters] = useState(EMPTY);
  const [debounced, setDebounced] = useState(EMPTY);
  const [sort, setSort] = useState({ key: "date", order: "desc" });
  const [page, setPage] = useState(1), [pageSize, setPageSize] = useState(25);
  const [detailId, setDetailId] = useState(null), [exporting, setExporting] = useState(""), [exportError, setExportError] = useState("");
  useEffect(() => { const t = setTimeout(() => setDebounced(filters), 350); return () => clearTimeout(t); }, [filters]);
  const filterQuery = useMemo(() => {
    if (!baseQuery) return "";
    const p = new URLSearchParams(baseQuery);
    Object.entries(debounced).forEach(([k, v]) => { const val = String(v).trim(); if (val && val !== "ALL") p.set(k, val); });
    p.set("sort", sort.key); p.set("order", sort.order);
    return p.toString();
  }, [baseQuery, debounced, sort]);
  useEffect(() => { setPage(1); }, [filterQuery, pageSize]);
  const res = useCompanyResource(filterQuery ? `/reports/transactions?${filterQuery}&page=${page}&page_size=${pageSize}` : null);
  const data = res.data, s = data?.summary, facets = data?.facets;
  useEffect(() => { if (data && data.page !== page) setPage(data.page); }, [data, page]);
  const set = (k, v) => setFilters(f => ({ ...f, [k]: v }));
  const toggleSort = key => setSort(cur => ({ key, order: cur.key === key && cur.order === "desc" ? "asc" : "desc" }));
  const exportFile = async format => {
    setExporting(format); setExportError("");
    try {
      const res2 = await api.get(`/reports/transactions/export?${filterQuery}&format=${format}`, { responseType: "blob" });
      download(res2.data, `detayli-hareket-raporu.${format}`); toast.success(`${format.toUpperCase()} hazır`);
    } catch (err) { let m = "Dışa aktarma başarısız."; try { const b = JSON.parse(await err.response.data.text()); if (typeof b.detail === "string") m = b.detail; } catch { /* keep default message */ } setExportError(m); }
    finally { setExporting(""); }
  };
  const opt = (all, list) => [{ value: "ALL", label: all }, ...list];
  return <section className="space-y-5 min-w-0" data-testid="detailed-transaction-report">
    <div className="flex flex-wrap justify-between items-end gap-3">
      <div><h2 className="font-display font-bold text-lg">Detaylı Hareket Raporu</h2><p className="text-xs text-slate-500 mt-1">Tarih, mağaza, pazar yeri ve döviz yukarıdaki filtrelerden gelir. Kâr hesabı Kâr-Zarar ile aynıdır.</p></div>
      <div className="flex flex-wrap gap-2">
        <Button variant="outline" onClick={() => exportFile("csv")} disabled={!data || !!exporting} data-testid="dtr-export-csv"><Download className="w-4 h-4 mr-2" />{exporting === "csv" ? "Hazırlanıyor…" : "CSV Dışa Aktar"}</Button>
        <Button onClick={() => exportFile("xlsx")} disabled={!data || !!exporting} className="bg-emerald-700 hover:bg-emerald-800 text-white" data-testid="dtr-export-xlsx"><FileSpreadsheet className="w-4 h-4 mr-2" />{exporting === "xlsx" ? "Hazırlanıyor…" : "XLSX Dışa Aktar"}</Button>
      </div>
    </div>

    <div className="border border-slate-200 rounded-xl bg-white p-4 space-y-4" data-testid="dtr-filters">
      <div className="relative"><Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" /><Input value={filters.q} onChange={e => set("q", e.target.value)} placeholder="Ara: Order ID, SKU, ASIN, ürün adı, açıklama, kategori" className="pl-9 bg-white" data-testid="dtr-search" /></div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <SelectField label="Hareket Yönü" id="dtr-direction" value={filters.direction} onChange={v => set("direction", v)} options={[{ value: "ALL", label: "Tümü" }, { value: "income", label: "Gelir" }, { value: "expense", label: "Gider" }]} />
        <SelectField label="Kategori" id="dtr-category" value={filters.category} onChange={v => set("category", v)} options={opt("Tüm Kategoriler", (facets?.categories || []).map(c => ({ value: c, label: c })))} />
        <SelectField label="Fulfillment" id="dtr-fulfillment" value={filters.fulfillment} onChange={v => set("fulfillment", v)} options={opt("Tümü", ["FBA", "FBM", "MIXED", "UNKNOWN"].map(c => ({ value: c, label: c })))} />
        <SelectField label="Kaynak" id="dtr-source" value={filters.source} onChange={v => set("source", v)} options={opt("Tüm Kaynaklar", facets?.sources || [])} />
        <SelectField label="Maliyet Kaynağı" id="dtr-cost-source" value={filters.cost_source} onChange={v => set("cost_source", v)} options={opt("Tümü", facets?.cost_sources || [])} />
        <SelectField label="Kârlılık" id="dtr-profitability" value={filters.profitability} onChange={v => set("profitability", v)} options={[{ value: "ALL", label: "Tümü" }, { value: "profitable", label: "Kârlı" }, { value: "loss", label: "Zararlı" }, { value: "break_even", label: "Başa baş" }]} />
        <TextField label="Min Tutar (USD)" id="dtr-min-amount" type="number" step="0.01" value={filters.min_amount} onChange={v => set("min_amount", v)} />
        <TextField label="Maks Tutar (USD)" id="dtr-max-amount" type="number" step="0.01" value={filters.max_amount} onChange={v => set("max_amount", v)} />
        <TextField label="Amazon Order ID" id="dtr-order-id" value={filters.order_id} onChange={v => set("order_id", v)} />
        <TextField label="SKU" id="dtr-sku" value={filters.sku} onChange={v => set("sku", v)} />
        <TextField label="ASIN" id="dtr-asin" value={filters.asin} onChange={v => set("asin", v)} />
        <TextField label="Ürün Adı" id="dtr-product-name" value={filters.product_name} onChange={v => set("product_name", v)} />
        <TextField label="Order Item ID" id="dtr-order-item-id" value={filters.order_item_id} onChange={v => set("order_item_id", v)} />
        <SelectField label="Sıralama" id="dtr-sort" value={sort.key} onChange={v => setSort(c => ({ ...c, key: v }))} options={SORTS.map(([value, label]) => ({ value, label }))} />
        <SelectField label="Yön" id="dtr-sort-order" value={sort.order} onChange={v => setSort(c => ({ ...c, order: v }))} options={[{ value: "desc", label: "Azalan" }, { value: "asc", label: "Artan" }]} />
        <div className="flex items-end"><Button variant="outline" className="w-full" onClick={() => { setFilters(EMPTY); setSort({ key: "date", order: "desc" }); }} data-testid="dtr-reset"><RotateCcw className="w-4 h-4 mr-2" />Filtreleri Temizle</Button></div>
      </div>
    </div>

    <FormError error={res.error || exportError} id="dtr-error" />
    {s?.incomplete_count > 0 && <p className="text-sm text-amber-800 bg-amber-50 rounded-md p-3" data-testid="dtr-incomplete">{s.incomplete_count} kayıtta kur verisi eksik; toplamlar kur tamamlanınca gösterilir.</p>}
    <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-8 gap-3" data-testid="dtr-summary">
      <Kpi label="Toplam Gelir" value={usd(s?.total_income)} testId="dtr-total-income" />
      <Kpi label="Toplam Gider" value={usd(s?.total_expense)} testId="dtr-total-expense" />
      <Kpi label="Toplam Efektif Maliyet" value={usd(s?.total_effective_cost)} testId="dtr-total-cost" />
      <Kpi label="Net Kâr" value={usd(s?.net_profit)} testId="dtr-net-profit" tone={tone(s?.net_profit)} />
      <Kpi label="Kâr Marjı" value={pct(s?.margin)} testId="dtr-margin" />
      <Kpi label="Kayıt Sayısı" value={s?.record_count ?? "—"} testId="dtr-record-count" />
      <Kpi label="FBA Kâr" value={usd(s?.fba_profit)} testId="dtr-fba-profit" tone={tone(s?.fba_profit)} />
      <Kpi label="FBM Kâr" value={usd(s?.fbm_profit)} testId="dtr-fbm-profit" tone={tone(s?.fbm_profit)} />
    </div>

    <div className="border border-slate-200 rounded-xl bg-white overflow-hidden">
      <div className="overflow-x-auto" data-testid="dtr-table-wrap">
        <table className="w-full text-sm whitespace-nowrap" data-testid="dtr-table">
          <thead className="bg-slate-50 text-xs text-slate-500"><tr>{COLUMNS.map(([label, , sortKey, right]) => <th key={label} className={`px-3 py-2.5 font-semibold ${right ? "text-right" : "text-left"}`}>
            {sortKey ? <button type="button" className="inline-flex items-center gap-1 hover:text-slate-900" onClick={() => toggleSort(sortKey)} data-testid={`dtr-sort-${sortKey}`}>{label}{sort.key === sortKey && (sort.order === "desc" ? <ArrowDown className="w-3 h-3" /> : <ArrowUp className="w-3 h-3" />)}</button> : label}
          </th>)}</tr></thead>
          <tbody>
            {res.loading ? <tr><td colSpan={COLUMNS.length} className="px-4 py-6 text-slate-500" data-testid="dtr-loading">Yükleniyor…</td></tr>
              : !data?.items.length ? <tr><td colSpan={COLUMNS.length} className="px-4 py-6 text-slate-500" data-testid="dtr-empty">Bu filtrelerle eşleşen hareket yok.</td></tr>
              : data.items.map(r => <tr key={r.id} onClick={() => setDetailId(r.id)} className="border-t border-slate-100 hover:bg-emerald-50/40 cursor-pointer" data-testid={`dtr-row-${r.id}`}>
                {COLUMNS.map(([label, render, , right]) => <td key={label} className={`px-3 py-2 ${right ? "text-right font-mono-num" : ""}`}>{render(r)}</td>)}
              </tr>)}
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap justify-between items-center gap-3 px-4 py-3 border-t border-slate-100" data-testid="dtr-pagination">
        <div className="flex items-center gap-2 text-xs text-slate-500"><span>Sayfa başına</span>{[25, 50, 100].map(n => <Button key={n} size="sm" variant={pageSize === n ? "default" : "outline"} onClick={() => setPageSize(n)} data-testid={`dtr-page-size-${n}`}>{n}</Button>)}</div>
        <span className="text-xs text-slate-500" data-testid="dtr-page-info">{data ? `${data.total} kayıt · Sayfa ${data.page} / ${data.total_pages}` : "—"}</span>
        <div className="flex gap-2"><Button variant="outline" size="sm" disabled={!data || page <= 1 || res.loading} onClick={() => setPage(p => p - 1)} data-testid="dtr-prev"><ChevronLeft className="w-4 h-4" /></Button><Button variant="outline" size="sm" disabled={!data || page >= data.total_pages || res.loading} onClick={() => setPage(p => p + 1)} data-testid="dtr-next"><ChevronRight className="w-4 h-4" /></Button></div>
      </div>
    </div>
    <DetailView id={detailId} onClose={() => setDetailId(null)} />
  </section>;
};
