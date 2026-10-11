import { useEffect, useState } from "react";
import { FileSpreadsheet, UploadCloud } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { MP_BY_CODE } from "@/constants/marketplaces";
import { formatUsd } from "@/components/FxStatus";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

const STATUS_LABELS = {
  new: { text: "Yeni", cls: "bg-emerald-100 text-emerald-800" },
  restore_missing_record: { text: "Eksik kayıt geri yüklenecek", cls: "bg-sky-100 text-sky-800" },
  partial_cost_completion: { text: "Kısmi maliyet tamamlama", cls: "bg-teal-100 text-teal-800" },
  existing_unchanged: { text: "Mevcut · değişmedi", cls: "bg-slate-100 text-slate-600" },
  updated: { text: "Güncellenecek", cls: "bg-sky-100 text-sky-800" },
  manual_override_preserved: { text: "Manuel maliyet korunuyor", cls: "bg-violet-100 text-violet-800" },
  amazon_order_not_found: { text: "Amazon siparişi bulunamadı", cls: "bg-orange-100 text-orange-800" },
  no_cost_data: { text: "Maliyet verisi yok", cls: "bg-amber-100 text-amber-800" },
  fba_order_fifo_cost: { text: "FBA · FIFO maliyeti", cls: "bg-blue-100 text-blue-800" },
};
const StatusBadge = ({ status }) => {
  const meta = STATUS_LABELS[status] || { text: status, cls: "bg-slate-100 text-slate-600" };
  return <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-semibold whitespace-nowrap ${meta.cls}`}>{meta.text}</span>;
};

export default function SellerFlashImport() {
  const { activeStore, activeStoreId } = useStore();
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState([]);
  const [unmatched, setUnmatched] = useState([]);

  const refreshLists = () => {
    if (!activeStoreId) return;
    api.get("/sellerflash/history", { params: { store_id: activeStoreId } })
      .then(({ data }) => setHistory(data || [])).catch(() => setHistory([]));
    api.get("/sellerflash/unmatched", { params: { store_id: activeStoreId } })
      .then(({ data }) => setUnmatched(data?.items || [])).catch(() => setUnmatched([]));
  };
  useEffect(() => { setResult(null); setFile(null); refreshLists(); }, [activeStoreId]);

  const upload = async commit => {
    setError("");
    if (!file) { setError("Bir SellerFlash raporu seçin (.csv, .xlsx, .xls)."); return; }
    if (!/\.(csv|xlsx|xls)$/i.test(file.name) || file.size > 10 * 1024 * 1024) {
      setError("En fazla 10 MB büyüklüğünde .csv, .xlsx veya .xls dosyası seçin."); return;
    }
    setBusy(true);
    try {
      const body = new FormData(); body.append("file", file);
      const { data } = await api.post("/sellerflash/import", body, { params: { store_id: activeStoreId, commit } });
      setResult(data);
      if (commit) {
        toast.success(`${data.new} yeni, ${data.updated} güncelleme, ${data.partial_completion} kısmi tamamlama · ${data.applied_costs} siparişe maliyet uygulandı`);
        refreshLists();
      }
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "SellerFlash raporu yüklenemedi.");
    } finally { setBusy(false); }
  };

  const applicable = result ? result.actionable : 0;

  if (!activeStoreId) {
    return <div className="text-sm text-slate-500" data-testid="sf-no-store">SellerFlash içe aktarma için önce bir mağaza seçin veya oluşturun.</div>;
  }

  return <div className="space-y-6" data-testid="sellerflash-page">
    <div>
      <h1 className="font-display text-3xl font-extrabold text-slate-900">SellerFlash Maliyet İçe Aktarma</h1>
      <p className="text-sm text-slate-500 mt-1">
        SellerFlash Profit Report ile ürün ve kargo maliyetlerini mevcut Amazon siparişlerine bağlayın.
        Maliyetler ayrı finansal işlem oluşturmaz; yalnızca eşleşen siparişin kâr hesabına işlenir.
        Manuel girilmiş maliyetler asla ezilmez.
      </p>
    </div>

    <section className="bg-white rounded-2xl border border-slate-200 p-5 space-y-4" data-testid="sf-upload-card">
      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-64">
          <label className="text-xs font-semibold uppercase tracking-wider text-slate-600" htmlFor="sf-file">
            SellerFlash Raporu ({activeStore?.name})
          </label>
          <Input id="sf-file" type="file" accept=".csv,.xlsx,.xls" disabled={busy} data-testid="sf-file-input" className="mt-2"
                 onChange={e => { setFile(e.target.files?.[0]); setResult(null); setError(""); }} />
        </div>
        <Button variant="outline" onClick={() => upload(false)} disabled={busy || !file} data-testid="sf-preview-button" className="bg-white">
          <UploadCloud className="w-4 h-4 mr-2" />{busy ? "İşleniyor…" : "Önizle"}
        </Button>
        {result && !result.committed && <Button onClick={() => upload(true)} disabled={busy || applicable <= 0} data-testid="sf-import-submit">
          {busy ? "Aktarılıyor…" : `${applicable} Kaydı Uygula`}
        </Button>}
      </div>
      <p className="text-xs text-slate-500" data-testid="sf-note">
        Eşleştirme anahtarı: yalnızca Seller Order Id = Amazon Order ID (pazar yeri engellemez). SellerFlash maliyetleri her zaman USD'dir, kur dönüşümü yapılmaz. Ürün ve kargo maliyeti bağımsızdır; boş hücre mevcut değeri korur. Aynı raporu tekrar yüklemek maliyetleri iki kez eklemez;
        değişen maliyetler güncellenir ve denetim geçmişine yazılır. SellerFlash Profit/Profit Rate yalnızca referanstır.
      </p>
      {error && <p role="alert" data-testid="sf-error" className="text-sm text-rose-700">{error}</p>}

      {result && <div className="space-y-4" data-testid="sf-result">
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 text-xs" data-testid="sf-counts">
          <div className="rounded-lg bg-slate-50 border px-2 py-1.5"><span className="block font-semibold text-slate-800" data-testid="sf-count-total">{result.total_rows}</span>Toplam satır</div>
          <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-2 py-1.5"><span className="block font-semibold text-emerald-800" data-testid="sf-count-matched">{result.matched}</span>Eşleşti</div>
          <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-2 py-1.5"><span className="block font-semibold text-emerald-800" data-testid="sf-count-new">{result.new}</span>Yeni</div>
          <div className="rounded-lg bg-sky-50 border border-sky-200 px-2 py-1.5"><span className="block font-semibold text-sky-800" data-testid="sf-count-updated">{result.updated + result.partial_completion + result.restored}</span>Güncelleme / Tamamlama</div>
          <div className="rounded-lg bg-slate-50 border px-2 py-1.5"><span className="block font-semibold text-slate-700" data-testid="sf-count-unchanged">{result.unchanged}</span>Değişmemiş</div>
          <div className="rounded-lg bg-orange-50 border border-orange-200 px-2 py-1.5"><span className="block font-semibold text-orange-800" data-testid="sf-count-unmatched">{result.unmatched}</span>Eşleşmedi</div>
          <div className="rounded-lg bg-rose-50 border border-rose-200 px-2 py-1.5"><span className="block font-semibold text-rose-800" data-testid="sf-count-conflicts">{result.manual_preserved}</span>Manuel korunan</div>
          <div className="rounded-lg bg-amber-50 border border-amber-200 px-2 py-1.5"><span className="block font-semibold text-amber-800" data-testid="sf-count-missing">{result.missing_product_cost + result.missing_shipping_cost}</span>Eksik maliyet</div>
        </div>
        {result.committed && <p className="text-sm font-semibold text-emerald-700" data-testid="sf-import-success">
          İçe aktarma tamamlandı: {result.new} yeni · {result.updated} güncelleme · {result.partial_completion} kısmi tamamlama · {result.restored} geri yükleme · {result.applied_costs} siparişe maliyet uygulandı
        </p>}
        {result.issues.length > 0 && <div className="text-xs text-amber-800 bg-amber-50 rounded-md p-3 max-h-32 overflow-y-auto" data-testid="sf-issues">
          {result.issues.map((issue, i) => <p key={i}>Satır {issue.line}: {issue.reason}</p>)}
        </div>}
        <div className="overflow-x-auto border rounded-xl" data-testid="sf-preview-table">
          <table className="w-full text-xs min-w-[1100px]">
            <thead className="bg-slate-50 text-slate-600">
              <tr>{["Seller Order ID", "Amazon Eşleşme", "Mevcut Ürün Maliyeti", "Gelen Ürün Maliyeti", "Mevcut Kargo", "Gelen Kargo", "Maliyet Dövizi", "Maliyet Kaynağı", "Amazon Net (USD)", "Tahmini Gerçek Kâr (USD)", "Durum", "İşlem"].map(h =>
                <th key={h} className="text-left font-semibold px-3 py-2 whitespace-nowrap">{h}</th>)}</tr>
            </thead>
            <tbody className="divide-y">
              {result.preview.map((row, i) => <tr key={i} data-testid={`sf-preview-row-${i}`}>
                <td className="px-3 py-2 font-mono break-all" data-testid={`sf-row-order-${i}`}>{row.seller_order_id}</td>
                <td className="px-3 py-2 whitespace-nowrap" data-testid={`sf-row-match-${i}`}>{row.amazon_match ? <>✓ {MP_BY_CODE[row.marketplace]?.flag} {row.marketplace}</> : "—"}</td>
                <td className="px-3 py-2 font-mono-num" data-testid={`sf-row-current-product-${i}`}>{formatUsd(row.current_product_cost)}</td>
                <td className="px-3 py-2 font-mono-num" data-testid={`sf-row-incoming-product-${i}`}>{row.incoming_product_cost == null ? "boş" : formatUsd(row.incoming_product_cost)}</td>
                <td className="px-3 py-2 font-mono-num" data-testid={`sf-row-current-shipping-${i}`}>{formatUsd(row.current_shipping_cost)}</td>
                <td className="px-3 py-2 font-mono-num" data-testid={`sf-row-incoming-shipping-${i}`}>{row.incoming_shipping_cost == null ? "boş" : formatUsd(row.incoming_shipping_cost)}</td>
                <td className="px-3 py-2 font-mono" data-testid={`sf-row-currency-${i}`}>{row.cost_currency}</td>
                <td className="px-3 py-2" data-testid={`sf-row-source-${i}`}>{row.cost_source || "—"}</td>
                <td className="px-3 py-2 font-mono-num">{formatUsd(row.existing_amazon_net_total)}</td>
                <td className={`px-3 py-2 font-mono-num font-semibold ${row.estimated_actual_profit < 0 ? "text-rose-700" : "text-emerald-700"}`}>{formatUsd(row.estimated_actual_profit)}</td>
                <td className="px-3 py-2" data-testid={`sf-row-status-${i}`}><StatusBadge status={row.match_status} /></td>
                <td className="px-3 py-2 text-slate-600 min-w-48" data-testid={`sf-row-action-${i}`}>{row.action}</td>
              </tr>)}
            </tbody>
          </table>
          {result.total_rows > result.preview.length && <p className="text-xs text-slate-500 px-3 py-2">İlk {result.preview.length} satır gösteriliyor.</p>}
        </div>
      </div>}
    </section>

    {unmatched.length > 0 && <section className="bg-white rounded-2xl border border-orange-200 p-5" data-testid="sf-unmatched">
      <h2 className="font-display font-bold text-lg text-slate-900 mb-1">Eşleşmeyen SellerFlash Siparişleri ({unmatched.length})</h2>
      <p className="text-xs text-slate-500 mb-3">Bu Seller Order Id değerlerine ait Amazon siparişi henüz içe aktarılmamış. Amazon Payments raporunu yükledikten sonra SellerFlash raporunu tekrar içe aktarın — kayıtlar otomatik eşleşir.</p>
      <div className="flex flex-wrap gap-2">
        {unmatched.slice(0, 30).map(u => <span key={u.id} className="px-2 py-1 rounded-lg bg-orange-50 border border-orange-200 text-xs font-mono" data-testid={`sf-unmatched-${u.seller_order_id}`}>
          {u.seller_order_id} · {u.marketplace}
        </span>)}
        {unmatched.length > 30 && <span className="text-xs text-slate-500">+{unmatched.length - 30} kayıt</span>}
      </div>
    </section>}

    <section className="bg-white rounded-2xl border border-slate-200 p-5" data-testid="sf-history">
      <h2 className="font-display font-bold text-lg text-slate-900 mb-3 flex items-center gap-2"><FileSpreadsheet className="w-4 h-4" /> SellerFlash İçe Aktarma Geçmişi</h2>
      {history.length === 0 && <p className="text-sm text-slate-500" data-testid="sf-history-empty">Henüz SellerFlash içe aktarması yok.</p>}
      {history.length > 0 && <div className="overflow-x-auto">
        <table className="w-full text-xs min-w-[760px]">
          <thead className="bg-slate-50 text-slate-600"><tr>{["Dosya", "Tür", "Yükleme", "Pazar", "Satır", "Yeni", "Güncellenen", "Aynı", "Eşleşmedi", "Çakışma", "Durum"].map(h => <th key={h} className="text-left font-semibold px-3 py-2 whitespace-nowrap">{h}</th>)}</tr></thead>
          <tbody className="divide-y">
            {history.map(b => <tr key={b.id} data-testid={`sf-history-${b.id}`}>
              <td className="px-3 py-2 break-all">{b.file_name || "—"}</td>
              <td className="px-3 py-2 uppercase font-mono">{b.file_type}</td>
              <td className="px-3 py-2 whitespace-nowrap">{b.uploaded_at?.slice(0, 16).replace("T", " ")}</td>
              <td className="px-3 py-2">{(b.marketplaces || []).join(", ") || "—"}</td>
              <td className="px-3 py-2 font-mono-num">{b.total_rows}</td>
              <td className="px-3 py-2 font-mono-num">{b.new}</td>
              <td className="px-3 py-2 font-mono-num">{b.updated}</td>
              <td className="px-3 py-2 font-mono-num">{b.unchanged}</td>
              <td className="px-3 py-2 font-mono-num">{b.unmatched}</td>
              <td className="px-3 py-2 font-mono-num">{b.conflicts}</td>
              <td className="px-3 py-2"><span className="px-1.5 py-0.5 rounded-full bg-emerald-100 text-emerald-800 text-[10px] font-semibold">{b.status}</span></td>
            </tr>)}
          </tbody>
        </table>
      </div>}
      <p className="text-[11px] text-slate-400 mt-3">İçe aktarma geçmişi yalnızca denetim amaçlıdır; finansal toplamları etkilemez.</p>
    </section>
  </div>;
}
