import { useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

export const STOCK = {
  OUT_OF_STOCK: ["Out of Stock", "bg-rose-100 text-rose-700"],
  LOW_STOCK: ["Low Stock", "bg-amber-100 text-amber-800"],
  HEALTHY: ["Healthy Stock", "bg-emerald-100 text-emerald-800"],
};

export const StockBadge = ({ status, testId }) => {
  const [label, cls] = STOCK[status] || STOCK.HEALTHY;
  return <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-semibold whitespace-nowrap ${cls}`} data-testid={testId}>{label}</span>;
};

/** Overview: only non-healthy SKUs. */
export const StockAlerts = ({ rows }) => {
  const alerts = (rows || []).filter(r => r.stock_status !== "HEALTHY");
  if (!alerts.length) return null;
  return (
    <div className="border border-amber-200 bg-amber-50 rounded-xl px-4 py-3" data-testid="fba-stock-alerts">
      <p className="text-sm font-semibold text-amber-900 mb-2">Stok uyarıları ({alerts.length})</p>
      <div className="flex flex-wrap gap-2">
        {alerts.map(r => <span key={r.sku} className="text-xs bg-white border border-amber-200 rounded-md px-2 py-1 flex items-center gap-2" data-testid={`fba-stock-alert-${r.sku}`}>
          <span className="font-mono">{r.sku}</span> {r.remaining_units} adet{r.threshold != null && ` / eşik ${r.threshold}`} <StockBadge status={r.stock_status} />
        </span>)}
      </div>
    </div>
  );
};

const ThresholdInput = ({ row, storeId, onSaved }) => {
  const [value, setValue] = useState(row.threshold ?? "");
  const save = async () => {
    const threshold = value === "" ? null : Number(value);
    if (threshold === row.threshold) return;
    try { await api.put("/fba/thresholds", { store_id: storeId, sku: row.sku, threshold }); toast.success(`${row.sku} eşiği kaydedildi`); onSaved(); }
    catch { toast.error("Eşik kaydedilemedi"); }
  };
  return <div className="flex gap-1 items-center">
    <Input type="number" min="0" value={value} onChange={e => setValue(e.target.value)} className="h-8 w-24" placeholder="—" data-testid={`fba-threshold-input-${row.sku}`} />
    <Button size="sm" variant="outline" onClick={save} data-testid={`fba-threshold-save-${row.sku}`}>Kaydet</Button>
  </div>;
};

/** Lots tab: SKU stock status with editable low-stock threshold. */
export const StockStatusTable = ({ rows, storeId, onSaved }) => (
  <div className="border border-slate-200 rounded-xl bg-white overflow-x-auto" data-testid="fba-stock-status">
    <table className="w-full text-sm">
      <thead className="bg-slate-50 text-xs uppercase text-slate-500"><tr>{["SKU", "ASIN", "Ürün", "Kalan (açık lotlar)", "Açık Lot", "Düşük Stok Eşiği", "Stok Durumu"].map(h => <th key={h} className="py-2 px-3 text-left whitespace-nowrap">{h}</th>)}</tr></thead>
      <tbody>
        {!rows.length && <tr><td colSpan={7} className="text-center text-slate-500 py-4">Henüz lot yok</td></tr>}
        {rows.map(r => <tr key={r.sku} className="border-b border-slate-100" data-testid={`fba-stock-row-${r.sku}`}>
          <td className="py-2 px-3 font-mono text-xs">{r.sku}</td><td className="py-2 px-3 font-mono text-xs">{r.asin || "—"}</td>
          <td className="py-2 px-3 max-w-48 truncate">{r.product_name || "—"}</td>
          <td className="py-2 px-3 font-mono-num" data-testid={`fba-stock-units-${r.sku}`}>{r.remaining_units}</td><td className="py-2 px-3 font-mono-num">{r.open_lots}</td>
          <td className="py-2 px-3"><ThresholdInput key={`${r.sku}-${r.threshold}`} row={r} storeId={storeId} onSaved={onSaved} /></td>
          <td className="py-2 px-3"><StockBadge status={r.stock_status} testId={`fba-stock-badge-${r.sku}`} /></td>
        </tr>)}
      </tbody>
    </table>
  </div>
);
