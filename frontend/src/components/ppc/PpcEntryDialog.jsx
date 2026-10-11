import { useEffect, useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useCategories } from "@/hooks/useCategories";
import { SelectField, TextField, FormError, apiError } from "@/components/company/Fields";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { FINANCE_NOTE } from "./ppcFormat";

const AD_TYPES = ["Sponsored Products", "Sponsored Brands", "Sponsored Display", "Diğer"];
const blank = mp => ({ date: new Date().toISOString().slice(0, 10), marketplace: mp, ppc_category: "PPC Reklam Harcaması", campaign: "", ad_type: "Sponsored Products", asin: "", sku: "", ad_spend_usd: "", ppc_sales_usd: "", clicks: "", impressions: "", orders: "", notes: "" });

const useAsinLookup = (storeId, asin) => {
  const [info, setInfo] = useState(null);
  useEffect(() => {
    const key = asin.trim();
    if (!storeId || key.length < 10) { setInfo(null); return; }
    const t = setTimeout(() => api.get("/ppc/asin-lookup", { params: { store_id: storeId, asin: key } }).then(r => setInfo(r.data)).catch(() => setInfo(null)), 350);
    return () => clearTimeout(t);
  }, [storeId, asin]);
  return info;
};

export const PpcEntryDialog = ({ open, onOpenChange, storeId, marketplaces, onSaved }) => {
  const [form, setForm] = useState(blank(""));
  const [error, setError] = useState("");
  const { byType } = useCategories(storeId);
  const cats = byType(undefined, "ppc").map(c => c.name);
  const info = useAsinLookup(storeId, form.asin);
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  useEffect(() => { if (open) { setForm(blank(marketplaces[0] || "")); setError(""); } }, [open]);
  useEffect(() => { if (info?.skus?.length === 1 && !form.sku) set("sku", info.skus[0]); }, [info]);

  const submit = async (e) => {
    e.preventDefault(); setError("");
    if (!storeId) { setError("Önce tek bir mağaza seçin"); return; }
    if (!form.asin.trim() && !form.campaign.trim()) { setError("ASIN veya kampanya gerekli"); return; }
    if (form.ad_spend_usd === "" || !(Number(form.ad_spend_usd) >= 0)) { setError("Geçerli reklam harcaması girin"); return; }
    try {
      await api.post("/ppc/attributions", {
        ...form, store_id: storeId,
        ad_spend_usd: Number(form.ad_spend_usd), ppc_sales_usd: Number(form.ppc_sales_usd) || 0,
        clicks: Number(form.clicks) || 0, impressions: Number(form.impressions) || 0, orders: Number(form.orders) || 0,
      });
      toast.success("PPC kaydı eklendi (finansal gider oluşturulmaz)");
      onOpenChange(false); onSaved();
    } catch (err) { setError(apiError(err)); }
  };

  const catOptions = [...new Set(["PPC Reklam Harcaması", ...cats])].map(c => ({ value: c, label: c }));
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-white max-w-2xl max-h-[90vh] overflow-y-auto" data-testid="ppc-dialog">
        <DialogHeader>
          <DialogTitle>Manuel PPC Kaydı</DialogTitle>
          <DialogDescription>{FINANCE_NOTE}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <TextField label="Tarih" id="ppc-f-date" type="date" value={form.date} onChange={v => set("date", v)} required />
            <SelectField label="Pazar Yeri" id="ppc-f-marketplace" value={form.marketplace} onChange={v => set("marketplace", v)} options={marketplaces.map(c => ({ value: c, label: c }))} />
            <SelectField label="PPC Kategori" id="ppc-f-category" value={form.ppc_category} onChange={v => set("ppc_category", v)} options={catOptions} />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <TextField label="Kampanya Adı" id="ppc-f-campaign" value={form.campaign} onChange={v => set("campaign", v)} placeholder="Kampanya adı" />
            <SelectField label="Reklam Tipi" id="ppc-f-adtype" value={form.ad_type} onChange={v => set("ad_type", v)} options={AD_TYPES.map(t => ({ value: t, label: t }))} />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <TextField label="ASIN" id="ppc-f-asin" value={form.asin} onChange={v => set("asin", v.toUpperCase())} placeholder="B0..." />
              {info && <p className="text-xs mt-1 text-slate-500" data-testid="ppc-f-asin-info">{info.found ? `FBA: ${info.product_name || "ürün"} · SKU: ${info.skus.join(", ") || "—"}` : "FBA verisinde bulunamadı"}</p>}
            </div>
            <TextField label="SKU" id="ppc-f-sku" value={form.sku} onChange={v => set("sku", v)} list="ppc-sku-options" />
            <datalist id="ppc-sku-options">{(info?.skus || []).map(s => <option key={s} value={s} />)}</datalist>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <TextField label="Reklam Harcaması (USD)" id="ppc-f-spend" type="number" step="0.01" min="0" value={form.ad_spend_usd} onChange={v => set("ad_spend_usd", v)} required />
            <TextField label="PPC Satışı (USD)" id="ppc-f-sales" type="number" step="0.01" min="0" value={form.ppc_sales_usd} onChange={v => set("ppc_sales_usd", v)} />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <TextField label="Tıklama" id="ppc-f-clicks" type="number" min="0" value={form.clicks} onChange={v => set("clicks", v)} />
            <TextField label="Gösterim" id="ppc-f-impressions" type="number" min="0" value={form.impressions} onChange={v => set("impressions", v)} />
            <TextField label="PPC Sipariş" id="ppc-f-orders" type="number" min="0" value={form.orders} onChange={v => set("orders", v)} />
          </div>
          <TextField label="Açıklama / Not" id="ppc-f-notes" value={form.notes} onChange={v => set("notes", v)} />
          <FormError error={error} id="ppc-f-error" />
          <DialogFooter>
            <Button type="submit" className="bg-pink-600 hover:bg-pink-700 text-white rounded-xl" data-testid="ppc-f-submit">Kaydet</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};
