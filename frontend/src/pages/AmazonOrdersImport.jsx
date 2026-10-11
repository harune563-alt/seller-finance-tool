import { useCallback, useEffect, useState } from "react";
import { FileSpreadsheet, UploadCloud } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const ACTION_LABELS = {
  attach: { text: "Attach", cls: "bg-emerald-100 text-emerald-800" },
  update: { text: "Update", cls: "bg-sky-100 text-sky-800" },
  enrich: { text: "Attach / Enrich", cls: "bg-indigo-100 text-indigo-800" },
  no_change: { text: "No Change", cls: "bg-slate-100 text-slate-600" },
  unmatched: { text: "Unmatched", cls: "bg-orange-100 text-orange-800" },
};

const FULFILLMENT_CLS = {
  FBA: "bg-blue-100 text-blue-800",
  FBM: "bg-violet-100 text-violet-800",
  MIXED: "bg-amber-100 text-amber-800",
  UNKNOWN: "bg-slate-100 text-slate-600",
};

const ActionBadge = ({ action }) => {
  const meta = ACTION_LABELS[action] || { text: action, cls: "bg-slate-100 text-slate-600" };
  return <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-semibold whitespace-nowrap ${meta.cls}`}>{meta.text}</span>;
};

const FulfillmentBadge = ({ value }) => {
  if (!value || value === "—") return <span className="text-slate-400">—</span>;
  const cls = FULFILLMENT_CLS[value] || "bg-slate-100 text-slate-600";
  return <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-semibold ${cls}`}>{value}</span>;
};

const PREVIEW_COLUMNS = [
  "Amazon Order ID", "Order Item ID", "SKU", "ASIN", "Quantity", "Product Name",
  "Fulfillment Channel Raw", "Resolved Fulfillment", "Order Status", "Item Status",
  "Existing Amazon Order Match", "Action",
];

export default function AmazonOrdersImport() {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState([]);
  const [unmatched, setUnmatched] = useState([]);

  const refreshLists = useCallback(() => {
    api.get("/amazon-orders/history")
      .then(({ data }) => setHistory(data || [])).catch(() => setHistory([]));
    api.get("/amazon-orders/unmatched")
      .then(({ data }) => setUnmatched(data?.items || [])).catch(() => setUnmatched([]));
  }, []);
  useEffect(() => { refreshLists(); }, [refreshLists]);

  const upload = async commit => {
    setError("");
    if (!file) { setError("Bir Amazon All Orders raporu seçin (.txt, .tsv, .csv)."); return; }
    if (!/\.(txt|tsv|csv)$/i.test(file.name) || file.size > 10 * 1024 * 1024) {
      setError("En fazla 10 MB büyüklüğünde .txt, .tsv veya .csv dosyası seçin."); return;
    }
    setBusy(true);
    try {
      const body = new FormData(); body.append("file", file);
      const { data } = await api.post("/amazon-orders/import", body, { params: { commit } });
      setResult(data);
      if (commit) {
        toast.success(`${data.new} yeni kalem, ${data.updated} güncelleme, ${data.enrichment_required || 0} finansal zenginleştirme · ${data.unmatched} eşleşmeyen`);
        refreshLists();
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Amazon All Orders raporu yüklenemedi.");
    } finally { setBusy(false); }
  };

  const applicable = result ? result.new + result.updated + (result.enrichment_required || 0) : 0;

  return <div className="space-y-6" data-testid="amazon-orders-page">
    <div>
      <h1 className="font-display text-3xl font-extrabold text-slate-900">Amazon Orders / Fulfillment Import</h1>
      <p className="text-sm text-slate-500 mt-1">
        Amazon All Orders raporu mevcut finansal siparişleri ürün bazında zenginleştirir ve
        FBA / FBM / MIXED sınıflandırması yapar. Bu içe aktarma yeni gelir veya gider OLUŞTURMAZ;
        Amazon Payments toplamlarını, SellerFlash maliyetlerini ve manuel maliyetleri değiştirmez.
      </p>
    </div>

    <section className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4" data-testid="ao-upload-card">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-64">
          <label className="text-xs font-semibold uppercase tracking-wider text-slate-600" htmlFor="ao-file">
            Amazon All Orders Raporu
          </label>
          <Input id="ao-file" type="file" accept=".txt,.tsv,.csv" disabled={busy} data-testid="ao-file-input" className="mt-2"
                 onChange={e => { setFile(e.target.files?.[0]); setResult(null); setError(""); }} />
        </div>
        <Button variant="outline" onClick={() => upload(false)} disabled={busy || !file} data-testid="ao-preview-button" className="bg-white">
          <UploadCloud className="w-4 h-4 mr-2" />{busy ? "İşleniyor…" : "Önizle"}
        </Button>
        {result && !result.committed && <Button onClick={() => upload(true)} disabled={busy} data-testid="ao-import-submit">
          {busy ? "Aktarılıyor…" : `${applicable} Değişikliği Uygula`}
        </Button>}
      </div>
      <p className="text-xs text-slate-500" data-testid="ao-note">
        Eşleştirme anahtarı: Amazon Order ID (pazar yeri gerekmez). Kalem kimliği: Amazon Order ID + Order Item ID.
        Aynı raporu tekrar yüklemek kalemleri çoğaltmaz; değişen durum/miktar/fulfillment bilgisi güncellenir.
      </p>
      {error && <p role="alert" data-testid="ao-error" className="text-sm text-rose-700">{error}</p>}

      {result && <div className="space-y-4" data-testid="ao-result">
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-10 gap-2 text-xs" data-testid="ao-counts">
          <div className="rounded-lg bg-slate-50 border px-2 py-1.5"><span className="block font-semibold text-slate-800" data-testid="ao-count-total">{result.total_rows}</span>Total Rows</div>
          <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-2 py-1.5"><span className="block font-semibold text-emerald-800" data-testid="ao-count-matched">{result.matched}</span>Matched</div>
          <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-2 py-1.5"><span className="block font-semibold text-emerald-800" data-testid="ao-count-new">{result.new}</span>New</div>
          <div className="rounded-lg bg-sky-50 border border-sky-200 px-2 py-1.5"><span className="block font-semibold text-sky-800" data-testid="ao-count-updated">{result.updated}</span>Updated</div>
          <div className="rounded-lg bg-indigo-50 border border-indigo-200 px-2 py-1.5"><span className="block font-semibold text-indigo-800" data-testid="ao-count-enrich">{result.enrichment_required || 0}</span>Enrichment Required</div>
          <div className="rounded-lg bg-slate-50 border px-2 py-1.5"><span className="block font-semibold text-slate-700" data-testid="ao-count-unchanged">{result.unchanged}</span>Unchanged</div>
          <div className="rounded-lg bg-orange-50 border border-orange-200 px-2 py-1.5"><span className="block font-semibold text-orange-800" data-testid="ao-count-unmatched">{result.unmatched}</span>Unmatched</div>
          <div className="rounded-lg bg-blue-50 border border-blue-200 px-2 py-1.5"><span className="block font-semibold text-blue-800" data-testid="ao-count-fba">{result.fba_items}</span>FBA Items</div>
          <div className="rounded-lg bg-violet-50 border border-violet-200 px-2 py-1.5"><span className="block font-semibold text-violet-800" data-testid="ao-count-fbm">{result.fbm_items}</span>FBM Items</div>
          <div className="rounded-lg bg-amber-50 border border-amber-200 px-2 py-1.5"><span className="block font-semibold text-amber-800" data-testid="ao-count-mixed">{result.mixed_orders}</span>Mixed Orders</div>
        </div>
        {result.committed && <p className="text-sm font-semibold text-emerald-700" data-testid="ao-import-success">
          İçe aktarma tamamlandı: {result.new} yeni · {result.updated} güncelleme · {result.enrichment_required || 0} finansal zenginleştirme · {result.unchanged} aynı · {result.unmatched} eşleşmeyen
        </p>}
        {result.issues.length > 0 && <div className="text-xs text-amber-800 bg-amber-50 rounded-md p-3 max-h-32 overflow-y-auto" data-testid="ao-issues">
          {result.issues.map((issue, i) => <p key={i}>Satır {issue.line}: {issue.reason}</p>)}
        </div>}
        <div className="overflow-x-auto border rounded-xl" data-testid="ao-preview-table">
          <table className="w-full text-xs min-w-[1400px]">
            <thead className="bg-slate-50 text-slate-600">
              <tr>{PREVIEW_COLUMNS.map(h =>
                <th key={h} className="text-left font-semibold px-3 py-2 whitespace-nowrap">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y">
              {result.preview.map((row, i) => <tr key={i} data-testid={`ao-preview-row-${i}`}>
                <td className="px-3 py-2 font-mono break-all" data-testid={`ao-row-order-${i}`}>{row.amazon_order_id}</td>
                <td className="px-3 py-2 font-mono break-all">{row.order_item_id}</td>
                <td className="px-3 py-2 font-mono break-all">{row.sku || "—"}</td>
                <td className="px-3 py-2 font-mono break-all">{row.asin || "—"}</td>
                <td className="px-3 py-2 font-mono-num">{row.quantity}</td>
                <td className="px-3 py-2 max-w-56 truncate" title={row.product_name}>{row.product_name || "—"}</td>
                <td className="px-3 py-2 whitespace-nowrap">{row.fulfillment_channel || "—"}</td>
                <td className="px-3 py-2" data-testid={`ao-row-fulfillment-${i}`}><FulfillmentBadge value={row.resolved_fulfillment} /></td>
                <td className="px-3 py-2 whitespace-nowrap">{row.order_status || "—"}</td>
                <td className="px-3 py-2 whitespace-nowrap">{row.item_status || "—"}</td>
                <td className="px-3 py-2" data-testid={`ao-row-match-${i}`}>{row.matched
                  ? <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-100 text-emerald-800">Matched</span>
                  : <span className="px-1.5 py-0.5 rounded-full text-[10px] font-semibold bg-orange-100 text-orange-800">Unmatched</span>}</td>
                <td className="px-3 py-2" data-testid={`ao-row-action-${i}`}><ActionBadge action={row.action} /></td>
              </tr>)}
            </tbody>
          </table>
          {result.total_rows > result.preview.length && <p className="text-xs text-slate-500 px-3 py-2">İlk {result.preview.length} satır gösteriliyor.</p>}
        </div>
      </div>}
    </section>

    {unmatched.length > 0 && <section className="bg-white rounded-2xl border border-orange-200 p-5" data-testid="ao-unmatched">
      <h2 className="font-display font-bold text-lg text-slate-900 mb-1">Eşleşmeyen All Orders Kalemleri ({unmatched.length})</h2>
      <p className="text-xs text-slate-500 mb-3">Bu Amazon Order ID değerlerine ait canonical finansal sipariş henüz yok. Finansal sipariş oluşturulmaz; Amazon Payments raporu yüklendikten sonra All Orders raporunu tekrar içe aktarın — kalemler otomatik eşleşir.</p>
      <div className="flex flex-wrap gap-2">
        {unmatched.slice(0, 30).map(u => <span key={u.id} className="px-2 py-1 rounded-lg bg-orange-50 border border-orange-200 text-xs font-mono" data-testid={`ao-unmatched-${u.amazon_order_id}-${u.order_item_id}`}>
          {u.amazon_order_id} · {u.order_item_id}
        </span>)}
        {unmatched.length > 30 && <span className="text-xs text-slate-500">+{unmatched.length - 30} kayıt</span>}
      </div>
    </section>}

    <section className="bg-white rounded-2xl border border-slate-200 p-5" data-testid="ao-history">
      <h2 className="font-display font-bold text-lg text-slate-900 mb-3 flex items-center gap-2"><FileSpreadsheet className="w-4 h-4" /> All Orders İçe Aktarma Geçmişi</h2>
      {history.length === 0 && <p className="text-sm text-slate-500" data-testid="ao-history-empty">Henüz All Orders içe aktarması yok.</p>}
      {history.length > 0 && <div className="overflow-x-auto">
        <table className="w-full text-xs min-w-[860px]">
          <thead className="bg-slate-50 text-slate-600"><tr>{["Dosya", "Yükleme", "Satır", "Matched", "New", "Updated", "Unchanged", "Unmatched", "FBA", "FBM", "Mixed", "Durum"].map(h => <th key={h} className="text-left font-semibold px-3 py-2 whitespace-nowrap">{h}</th>)}</tr></thead>
          <tbody className="divide-y">
            {history.map(b => <tr key={b.id} data-testid={`ao-history-${b.id}`}>
              <td className="px-3 py-2 break-all">{b.file_name || "—"}</td>
              <td className="px-3 py-2 whitespace-nowrap">{b.uploaded_at?.slice(0, 16).replace("T", " ")}</td>
              <td className="px-3 py-2 font-mono-num">{b.total_rows}</td>
              <td className="px-3 py-2 font-mono-num">{b.matched}</td>
              <td className="px-3 py-2 font-mono-num">{b.new}</td>
              <td className="px-3 py-2 font-mono-num">{b.updated}</td>
              <td className="px-3 py-2 font-mono-num">{b.unchanged}</td>
              <td className="px-3 py-2 font-mono-num">{b.unmatched}</td>
              <td className="px-3 py-2 font-mono-num">{b.fba_items}</td>
              <td className="px-3 py-2 font-mono-num">{b.fbm_items}</td>
              <td className="px-3 py-2 font-mono-num">{b.mixed_orders}</td>
              <td className="px-3 py-2"><span className="px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-semibold">{b.status}</span></td>
            </tr>)}
          </tbody>
        </table>
      </div>}
      <p className="text-[11px] text-slate-400 mt-3">İçe aktarma geçmişi yalnızca denetim amaçlıdır; finansal toplamları etkilemez.</p>
    </section>
  </div>;
}
