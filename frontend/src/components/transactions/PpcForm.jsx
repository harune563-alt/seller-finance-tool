import { useState } from "react";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { useFormMarketplace } from "@/hooks/useFormMarketplace";
import { useCategories } from "@/hooks/useCategories";
import { MP_BY_CODE } from "@/constants/marketplaces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { useFxQuote } from "@/hooks/useFxQuote";
import { FxStatus, formatUsd } from "@/components/FxStatus";

const AD_TYPES = ["Sponsored Products", "Sponsored Brands", "Sponsored Display", "Diğer"];

const blankForm = () => ({
  date: new Date().toISOString().slice(0, 10),
  category: "", amount: "", description: "",
  campaign_name: "", ad_type: "Sponsored Products", asin_sku: "",
  clicks: "", impressions: "", orders_count: "",
  aggregate_mode: true,
});

/**
 * PPC form supports:
 *  - Daily aggregate: single row per campaign/day with ad metrics
 *  - Per-event: one record per cost/order event
 */
export const PpcForm = ({ onSaved }) => {
  const { activeStore, activeStoreId } = useStore();
  const { marketplace, currency, selectMarketplace } = useFormMarketplace();
  const { byType } = useCategories(activeStoreId);
  const ppcCategories = byType(undefined, "ppc");
  const [form, setForm] = useState(blankForm);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const fx = useFxQuote(currency, form.date);
  const amountUsd = fx.quote ? Math.round(Number(form.amount || 0) * Number(fx.quote.rate) * 100) / 100 : null;

  const activeCategory = ppcCategories.find((c) => c.name === form.category) || ppcCategories[0];
  const txType = activeCategory?.type || "expense";

  const change = (key, value) => { setForm((f) => ({ ...f, [key]: value })); setError(""); };

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (!activeStoreId || !activeStore?.marketplaces?.includes(marketplace)) { setError("Geçerli bir mağaza ve pazar yeri seçin."); return; }
    if (!fx.quote) { setError("Kayıt için otomatik kurun alınması gerekiyor."); return; }
    if (!form.category || !ppcCategories.find((c) => c.name === form.category)) { setError("Önce bir PPC kategorisi seçin."); return; }
    if (!Number.isFinite(Number(form.amount)) || Number(form.amount) <= 0) { setError("Tutar 0'dan büyük olmalı."); return; }
    const payload = {
      store_id: activeStoreId, marketplace, currency,
      type: txType, category: form.category, section: "ppc",
      amount: Number(form.amount), date: form.date,
      description: form.description, order_id: "",
      campaign_name: form.campaign_name.trim(),
      ad_type: form.ad_type,
      asin_sku: form.asin_sku.trim(),
      clicks: Number(form.clicks) || 0,
      impressions: Number(form.impressions) || 0,
      orders_count: Number(form.orders_count) || 0,
    };
    setSaving(true);
    try {
      await api.post("/transactions", payload);
      toast.success(form.aggregate_mode ? "PPC günlük kaydı eklendi" : "PPC işlemi eklendi");
      setForm((f) => ({ ...blankForm(), aggregate_mode: f.aggregate_mode, category: f.category, campaign_name: f.campaign_name, ad_type: f.ad_type, asin_sku: f.asin_sku, date: f.date }));
      onSaved?.();
    } catch (err) {
      setError(err?.response?.data?.detail || "Kayıt başarısız");
    } finally { setSaving(false); }
  };

  return (
    <form onSubmit={submit} noValidate className="border-y border-slate-200 bg-white px-4 sm:px-6 py-6 space-y-6" data-testid="ppc-form">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h2 className="font-display font-semibold text-base">PPC Reklam Kaydı</h2>
        <div className="flex items-center gap-3" data-testid="ppc-mode-toggle">
          <Label htmlFor="ppc-mode" className="text-sm text-slate-500">
            {form.aggregate_mode ? "Mod: Günlük toplam" : "Mod: Her olay tekil"}
          </Label>
          <Switch id="ppc-mode" checked={form.aggregate_mode} onCheckedChange={(v) => change("aggregate_mode", v)} data-testid="ppc-mode-switch" />
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div>
          <Label htmlFor="ppc-date">Tarih</Label>
          <Input id="ppc-date" type="date" value={form.date} onChange={(e) => change("date", e.target.value)} data-testid="ppc-date-input" className="mt-2" />
        </div>
        <div>
          <Label htmlFor="ppc-marketplace">Pazar Yeri</Label>
          <Select value={marketplace} onValueChange={selectMarketplace}>
            <SelectTrigger id="ppc-marketplace" data-testid="ppc-marketplace-select" className="mt-2"><SelectValue placeholder="Pazar seçin" /></SelectTrigger>
            <SelectContent data-testid="ppc-marketplace-options">
              {(activeStore?.marketplaces || []).map((c) => (
                <SelectItem key={c} value={c} data-testid={`ppc-marketplace-${c.toLowerCase()}`}>{MP_BY_CODE[c]?.flag} {MP_BY_CODE[c]?.name}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor="ppc-category">Kategori</Label>
          <Select value={form.category} onValueChange={(v) => change("category", v)}>
            <SelectTrigger id="ppc-category" data-testid="ppc-category-select" className="mt-2"><SelectValue placeholder="PPC Kategori" /></SelectTrigger>
            <SelectContent data-testid="ppc-category-options">
              {ppcCategories.map((c) => <SelectItem key={c.id} value={c.name}>{c.name} ({c.type === "income" ? "Gelir" : "Gider"})</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor="ppc-amount">Tutar ({currency || "—"})</Label>
          <Input id="ppc-amount" type="number" step="0.01" min="0.01" value={form.amount} onChange={(e) => change("amount", e.target.value)} data-testid="ppc-amount-input" className="mt-2 font-mono-num" placeholder="0.00" />
          <p className="text-xs text-slate-500 mt-1" data-testid="ppc-amount-usd">USD karşılığı: {formatUsd(amountUsd)}</p>
        </div>
        <div className="sm:col-span-2">
          <Label htmlFor="ppc-campaign">Kampanya Adı</Label>
          <Input id="ppc-campaign" value={form.campaign_name} onChange={(e) => change("campaign_name", e.target.value)} data-testid="ppc-campaign-input" className="mt-2" placeholder="Örn: Winter Sale 2026" />
        </div>
        <div>
          <Label htmlFor="ppc-adtype">Reklam Tipi</Label>
          <Select value={form.ad_type} onValueChange={(v) => change("ad_type", v)}>
            <SelectTrigger id="ppc-adtype" data-testid="ppc-adtype-select" className="mt-2"><SelectValue /></SelectTrigger>
            <SelectContent>{AD_TYPES.map((t) => <SelectItem key={t} value={t}>{t}</SelectItem>)}</SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor="ppc-asin">ASIN / SKU</Label>
          <Input id="ppc-asin" value={form.asin_sku} onChange={(e) => change("asin_sku", e.target.value)} data-testid="ppc-asin-input" className="mt-2" placeholder="B0XXXXXX veya SKU" />
        </div>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 border-t border-slate-100 pt-5">
        <div>
          <Label htmlFor="ppc-clicks">Tıklama</Label>
          <Input id="ppc-clicks" type="number" min="0" step="1" value={form.clicks} onChange={(e) => change("clicks", e.target.value)} data-testid="ppc-clicks-input" className="mt-2 font-mono-num" placeholder="0" />
        </div>
        <div>
          <Label htmlFor="ppc-impr">Gösterim</Label>
          <Input id="ppc-impr" type="number" min="0" step="1" value={form.impressions} onChange={(e) => change("impressions", e.target.value)} data-testid="ppc-impr-input" className="mt-2 font-mono-num" placeholder="0" />
        </div>
        <div>
          <Label htmlFor="ppc-orders">Sipariş Sayısı</Label>
          <Input id="ppc-orders" type="number" min="0" step="1" value={form.orders_count} onChange={(e) => change("orders_count", e.target.value)} data-testid="ppc-orders-input" className="mt-2 font-mono-num" placeholder="0" />
        </div>
      </div>
      <div>
        <Label htmlFor="ppc-desc">Açıklama</Label>
        <Input id="ppc-desc" value={form.description} onChange={(e) => change("description", e.target.value)} data-testid="ppc-desc-input" className="mt-2" />
      </div>
      <FxStatus quote={fx.quote} loading={fx.loading} error={fx.error} retry={fx.retry} />
      {error && <p role="alert" data-testid="ppc-form-error" className="text-sm text-rose-700 bg-rose-50 p-3 rounded-md">{error}</p>}
      <div className="flex justify-end">
        <Button type="submit" disabled={saving || !activeStoreId || !fx.quote || ppcCategories.length === 0} data-testid="ppc-submit" className="bg-rose-600 hover:bg-rose-700 text-white">
          <Plus className="w-4 h-4 mr-2" /> {saving ? "Kaydediliyor…" : "PPC Kaydet"}
        </Button>
      </div>
    </form>
  );
};
