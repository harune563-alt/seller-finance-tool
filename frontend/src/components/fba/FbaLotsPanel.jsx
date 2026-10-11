import { useState } from "react";
import { History, Pencil, Plus, SlidersHorizontal, Upload } from "lucide-react";
import { LotImportDialog } from "@/components/fba/LotImportDialog";
import { StockAlerts, StockBadge, StockStatusTable } from "@/components/fba/StockStatus";
import { Button } from "@/components/ui/button";
import { TableCard, THead, Td, EmptyRow, usd, unitUsd } from "@/components/fba/common";
import { LotFormDialog, AdjustDialog, LotHistoryDialog } from "@/components/fba/LotDialogs";

const COLS = [["Lot ID"], ["Alış Tarihi"], ["ASIN"], ["SKU"], ["Ürün"], ["İlk Adet", true], ["Tüketilen", true], ["Kalan", true], ["Ürün / Birim", true],
  ["Inbound Toplam", true], ["Inbound / Birim", true], ["Landed / Birim", true], ["Kalan Stok Değeri", true], ["Durum"], [""]];
const STATUS_CLS = { OPEN: "bg-emerald-100 text-emerald-800", DEPLETED: "bg-slate-200 text-slate-700", CLOSED: "bg-rose-100 text-rose-700" };

export const FbaLotsPanel = ({ lots, storeId, marketplaces, onChanged, stock = [] }) => {
  const [form, setForm] = useState(null);
  const [adjust, setAdjust] = useState(null);
  const [history, setHistory] = useState(null);
  const [importing, setImporting] = useState(false);
  const stockBySku = Object.fromEntries(stock.map(s => [s.sku, s.stock_status]));
  return (
    <div className="space-y-4" data-testid="fba-lots-panel">
      <StockAlerts rows={stock} />
      <div className="flex justify-between items-center flex-wrap gap-3">
        <p className="text-xs text-slate-500">Landed birim = Ürün birim + (Inbound toplam ÷ İlk adet). FIFO: aynı SKU'da en eski lot önce tüketilir.</p>
        <div className="flex gap-2">
          <Button variant="outline" onClick={() => setImporting(true)} data-testid="fba-lot-import-btn"><Upload className="w-4 h-4 mr-2" />CSV / XLSX İçe Aktar</Button>
          <Button onClick={() => setForm({})} className="bg-emerald-600 hover:bg-emerald-700 text-white" data-testid="fba-new-lot-btn"><Plus className="w-4 h-4 mr-2" />Yeni Lot</Button>
        </div>
      </div>
      <TableCard testId="fba-lots-table">
        <THead cols={COLS} />
        <tbody>
          {lots.length === 0 && <EmptyRow cols={COLS.length} text="Henüz FBA lotu yok" testId="fba-lots-empty" />}
          {lots.map(l => (
            <tr key={l.id} className="border-b border-slate-100 hover:bg-slate-50" data-testid={`fba-lot-row-${l.lot_code}`}>
              <Td className="font-mono text-xs">{l.lot_code}</Td>
              <Td>{l.purchase_date}</Td>
              <Td className="font-mono text-xs">{l.asin || "—"}</Td>
              <Td className="font-mono text-xs">{l.sku}</Td>
              <Td className="max-w-48 truncate" title={l.product_name}>{l.product_name || "—"}</Td>
              <Td right>{l.original_quantity}</Td>
              <Td right>{l.consumed_quantity}</Td>
              <Td right data-testid={`fba-lot-remaining-${l.lot_code}`}>{l.remaining_quantity}</Td>
              <Td right>{usd(l.product_unit_cost_usd)}</Td>
              <Td right>{usd(l.inbound_shipping_total_usd)}</Td>
              <Td right>{unitUsd(l.inbound_shipping_unit_usd)}</Td>
              <Td right data-testid={`fba-lot-landed-${l.lot_code}`}>{unitUsd(l.landed_unit_cost_usd)}</Td>
              <Td right className="font-semibold" data-testid={`fba-lot-value-${l.lot_code}`}>{usd(l.remaining_value_usd)}</Td>
              <Td><div className="flex gap-1 items-center"><span className={`px-1.5 py-0.5 rounded-full text-[10px] font-semibold ${STATUS_CLS[l.lot_status]}`} data-testid={`fba-lot-status-${l.lot_code}`}>{l.lot_status}</span>{stockBySku[l.sku] && stockBySku[l.sku] !== "HEALTHY" && <StockBadge status={stockBySku[l.sku]} testId={`fba-lot-stock-${l.lot_code}`} />}</div></Td>
              <Td>
                <div className="flex">
                  <Button variant="ghost" size="icon" title="Düzenle" onClick={() => setForm(l)} data-testid={`fba-lot-edit-${l.lot_code}`}><Pencil className="w-4 h-4" /></Button>
                  <Button variant="ghost" size="icon" title="Düzeltme" disabled={l.lot_status === "CLOSED"} onClick={() => setAdjust(l)} data-testid={`fba-lot-adjust-${l.lot_code}`}><SlidersHorizontal className="w-4 h-4" /></Button>
                  <Button variant="ghost" size="icon" title="Geçmiş" onClick={() => setHistory(l)} data-testid={`fba-lot-history-${l.lot_code}`}><History className="w-4 h-4" /></Button>
                </div>
              </Td>
            </tr>
          ))}
        </tbody>
      </TableCard>
      <h3 className="font-display font-bold text-base pt-2">SKU Stok Durumu ve Düşük Stok Eşikleri</h3>
      <StockStatusTable rows={stock} storeId={storeId} onSaved={onChanged} />
      <LotImportDialog open={importing} onClose={() => setImporting(false)} storeId={storeId} onSaved={onChanged} />
      <LotFormDialog open={!!form} lot={form?.id ? form : null} onClose={() => setForm(null)} storeId={storeId} marketplaces={marketplaces} onSaved={onChanged} />
      <AdjustDialog lot={adjust} onClose={() => setAdjust(null)} onSaved={onChanged} />
      <LotHistoryDialog lot={history} onClose={() => setHistory(null)} />
    </div>
  );
};
