import { useState } from "react";
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

export const CsvImport = ({ onSaved }) => {
  const { activeStore, activeStoreId, activeMarketplace } = useStore();
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState(null);
  const [marketplace, setMarketplace] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
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
      if (commit) { toast.success(`${data.inserted} kayıt eklendi`); onSaved(); }
    } catch (err) { const detail = err.response?.data?.detail; setError(typeof detail === "string" ? detail : "CSV yüklenemedi."); }
    finally { setBusy(false); }
  };
  return <Dialog open={open} onOpenChange={openChanged}><DialogTrigger asChild><Button variant="outline" disabled={!activeStoreId} className="bg-white" data-testid="open-csv-import"><Upload className="w-4 h-4 mr-2" />CSV İçe Aktar</Button></DialogTrigger>
    <DialogContent className="bg-white max-w-2xl max-h-[88vh] overflow-y-auto" data-testid="csv-import-dialog">
      <DialogHeader><DialogTitle>Amazon Payments CSV</DialogTitle><DialogDescription>Order payments · Refunds · Service Fees</DialogDescription></DialogHeader>
      <div className="space-y-4">
        <div><Label htmlFor="csv-marketplace">Raporun Pazar Yeri</Label><Select value={marketplace} disabled={busy} onValueChange={v => { if (activeStore?.marketplaces.includes(v)) { setMarketplace(v); setResult(null); } }}><SelectTrigger id="csv-marketplace" data-testid="csv-marketplace-select" className="mt-2"><SelectValue /></SelectTrigger><SelectContent data-testid="csv-marketplace-options">{(activeStore?.marketplaces || []).map(c => <SelectItem key={c} value={c} data-testid={`csv-marketplace-${c.toLowerCase()}`}>{MP_BY_CODE[c]?.flag} {MP_BY_CODE[c]?.name} · {MP_BY_CODE[c]?.currency}</SelectItem>)}</SelectContent></Select></div>
        <div><Label htmlFor="csv-file">CSV Dosyası</Label><Input id="csv-file" type="file" accept=".csv,text/csv" disabled={busy} data-testid="csv-file-input" className="mt-2" onChange={e => { setFile(e.target.files?.[0]); setResult(null); setError(""); }} /></div>
        <p className="text-xs text-slate-500" data-testid="csv-accounting-note">CSV Total tutarı, Amazon kesintileri sonrası değerdir; bu kesintiler tekrar düşülmez. Ürün, kargo ve ekstra maliyetleriniz ayrı tutulur.</p>
        {error && <p role="alert" data-testid="csv-error" className="text-sm text-rose-700">{error}</p>}
        {result && <div className="space-y-3" data-testid="csv-preview">
          <div className="text-sm bg-slate-50 p-3 rounded-md space-y-1" data-testid="csv-result-counts"><p>{result.accepted} uygun · {result.duplicates} tekrar · {result.rejected_count} atlanan satır</p>{result.committed && <p className="font-semibold text-emerald-700" data-testid="csv-import-success">{result.inserted} kayıt eklendi</p>}</div>
          {result.issues.length > 0 && <div className="text-xs text-amber-800 bg-amber-50 rounded-md p-3 max-h-32 overflow-y-auto" data-testid="csv-issues">{result.issues.map((issue, i) => <p key={i}>Satır {issue.line}: {issue.reason}</p>)}{result.rejected_count > 100 && <p>İlk 100 hata gösteriliyor.</p>}</div>}
          <div className="divide-y text-xs max-h-52 overflow-y-auto">{result.preview.map((r, i) => <div key={i} className="py-2 flex flex-wrap gap-2 justify-between" data-testid={`csv-preview-row-${i}`}><span>{r.date} · {r.category}</span><strong>{formatMoney(r.type === "expense" ? -r.amount : r.amount, r.currency)}</strong></div>)}</div>
          {result.accepted > 20 && <p className="text-xs text-slate-500">İlk 20 kayıt gösteriliyor.</p>}
        </div>}
        <div className="flex justify-end gap-2 flex-wrap">
          <Button variant="outline" onClick={() => openChanged(false)} disabled={busy} data-testid="csv-close">{result?.committed ? "Kapat" : "Vazgeç"}</Button>
          {!result?.committed && <Button variant="outline" onClick={() => upload(false)} disabled={busy || !file} data-testid="csv-preview-button">{busy ? "İşleniyor…" : "Önizle"}</Button>}
          {result && !result.committed && <Button onClick={() => upload(true)} disabled={busy || result.accepted <= result.duplicates} data-testid="csv-import-submit">{busy ? "Aktarılıyor…" : `${result.accepted - result.duplicates} Kaydı İçe Aktar`}</Button>}
        </div>
      </div>
    </DialogContent>
  </Dialog>;
};