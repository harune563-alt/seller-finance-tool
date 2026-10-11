import { Trash2, Plus, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { formatUsd } from "@/components/FxStatus";
import { pct, roasFmt, num, StatusPill } from "./ppcFormat";

const HEAD = ["Tarih", "Pazar", "Kategori", "Kampanya", "Reklam Tipi", "ASIN", "SKU", "Harcama", "PPC Satış", "Tık.", "Gös.", "Sip.", "ACoS", "ROAS", "Durum", ""];
const RIGHT = new Set([7, 8, 9, 10, 11, 12, 13]);

const Row = ({ r, onDelete }) => (
  <tr className="border-b border-slate-50 hover:bg-slate-50/60" data-testid={`ppc-row-${r.id}`}>
    <td className="px-4 py-2.5 font-mono-num text-slate-700 whitespace-nowrap">{r.date}</td>
    <td className="px-3 py-2.5 text-slate-600">{r.marketplace || "—"}</td>
    <td className="px-3 py-2.5 text-xs text-slate-600">{r.ppc_category || "—"}</td>
    <td className="px-3 py-2.5 text-slate-700 max-w-[160px] truncate" title={r.campaign}>{r.campaign || "—"}</td>
    <td className="px-3 py-2.5 text-xs text-slate-600">{r.ad_type || "—"}</td>
    <td className="px-3 py-2.5 font-mono text-xs">{r.asin || "—"}</td>
    <td className="px-3 py-2.5 font-mono text-xs">{r.sku || "—"}</td>
    <td className="px-3 py-2.5 text-right font-mono-num text-amber-700">{formatUsd(r.ad_spend_usd)}</td>
    <td className="px-3 py-2.5 text-right font-mono-num text-emerald-700">{formatUsd(r.ppc_sales_usd)}</td>
    <td className="px-3 py-2.5 text-right font-mono-num">{num(r.clicks)}</td>
    <td className="px-3 py-2.5 text-right font-mono-num">{num(r.impressions)}</td>
    <td className="px-3 py-2.5 text-right font-mono-num">{num(r.orders)}</td>
    <td className="px-3 py-2.5 text-right font-mono-num">{pct(r.acos_percent)}</td>
    <td className="px-3 py-2.5 text-right font-mono-num">{roasFmt(r.roas)}</td>
    <td className="px-3 py-2.5"><StatusPill status={r.reconciliation_status} label={r.reconciliation_label} testId={`ppc-status-${r.id}`} /></td>
    <td className="px-3 py-2.5 text-right">
      <button className="text-slate-400 hover:text-rose-600" onClick={() => onDelete(r)} data-testid={`ppc-delete-${r.id}`} title={r.notes || "Sil"}><Trash2 className="w-4 h-4" /></button>
    </td>
  </tr>
);

export const PpcRecords = ({ rows, onAdd, onImport, onDelete }) => (
  <div className="rounded-2xl bg-white border border-slate-200 overflow-hidden" data-testid="ppc-table-card">
    <div className="px-5 py-4 border-b border-slate-100 flex flex-wrap gap-3 items-center justify-between">
      <div>
        <h2 className="font-display text-lg font-bold text-slate-900">PPC Kayıtları (Attribution)</h2>
        <p className="text-xs text-slate-500">{rows.length} kayıt · Bu kayıtlar finansal gider oluşturmaz</p>
      </div>
      <div className="flex gap-2">
        <Button variant="outline" onClick={onImport} className="rounded-xl" data-testid="ppc-import-btn"><Upload className="w-4 h-4 mr-2" /> PPC Raporu İçe Aktar</Button>
        <Button onClick={onAdd} className="bg-pink-600 hover:bg-pink-700 text-white rounded-xl" data-testid="ppc-add-btn"><Plus className="w-4 h-4 mr-2" /> Manuel PPC Kaydı</Button>
      </div>
    </div>
    <div className="overflow-x-auto">
      <table className="w-full text-sm min-w-[1400px]">
        <thead>
          <tr className="text-left text-xs uppercase tracking-wider text-slate-500 border-b border-slate-100">
            {HEAD.map((h, i) => <th key={i} className={`px-3 py-3 ${RIGHT.has(i) ? "text-right" : ""}`}>{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && <tr><td colSpan={HEAD.length} className="px-5 py-8 text-center text-slate-400" data-testid="ppc-empty-rows">Bu filtrelerle PPC kaydı yok</td></tr>}
          {rows.map(r => <Row key={r.id} r={r} onDelete={onDelete} />)}
        </tbody>
      </table>
    </div>
  </div>
);
