import { useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { TextField, SelectField, FormError, apiError, today } from "@/components/company/Fields";
import { usd, unitUsd } from "@/components/fba/common";

const EMPTY = { marketplace: "", sku: "", asin: "", product_name: "", purchase_date: today(), fba_received_date: "", original_quantity: "", product_unit_cost_usd: "", inbound_shipping_total_usd: "", note: "" };

export const LotFormDialog = ({ open, onClose, storeId, marketplaces, lot, onSaved }) => {
  const [form, setForm] = useState(EMPTY);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => { setError(""); setForm(lot ? { ...EMPTY, ...lot, fba_received_date: lot.fba_received_date || "", note: "" } : { ...EMPTY, marketplace: marketplaces[0] || "" }); }, [lot, open, marketplaces]);
  const set = k => v => setForm(f => ({ ...f, [k]: v }));
  const locked = lot && lot.consumed_quantity > 0;
  const qty = Number(form.original_quantity), unit = Number(form.product_unit_cost_usd), inbound = Number(form.inbound_shipping_total_usd || 0);
  const inboundUnit = qty > 0 ? inbound / qty : null;
  const save = async () => {
    setSaving(true); setError("");
    try {
      if (lot) {
        const body = { marketplace: form.marketplace, asin: form.asin, product_name: form.product_name, fba_received_date: form.fba_received_date || null, note: form.note };
        if (!locked) Object.assign(body, { sku: form.sku, purchase_date: form.purchase_date, product_unit_cost_usd: unit });
        await api.patch(`/fba/lots/${lot.id}`, body);
      } else {
        await api.post("/fba/lots", { ...form, store_id: storeId, fba_received_date: form.fba_received_date || null, original_quantity: qty, product_unit_cost_usd: unit, inbound_shipping_total_usd: inbound });
      }
      toast.success(lot ? "Lot güncellendi" : "Lot oluşturuldu — FIFO maliyeti atandı");
      onSaved(); onClose();
    } catch (e) { setError(apiError(e)); } finally { setSaving(false); }
  };
  return (
    <Dialog open={open} onOpenChange={v => !v && onClose()}>
      <DialogContent className="bg-white max-w-2xl" data-testid="fba-lot-dialog">
        <DialogHeader><DialogTitle>{lot ? `Lot düzenle · ${lot.lot_code}` : "Yeni FBA Lotu"}</DialogTitle>
          <DialogDescription>Maliyetler USD. FBA maliyeti yalnızca ürün alış maliyeti + FBA'ya inbound kargodan oluşur.</DialogDescription></DialogHeader>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <SelectField label="Referans Pazar" id="fba-lot-marketplace" value={form.marketplace} onChange={set("marketplace")} options={marketplaces.map(c => ({ value: c, label: c }))} />
          <TextField label="SKU" id="fba-lot-sku" value={form.sku} onChange={set("sku")} disabled={locked} />
          <TextField label="ASIN" id="fba-lot-asin" value={form.asin} onChange={set("asin")} />
          <TextField label="Ürün Adı" id="fba-lot-name" value={form.product_name} onChange={set("product_name")} />
          <TextField label="Alış Tarihi" id="fba-lot-purchase-date" type="date" value={form.purchase_date} onChange={set("purchase_date")} disabled={locked} />
          <TextField label="FBA Teslim Tarihi (opsiyonel)" id="fba-lot-received-date" type="date" value={form.fba_received_date} onChange={set("fba_received_date")} />
          {!lot && <TextField label="Adet" id="fba-lot-qty" type="number" min="1" step="1" value={form.original_quantity} onChange={set("original_quantity")} />}
          <TextField label="Ürün Birim Maliyeti (USD)" id="fba-lot-unit-cost" type="number" min="0" step="0.01" value={form.product_unit_cost_usd} onChange={set("product_unit_cost_usd")} disabled={locked} />
          {!lot && <TextField label="Inbound Kargo Toplamı (USD)" id="fba-lot-inbound" type="number" min="0" step="0.01" value={form.inbound_shipping_total_usd} onChange={set("inbound_shipping_total_usd")} />}
          <TextField label="Not (opsiyonel)" id="fba-lot-note" value={form.note} onChange={set("note")} />
        </div>
        {!lot && <p className="text-xs text-slate-600 bg-slate-50 rounded-md p-3" data-testid="fba-lot-preview">Inbound / birim: {unitUsd(inboundUnit)} · Landed birim: {unitUsd(inboundUnit == null ? null : unit + inboundUnit)} · Stok değeri: {usd(inboundUnit == null ? null : qty * (unit + inboundUnit))}</p>}
        {locked && <p className="text-xs text-amber-700">Satışa tahsis edilmiş lotta SKU, alış tarihi ve ürün maliyeti kilitlidir; miktar/inbound için Düzeltme kullanın.</p>}
        <FormError error={error} id="fba-lot-error" />
        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="fba-lot-cancel">Vazgeç</Button>
          <Button onClick={save} disabled={saving} className="bg-emerald-600 hover:bg-emerald-700 text-white" data-testid="fba-lot-save">{saving ? "Kaydediliyor…" : "Kaydet"}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

const ADJUST = [
  { value: "increase_quantity", label: "Adet artır", input: "Eklenecek adet" },
  { value: "decrease_quantity", label: "Adet azalt (kayıp/hasar)", input: "Düşülecek adet" },
  { value: "correct_remaining", label: "Kalan adedi düzelt", input: "Yeni kalan adet" },
  { value: "update_inbound_shipping", label: "Inbound kargoyu güncelle", input: "Yeni inbound toplamı (USD)" },
  { value: "close_lot", label: "Lotu kapat", input: null },
];

export const AdjustDialog = ({ lot, onClose, onSaved }) => {
  const [type, setType] = useState("increase_quantity");
  const [value, setValue] = useState("");
  const [note, setNote] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { setType("increase_quantity"); setValue(""); setNote(""); setError(""); }, [lot]);
  const meta = ADJUST.find(a => a.value === type);
  const save = async () => {
    setError("");
    try {
      await api.post(`/fba/lots/${lot.id}/adjust`, { adjustment_type: type, value: meta.input ? Number(value) : null, note });
      toast.success("Düzeltme kaydedildi (denetim kaydı oluşturuldu)");
      onSaved(); onClose();
    } catch (e) { setError(apiError(e)); }
  };
  return (
    <Dialog open={!!lot} onOpenChange={v => !v && onClose()}>
      <DialogContent className="bg-white" data-testid="fba-adjust-dialog">
        <DialogHeader><DialogTitle>Stok Düzeltmesi · {lot?.lot_code}</DialogTitle>
          <DialogDescription>Kalan: {lot?.remaining_quantity} / {lot?.original_quantity} · Her düzeltme denetim kaydı oluşturur.</DialogDescription></DialogHeader>
        <SelectField label="Düzeltme Türü" id="fba-adjust-type" value={type} onChange={setType} options={ADJUST.map(({ value: v, label }) => ({ value: v, label }))} />
        {meta.input && <TextField label={meta.input} id="fba-adjust-value" type="number" min="0" value={value} onChange={setValue} />}
        <TextField label="Neden / Not (opsiyonel)" id="fba-adjust-note" value={note} onChange={setNote} />
        <FormError error={error} id="fba-adjust-error" />
        <DialogFooter>
          <Button variant="outline" onClick={onClose} data-testid="fba-adjust-cancel">Vazgeç</Button>
          <Button onClick={save} variant={type === "close_lot" ? "destructive" : "default"} data-testid="fba-adjust-save">Uygula</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
};

export const LotHistoryDialog = ({ lot, onClose }) => {
  const [data, setData] = useState(null);
  useEffect(() => { setData(null); if (lot) api.get(`/fba/lots/${lot.id}/history`).then(({ data: d }) => setData(d)).catch(() => setData({ adjustments: [], allocations: [] })); }, [lot]);
  const fmt = v => v == null ? "—" : typeof v === "object" ? Object.entries(v).map(([k, x]) => `${k}: ${x}`).join(", ") : String(v);
  return (
    <Dialog open={!!lot} onOpenChange={v => !v && onClose()}>
      <DialogContent className="bg-white max-w-3xl max-h-[80vh] overflow-y-auto" data-testid="fba-history-dialog">
        <DialogHeader><DialogTitle>Lot Geçmişi · {lot?.lot_code}</DialogTitle><DialogDescription>{lot?.sku} · {lot?.product_name}</DialogDescription></DialogHeader>
        <h4 className="text-sm font-semibold">Düzeltmeler / Denetim</h4>
        <ul className="space-y-2 text-xs" data-testid="fba-history-adjustments">
          {(data?.adjustments || []).map(a => <li key={a.id} className="border border-slate-200 rounded-md p-2"><strong>{a.adjustment_type}</strong> · {a.timestamp?.slice(0, 19).replace("T", " ")} · {a.user_email}<br />Önce: {fmt(a.previous_value)}<br />Sonra: {fmt(a.new_value)}{a.note && <><br />Not: {a.note}</>}</li>)}
          {data && !data.adjustments.length && <li className="text-slate-500">Kayıt yok</li>}
        </ul>
        <h4 className="text-sm font-semibold mt-2">FIFO Tüketimleri</h4>
        <ul className="space-y-1 text-xs" data-testid="fba-history-allocations">
          {(data?.allocations || []).map(a => <li key={a.id} className={a.status !== "active" ? "line-through text-slate-400" : ""}>{a.order_date} · <span className="font-mono">{a.amazon_order_id}</span> · {a.quantity} adet × {unitUsd(a.landed_unit_cost_usd)} = {usd(a.total_allocated_cost_usd)}{a.status !== "active" && " (geri alındı)"}</li>)}
          {data && !data.allocations.length && <li className="text-slate-500">Henüz tüketim yok</li>}
        </ul>
      </DialogContent>
    </Dialog>
  );
};
