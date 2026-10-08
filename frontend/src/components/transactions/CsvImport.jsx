import { useEffect, useState } from "react";
import { Upload } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { MP_BY_CODE, formatMoney } from "@/constants/marketplaces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const STATUS_LABELS = {
  new: "Yeni",
  existing_unchanged: "Değişmemiş",
  existing_updated: "Güncellenecek",
  date_changed: "Tarih değişmiş",
  possible_duplicate: "Olası mükerrer",
  conflict: "Çakışma",
};

export const CsvImport = ({ onSaved }) => {
  const { activeStore, activeStoreId, activeMarketplace } = useStore();
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState(null);
  const [marketplace, setMarketplace] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [history, setHistory] = useState([]);

  useEffect(() => {
    if (!open || !activeStoreId) return;
    api.get("/transactions/import/history", { params: { store_id: activeStoreId } })
      .then(({ data }) => setHistory(data || []))
      .catch(() => setHistory([]));
  }, [open, activeStoreId, result?.batch_id]);

  const openChanged = value => {
    if (busy) return;
    setOpen(value); setFile(null); setResult(null); setError("");
    setMarketplace(activeStore?.marketplaces?.includes(activeMarketplace) ? activeMarketplace : activeStore?.marketplaces?.[0] || "");
  };
  const upload = async commit => {
    setError("");
    if (!file || !marketplace) { setError("CSV dosyası ve pazar yeri seçin."); return; }
    if (!file.name.toLowerCase().endsWith(".csv") || file.size > 5 * 1024 * 1024) { setError("En fazla 5 MB büyüklüğünde bir CSV dosyası seçin."); return; }
    setBusy(true);
    try {
      const body = new FormData(); body.append("file", file);
      const { data } = await api.post("/transactions/import", body, { params: { store_id: activeStoreId, marketplace, commit } });
      setResult(data);
      if (commit) { toast.success(`${data.inserted} yeni kayıt eklendi`); onSaved(); }
    } catch (err) { const detail = err.response?.data?.detail; setError(typeof detail === "string" ? detail : "CSV yüklenemedi."); }
    finally { setBusy(false); }
  };
  const recon = result?.reconciliation;
  const applicable = recon ? recon.new + recon.existing_updated + recon.date_changed : (result ? result.accepted - result.duplicates : 0);
  return <Dialog open={open} onOpenChange={openChanged}><DialogTrigger asChild><Button variant="outline" disabled={!activeStoreId} className="bg-white" data-testid="open-csv-import"><Upload className="w-4 h-4 mr-2" />CSV İçe Aktar</Button></DialogTrigger>
    <DialogContent className="bg-white max-w-2xl max-h-[88vh] overflow-y-auto" data-testid="csv-import-dialog">
      <DialogHeader><DialogTitle>Amazon Payments CSV</DialogTitle><DialogDescription>Order payments · Refunds · Service Fees — tekrarlı/örtüşen raporlar güvenle yüklenebilir</DialogDescription></DialogHeader>
      <div className="space-y-4">
        <div><Label htmlFor="csv-marketplace">Raporun Pazar Yeri</Label><Select value={marketplace} disabled={busy} onValueChange={v => { if (activeStore?.marketplaces.includes(v)) { setMarketplace(v); setResult(null); } }}><SelectTrigger id="csv-marketplace" data-testid="csv-marketplace-select" className="mt-2"><SelectValue /></SelectTrigger><SelectContent data-testid="csv-marketplace-options">{(activeStore?.marketplaces || []).map(c => <SelectItem key={c} value={c} data-testid={`csv-marketplace-${c.toLowerCase()}`}>{MP_BY_CODE[c]?.flag} {MP_BY_CODE[c]?.name} · {MP_BY_CODE[c]?.currency}</SelectItem>)}</SelectContent></Select></div>
        <div><Label htmlFor="csv-file">CSV Dosyası</Label><Input id="csv-file" type="file" accept=".csv,text/csv" disabled={busy} data-testid="csv-file-input" className="mt-2" onChange={e => { setFile(e.target.files?.[0]); setResult(null); setError(""); }} /></div>
        <p className="text-xs text-slate-500" data-testid="csv-accounting-note">CSV Total tutarı, Amazon kesintileri sonrası değerdir; bu kesintiler tekrar düşülmez. Aynı raporu veya örtüşen raporları tekrar yüklemek finansal toplamları değiştirmez. Amazon bir işlemin tarihini sonradan değiştirirse ilk kaydedilen tarih korunur.</p>
        {error && <p role="alert" data-testid="csv-error" className="text-sm text-rose-700">{error}</p>}
        {result && <div className="space-y-3" data-testid="csv-preview">
          <div className="text-sm bg-slate-50 p-3 rounded-md space-y-1" data-testid="csv-result-counts"><p>{result.accepted} uygun · {result.duplicates} tekrar · {result.rejected_count} atlanan satır</p>{result.committed && <p className="font-semibold text-emerald-700" data-testid="csv-import-success">{result.inserted} kayıt eklendi</p>}</div>
          {recon && <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs" data-testid="csv-reconciliation">
            <div className="rounded-lg bg-emerald-50 border border-emerald-200 px-2 py-1.5" data-testid="csv-recon-new"><span className="block text-emerald-800 font-semibold">{recon.new}</span>Yeni</div>
            <div className="rounded-lg bg-slate-50 border border-slate-200 px-2 py-1.5" data-testid="csv-recon-unchanged"><span className="block text-slate-800 font-semibold">{recon.existing_unchanged}</span>Değişmemiş</div>
            <div className="rounded-lg bg-amber-50 border border-amber-200 px-2 py-1.5" data-testid="csv-recon-date-changed"><span className="block text-amber-800 font-semibold">{recon.date_changed}</span>Tarih değişimi</div>
            <div className="rounded-lg bg-sky-50 border border-sky-200 px-2 py-1.5" data-testid="csv-recon-updated"><span className="block text-sky-800 font-semibold">{recon.existing_updated}</span>Güncellenen</div>
            <div className="rounded-lg bg-orange-50 border border-orange-200 px-2 py-1.5" data-testid="csv-recon-possible-duplicates"><span className="block text-orange-800 font-semibold">{recon.possible_duplicates}</span>Olası mükerrer</div>
            <div className="rounded-lg bg-rose-50 border border-rose-200 px-2 py-1.5" data-testid="csv-recon-conflicts"><span className="block text-rose-800 font-semibold">{recon.conflicts}</span>Çakışma</div>
            <div className="rounded-lg bg-slate-50 border border-slate-200 px-2 py-1.5 col-span-2" data-testid="csv-recon-orders"><span className="block text-slate-800 font-semibold">{recon.orders_affected}</span>Etkilenen sipariş</div>
          </div>}
          {result.date_changes?.length > 0 && <div className="text-xs bg-amber-50 border border-amber-200 rounded-md p-3 space-y-1" data-testid="csv-date-changes">
            <p className="font-semibold text-amber-900">Amazon tarafından bildirilen tarih değişti — ilk kaydedilen tarih korunur:</p>
            {result.date_changes.map((c, i) => <p key={i} data-testid={`csv-date-change-${i}`}>{c.order_id || "—"}: {c.previous_reported_date} → {c.new_reported_date}</p>)}
            {recon && recon.date_changed > result.date_changes.length && <p>İlk {result.date_changes.length} değişiklik gösteriliyor.</p>}
          </div>}
          {result.issues.length > 0 && <div className="text-xs text-amber-800 bg-amber-50 rounded-md p-3 max-h-32 overflow-y-auto" data-testid="csv-issues">{result.issues.map((issue, i) => <p key={i}>Satır {issue.line}: {issue.reason}</p>)}{result.rejected_count > 100 && <p>İlk 100 hata gösteriliyor.</p>}</div>}
          <div className="divide-y text-xs max-h-52 overflow-y-auto">{result.preview.map((r, i) => <div key={i} className="py-2 flex flex-wrap gap-2 justify-between items-center" data-testid={`csv-preview-row-${i}`}><span className="flex items-center gap-2 flex-wrap">{r.date} · {r.category}{result.classifications?.[i] && <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-semibold ${result.classifications[i].status === "new" ? "bg-emerald-100 text-emerald-800" : result.classifications[i].status === "date_changed" ? "bg-amber-100 text-amber-800" : result.classifications[i].status === "existing_unchanged" ? "bg-slate-100 text-slate-600" : "bg-orange-100 text-orange-800"}`} data-testid={`csv-row-status-${i}`}>{STATUS_LABELS[result.classifications[i].status] || result.classifications[i].status}</span>}</span><strong>{formatMoney(r.type === "expense" ? -r.amount : r.amount, r.currency)}</strong></div>)}</div>
          {result.accepted > 20 && <p className="text-xs text-slate-500">İlk 20 kayıt gösteriliyor.</p>}
        </div>}
        {!result && history.length > 0 && <div className="border-t pt-3" data-testid="csv-import-history">
          <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">Son İçe Aktarmalar</p>
          <div className="divide-y text-xs max-h-40 overflow-y-auto">
            {history.slice(0, 8).map(b => <div key={b.id} className="py-1.5 flex flex-wrap justify-between gap-2" data-testid={`csv-history-${b.id}`}>
              <span className="text-slate-700">{b.file_name || "dosya"} · {b.uploaded_at?.slice(0, 10)}</span>
              <span className="text-slate-500">{b.new} yeni · {b.date_changed} tarih · {b.existing_unchanged} aynı{b.report_date_min ? ` · ${b.report_date_min}→${b.report_date_max}` : ""}</span>
            </div>)}
          </div>
        </div>}
        <div className="flex justify-end gap-2 flex-wrap">
          <Button variant="outline" onClick={() => openChanged(false)} disabled={busy} data-testid="csv-close">{result?.committed ? "Kapat" : "Vazgeç"}</Button>
          {!result?.committed && <Button variant="outline" onClick={() => upload(false)} disabled={busy || !file} data-testid="csv-preview-button">{busy ? "İşleniyor…" : "Önizle"}</Button>}
          {result && !result.committed && <Button onClick={() => upload(true)} disabled={busy || applicable <= 0} data-testid="csv-import-submit">{busy ? "Aktarılıyor…" : recon ? (recon.date_changed > 0 && recon.new === 0 ? `${recon.date_changed} Tarih Güncellemesini Uygula` : `${recon.new} Yeni Kaydı İçe Aktar`) : `${result.accepted - result.duplicates} Kaydı İçe Aktar`}</Button>}
        </div>
      </div>
    </DialogContent>
  </Dialog>;
};