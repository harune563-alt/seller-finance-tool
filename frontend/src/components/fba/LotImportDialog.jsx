import { useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { FormError, apiError } from "@/components/company/Fields";
import { usd, unitUsd } from "@/components/fba/common";

const STATUS = {
  new_lot: ["Yeni Lot", "bg-emerald-100 text-emerald-800"],
  existing_unchanged: ["Mevcut · Değişmedi", "bg-slate-100 text-slate-600"],
  updated: ["Güncellenecek", "bg-sky-100 text-sky-800"],
  invalid: ["Geçersiz", "bg-rose-100 text-rose-700"],
};

export const LotImportDialog = ({ open, onClose, storeId, onSaved }) => {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async commit => {
    setBusy(true); setError("");
    try {
      const body = new FormData(); body.append("file", file);
      const { data } = await api.post("/fba/lots/import", body, { params: { store_id: storeId, commit } });
      setResult(data);
      if (commit) { toast.success(`${data.counts.new_lot} yeni lot, ${data.counts.updated} güncelleme`); onSaved(); }
    } catch (e) { setError(apiError(e)); } finally { setBusy(false); }
  };
  const close = () => { setFile(null); setResult(null); setError(""); onClose(); };
  const actionable = result ? result.counts.new_lot + result.counts.updated : 0;
  return (
    <Dialog open={open} onOpenChange={v => !v && close()}>
      <DialogContent className="bg-white max-w-5xl max-h-[85vh] overflow-y-auto" data-testid="fba-lot-import-dialog">
        <DialogHeader><DialogTitle>FBA Lot İçe Aktarma (CSV / XLSX)</DialogTitle>
          <DialogDescription>Zorunlu: SKU, ASIN, Product Name, Purchase Date, Original Quantity, Product Unit Cost USD, Inbound Shipping Total USD. Opsiyonel: FBA Received Date, Marketplace, Lot Reference. Lot kimliği: SKU + Lot Reference (yoksa SKU + Purchase Date).</DialogDescription></DialogHeader>
        <div className="flex flex-wrap gap-3 items-center">
          <Input type="file" accept=".csv,.xlsx" className="max-w-sm" data-testid="fba-lot-import-file" onChange={e => { setFile(e.target.files?.[0] || null); setResult(null); }} />
          <Button variant="outline" disabled={!file || busy} onClick={() => run(false)} data-testid="fba-lot-import-preview">Önizle</Button>
          {result && !result.committed && <Button disabled={busy || !actionable} onClick={() => run(true)} className="bg-emerald-600 hover:bg-emerald-700 text-white" data-testid="fba-lot-import-apply">{actionable} Lotu Uygula</Button>}
        </div>
        <FormError error={error} id="fba-lot-import-error" />
        {result && <>
          <div className="flex flex-wrap gap-2 text-xs" data-testid="fba-lot-import-counts">
            {Object.entries(STATUS).map(([k, [label, cls]]) => <span key={k} className={`px-2 py-1 rounded-md ${cls}`} data-testid={`fba-lot-import-count-${k}`}>{label}: {result.counts[k]}</span>)}
            {result.committed && <span className="text-emerald-700 font-semibold" data-testid="fba-lot-import-done">Uygulandı</span>}
          </div>
          <div className="overflow-x-auto border rounded-lg">
            <table className="w-full text-xs">
              <thead className="bg-slate-50 text-slate-500"><tr>{["Satır", "SKU", "ASIN", "Ürün", "Alış", "Adet", "Ürün/Birim", "Inbound Top.", "Landed/Birim", "Durum", "Not"].map(h => <th key={h} className="text-left px-2 py-1.5 whitespace-nowrap">{h}</th>)}</tr></thead>
              <tbody className="divide-y">
                {result.rows.map((r, i) => <tr key={i} data-testid={`fba-lot-import-row-${i}`}>
                  <td className="px-2 py-1.5">{r.line}</td><td className="px-2 py-1.5 font-mono">{r.sku}</td><td className="px-2 py-1.5 font-mono">{r.asin}</td>
                  <td className="px-2 py-1.5 max-w-40 truncate">{r.product_name}</td><td className="px-2 py-1.5">{r.purchase_date || "—"}</td>
                  <td className="px-2 py-1.5 font-mono-num">{r.original_quantity ?? "—"}</td><td className="px-2 py-1.5 font-mono-num">{usd(r.product_unit_cost_usd)}</td>
                  <td className="px-2 py-1.5 font-mono-num">{usd(r.inbound_shipping_total_usd)}</td><td className="px-2 py-1.5 font-mono-num">{unitUsd(r.landed_unit_cost_usd)}</td>
                  <td className="px-2 py-1.5"><span className={`px-1.5 py-0.5 rounded-full text-[10px] font-semibold ${STATUS[r.status][1]}`} data-testid={`fba-lot-import-status-${i}`}>{STATUS[r.status][0]}</span></td>
                  <td className="px-2 py-1.5 text-slate-500">{r.errors.join("; ") || Object.keys(r.changes || {}).join(", ") || (r.lot_code || "")}</td>
                </tr>)}
              </tbody>
            </table>
          </div>
        </>}
        <DialogFooter><Button variant="outline" onClick={close} data-testid="fba-lot-import-close">Kapat</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  );
};
