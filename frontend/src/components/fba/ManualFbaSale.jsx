import { useEffect, useRef, useState } from "react";
import api from "@/lib/api";
import { useCategories } from "@/hooks/useCategories";
import { Button } from "@/components/ui/button";
import { TextField, FormError, apiError } from "@/components/company/Fields";
import { SelectField } from "@/components/company/Fields";
import { usd } from "@/components/fba/common";
import { Package, Search, AlertTriangle } from "lucide-react";
import { toast } from "sonner";

const EMPTY = { sku: "", asin: "", product_name: "", quantity: "1", amount: "", order_id: "", date: new Date().toISOString().slice(0, 10) };

export const ManualFbaSale = ({ storeId, marketplaces, onSaved }) => {
  const [form, setForm] = useState(EMPTY);
  const [marketplace, setMarketplace] = useState(marketplaces?.[0] || "US");
  const { byType } = useCategories(storeId);
  const fbaCategories = byType(undefined, "fba");
  const [category, setCategory] = useState("FBA Satış");
  const [lookup, setLookup] = useState(null);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const debounce = useRef(null);

  useEffect(() => { if (marketplaces?.length && !marketplaces.includes(marketplace)) setMarketplace(marketplaces[0]); }, [marketplaces, marketplace]);

  // SKU lookup + FIFO preview (debounced) whenever SKU or quantity changes.
  useEffect(() => {
    if (debounce.current) clearTimeout(debounce.current);
    const sku = form.sku.trim();
    const qty = parseInt(form.quantity, 10) || 0;
    if (!sku || !storeId) { setLookup(null); setPreview(null); return; }
    debounce.current = setTimeout(async () => {
      try {
        const { data } = await api.get("/fba/sku-lookup", { params: { store_id: storeId, sku, quantity: qty } });
        setLookup(data);
        setPreview(data.fifo_preview);
        setForm(f => ({ ...f, asin: f.asin || data.asin || "", product_name: f.product_name || data.product_name || "" }));
      } catch { setLookup(null); setPreview(null); }
    }, 350);
    return () => debounce.current && clearTimeout(debounce.current);
  }, [form.sku, form.quantity, storeId]);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    const qty = parseInt(form.quantity, 10) || 0;
    const amount = Number(form.amount);
    if (!form.sku.trim()) { setError("SKU gerekli"); return; }
    if (qty <= 0) { setError("Adet 0'dan büyük olmalı"); return; }
    if (!(amount > 0)) { setError("Satış tutarı 0'dan büyük olmalı"); return; }
    if (preview && !preview.sufficient) { setError(`Yetersiz FBA stok — mevcut ${preview.available_stock}, istenen ${qty}`); return; }
    setSaving(true);
    try {
      const { data } = await api.post("/fba/manual-sale", {
        store_id: storeId, marketplace, sku: form.sku.trim(), asin: form.asin.trim(),
        product_name: form.product_name.trim(), quantity: qty, amount,
        order_id: form.order_id.trim(), date: form.date, currency: "CAD", category,
      });
      toast.success(`Manuel FBA satışı kaydedildi · ${data.order_id}`);
      setForm(EMPTY); setLookup(null); setPreview(null);
      onSaved && onSaved();
    } catch (err) {
      const d = err.response?.data?.detail;
      setError(typeof d === "object" ? (d.error || "Kayıt başarısız") : apiError(err));
    } finally { setSaving(false); }
  };

  const insufficient = preview && !preview.sufficient;

  return (
    <div className="rounded-2xl bg-white border border-slate-200 p-5 space-y-4" data-testid="manual-fba-sale">
      <div className="flex items-center gap-2">
        <div className="w-9 h-9 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center"><Package className="w-4 h-4" /></div>
        <div>
          <h3 className="font-display font-bold text-slate-900">Manuel FBA Satışı</h3>
          <p className="text-xs text-slate-500">SKU/ASIN seç — FIFO maliyeti otomatik hesaplanır, ürün maliyeti girmene gerek yok.</p>
        </div>
      </div>

      <form onSubmit={submit} className="space-y-4">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <TextField label="SKU" id="mfba-sku" value={form.sku} onChange={v => setForm({ ...form, sku: v })} placeholder="örn. ABC-123" required />
          <TextField label="ASIN" id="mfba-asin" value={form.asin} onChange={v => setForm({ ...form, asin: v })} placeholder="Otomatik dolar" />
          <SelectField label="Pazar Yeri" id="mfba-marketplace" value={marketplace} onChange={setMarketplace}
            options={(marketplaces || []).map(c => ({ value: c, label: c }))} />
          <SelectField label="Kategori" id="mfba-category" value={category} onChange={setCategory}
            options={(fbaCategories.length ? fbaCategories.map(c => c.name) : ["FBA Satış"]).map(n => ({ value: n, label: n }))} />
        </div>
        <TextField label="Ürün Adı" id="mfba-product" value={form.product_name} onChange={v => setForm({ ...form, product_name: v })} placeholder="Otomatik dolar" />
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
          <TextField label="Adet" id="mfba-quantity" type="number" min="1" value={form.quantity} onChange={v => setForm({ ...form, quantity: v })} required />
          <TextField label="Satış Tutarı (Amazon Net · CAD)" id="mfba-amount" type="number" step="0.01" min="0.01" value={form.amount} onChange={v => setForm({ ...form, amount: v })} placeholder="0.00 CAD" required />
          <TextField label="Order ID (opsiyonel)" id="mfba-order" value={form.order_id} onChange={v => setForm({ ...form, order_id: v })} placeholder="Boş bırak = otomatik" />
          <TextField label="Tarih" id="mfba-date" type="date" value={form.date} onChange={v => setForm({ ...form, date: v })} required />
        </div>

        {lookup && (
          <div className="rounded-xl bg-slate-50 border border-slate-200 p-3 text-sm" data-testid="mfba-lookup">
            <div className="flex items-center gap-2 text-slate-600"><Search className="w-4 h-4" />
              <span>Stok: <b data-testid="mfba-remaining">{lookup.remaining_units}</b> adet · <b>{lookup.open_lots}</b> açık lot</span>
            </div>
          </div>
        )}

        {preview && (
          <div className={`rounded-xl border p-4 ${insufficient ? "bg-rose-50 border-rose-200" : "bg-emerald-50/50 border-emerald-200"}`} data-testid="mfba-preview">
            {insufficient ? (
              <div className="flex items-center gap-2 text-rose-700 font-semibold" data-testid="mfba-insufficient">
                <AlertTriangle className="w-4 h-4" /> Yetersiz FBA Stok — mevcut {preview.available_stock}, istenen {preview.requested_quantity} (eksik {preview.shortfall})
              </div>
            ) : (
              <>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                  <div><div className="text-xs text-slate-500">İstenen Adet</div><div className="font-mono-num font-semibold">{preview.requested_quantity}</div></div>
                  <div><div className="text-xs text-slate-500">FIFO Ürün Maliyeti</div><div className="font-mono-num font-semibold" data-testid="mfba-product-cost">{usd(preview.product_cost_usd)}</div></div>
                  <div><div className="text-xs text-slate-500">FIFO Inbound</div><div className="font-mono-num font-semibold" data-testid="mfba-inbound-cost">{usd(preview.inbound_cost_usd)}</div></div>
                  <div><div className="text-xs text-slate-500">Toplam FIFO Maliyeti</div><div className="font-mono-num font-semibold text-indigo-700" data-testid="mfba-total-cost">{usd(preview.total_fifo_cost_usd)}</div></div>
                </div>
                <div className="mt-3 border-t border-emerald-200 pt-2">
                  <div className="text-xs text-slate-500 mb-1">Lot dağılımı (FIFO):</div>
                  <div className="space-y-1">
                    {preview.allocations.map((a, i) => (
                      <div key={a.lot_id} className="text-xs font-mono-num text-slate-600" data-testid={`mfba-alloc-${i}`}>
                        {a.lot_code || a.lot_id.slice(0, 8)} · {a.quantity} adet × {usd(a.landed_unit_cost_usd)} = {usd(a.total_cost_usd)}
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        )}

        <FormError error={error} id="mfba-error" />
        <Button type="submit" disabled={saving || insufficient} className="bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl" data-testid="mfba-submit">
          {saving ? "Kaydediliyor…" : "FBA Satışını Kaydet"}
        </Button>
      </form>
    </div>
  );
};
