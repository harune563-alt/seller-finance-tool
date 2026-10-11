import { useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { formatUsd } from "@/components/FxStatus";
import { SelectField, FormError, apiError } from "@/components/company/Fields";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";

export const PpcImportDialog = ({ open, onOpenChange, storeId, marketplaces, onSaved }) => {
  const [file, setFile] = useState(null);
  const [marketplace, setMarketplace] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { if (open) { setFile(null); setResult(null); setError(""); setMarketplace(marketplaces[0] || ""); } }, [open]);

  const run = async (commit) => {
    if (!storeId) { setError("Önce tek bir mağaza seçin"); return; }
    if (!file || !marketplace) { setError("Dosya ve pazar yeri seçin"); return; }
    setBusy(true); setError("");
    const fd = new FormData(); fd.append("file", file);
    try {
      const { data } = await api.post("/ppc/attributions/import-file", fd, { params: { store_id: storeId, marketplace, commit } });
      setResult(data);
      if (commit) { toast.success(`${data.new} yeni, ${data.existing} güncellenen PPC kaydı`); onSaved(); }
    } catch (err) { setError(apiError(err)); }
    finally { setBusy(false); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white max-w-xl" data-testid="ppc-import-dialog">
        <DialogHeader>
          <DialogTitle>PPC Raporu İçe Aktar</DialogTitle>
          <DialogDescription>Amazon Advertising raporu (CSV/XLSX). Aynı rapor tekrar yüklenirse kayıtlar güncellenir, çoğaltılmaz. Finansal gider oluşturulmaz.</DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <SelectField label="Pazar Yeri" id="ppc-import-marketplace" value={marketplace} onChange={setMarketplace} options={marketplaces.map(c => ({ value: c, label: c }))} />
          <input type="file" accept=".csv,.xlsx,.tsv,.txt" onChange={e => { setFile(e.target.files?.[0] || null); setResult(null); }} data-testid="ppc-import-file" className="block w-full text-sm" />
          {result && (
            <div className="text-sm bg-slate-50 rounded-lg p-3 space-y-1" data-testid="ppc-import-result">
              <p>{result.total} satır · <b>{result.new}</b> yeni · <b>{result.existing}</b> mevcut · {result.rejected_count} atlanan</p>
              <p>Toplam harcama: <b>{formatUsd(result.total_spend_usd)}</b> {result.committed ? "· Kaydedildi" : "· Önizleme"}</p>
              {result.issues?.length > 0 && <div className="text-xs text-amber-800 max-h-24 overflow-y-auto">{result.issues.map((x, i) => <p key={i}>Satır {x.line}: {x.reason}</p>)}</div>}
            </div>
          )}
          <FormError error={error} id="ppc-import-error" />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => run(false)} disabled={busy || !file} data-testid="ppc-import-preview">Önizle</Button>
          <Button onClick={() => run(true)} disabled={busy || !file || result?.committed} className="bg-pink-600 hover:bg-pink-700 text-white" data-testid="ppc-import-commit">İçe Aktar</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
