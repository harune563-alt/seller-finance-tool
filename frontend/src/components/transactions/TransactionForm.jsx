import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { useFormMarketplace } from "@/hooks/useFormMarketplace";
import { MP_BY_CODE, TRANSACTION_CATEGORIES, COST_FIELDS, RECOVERY_FIELDS, formatMoney } from "@/constants/marketplaces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { CostFields } from "./CostFields";

const blank = () => ({ date: new Date().toISOString().slice(0, 10), category: "Order payments", amount: "", order_id: "", description: "", product_cost: "", shipping_cost: "", extra_cost: "", product_cost_recovery: "", shipping_cost_recovery: "" });
export const TransactionForm = ({ onSaved }) => {
  const { activeStore, activeStoreId, activeMarketplace } = useStore();
  const [form, setForm] = useState(blank);
  const { marketplace, currency, selectMarketplace } = useFormMarketplace();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    setForm(blank()); setError("");
  }, [activeStoreId, activeMarketplace]);
  const isIncome = form.category === "Order payments";
  const isRefund = form.category === "Refunds";
  const costs = COST_FIELDS.reduce((total, { key }) => total + (Number(form[key]) || 0), 0);
  const recovered = RECOVERY_FIELDS.reduce((total, { key }) => total + (Number(form[key]) || 0), 0);
  const change = (key, value) => { setForm(f => ({ ...f, [key]: value })); setError(""); };
  const submit = async e => {
    e.preventDefault(); setError("");
    if (!activeStoreId || !activeStore?.marketplaces?.includes(marketplace)) { setError("Geçerli bir mağaza ve pazar yeri seçin."); return; }
    if (!form.date || !TRANSACTION_CATEGORIES.includes(form.category) || !Number.isFinite(Number(form.amount)) || Number(form.amount) <= 0) { setError("Tarih, işlem türü ve sıfırdan büyük bir tutar girin."); return; }
    if (isIncome && COST_FIELDS.some(({ key }) => !Number.isFinite(Number(form[key])) || Number(form[key]) < 0)) { setError("Maliyetler sıfır veya pozitif olmalıdır."); return; }
    if (isRefund && RECOVERY_FIELDS.some(({ key }) => !Number.isFinite(Number(form[key])) || Number(form[key]) < 0)) { setError("Geri alınan tutarlar sıfır veya pozitif olmalıdır."); return; }
    setSaving(true);
    try {
      await api.post("/transactions", { ...form, store_id: activeStoreId, marketplace, currency, type: isIncome ? "income" : "expense", amount: Number(form.amount),
        ...Object.fromEntries(COST_FIELDS.map(({ key }) => [key, isIncome ? Number(form[key]) : 0])),
        ...Object.fromEntries(RECOVERY_FIELDS.map(({ key }) => [key, isRefund ? Number(form[key]) : 0])), order_id: form.order_id.trim() });
      toast.success("İşlem kaydedildi"); setForm(f => ({ ...blank(), category: f.category, date: f.date })); onSaved();
    } catch (err) { const detail = err.response?.data?.detail; setError(typeof detail === "string" ? detail : "Kayıt başarısız. Alanları kontrol edin."); }
    finally { setSaving(false); }
  };
  return <form onSubmit={submit} noValidate className="border-y border-slate-200 bg-white px-4 sm:px-6 py-6 space-y-6" data-testid="transaction-form">
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      <div><Label htmlFor="tx-date">Tarih</Label><Input id="tx-date" type="date" value={form.date} onChange={e => change("date", e.target.value)} data-testid="tx-date-input" className="mt-2" /></div>
      <div><Label htmlFor="tx-marketplace">Pazar Yeri</Label><Select value={marketplace} onValueChange={selectMarketplace}>
        <SelectTrigger id="tx-marketplace" data-testid="tx-marketplace-select" className="mt-2"><SelectValue placeholder="Pazar seçin" /></SelectTrigger>
        <SelectContent data-testid="tx-marketplace-options">{(activeStore?.marketplaces || []).map(c => <SelectItem key={c} value={c} data-testid={`tx-marketplace-${c.toLowerCase()}`}>{MP_BY_CODE[c]?.flag} {MP_BY_CODE[c]?.name}</SelectItem>)}</SelectContent>
      </Select></div>
      <div><Label htmlFor="tx-category">İşlem Türü</Label><Select value={form.category} onValueChange={v => { if (TRANSACTION_CATEGORIES.includes(v)) change("category", v); }}>
        <SelectTrigger id="tx-category" data-testid="tx-category-select" className="mt-2"><SelectValue /></SelectTrigger>
        <SelectContent data-testid="tx-category-options">{TRANSACTION_CATEGORIES.map((c, i) => <SelectItem key={c} value={c} data-testid={`tx-category-${i}`}>{c}</SelectItem>)}</SelectContent>
      </Select></div>
      <div><Label htmlFor="tx-amount">{isIncome ? "Gelir" : isRefund ? "Müşteriye İade" : "Gider"} Tutarı ({currency || "—"})</Label><div className="relative mt-2">{!isIncome && <span className="absolute left-3 top-2 text-rose-600 font-semibold" aria-hidden="true">−</span>}<Input id="tx-amount" type="number" step="0.01" min="0.01" value={form.amount} onChange={e => change("amount", e.target.value)} data-testid="tx-amount-input" className={`font-mono-num ${!isIncome ? "pl-7 text-rose-600" : ""}`} placeholder="0.00" /></div></div>
      <div><Label htmlFor="tx-order">Order ID</Label><Input id="tx-order" value={form.order_id} onChange={e => change("order_id", e.target.value)} data-testid="tx-order-input" className="mt-2" /></div>
      <div className="sm:col-span-2 lg:col-span-3"><Label htmlFor="tx-description">Açıklama</Label><Input id="tx-description" value={form.description} onChange={e => change("description", e.target.value)} data-testid="tx-description-input" className="mt-2" /></div>
    </div>
    {isIncome && <div className="border-t border-slate-100 pt-5 space-y-4">
      <h2 className="font-display font-semibold text-base">Maliyetler</h2>
      <CostFields value={form} onChange={setForm} currency={currency} />
      <div className="flex justify-between gap-4 flex-wrap text-sm" data-testid="tx-form-preview"><span className="text-slate-500">Toplam maliyet: <strong data-testid="tx-preview-costs">{formatMoney(costs, currency)}</strong></span><span>Bu kaydın net kârı: <strong className={Number(form.amount) - costs < 0 ? "text-rose-600" : "text-emerald-700"} data-testid="tx-preview-net-profit">{formatMoney(Number(form.amount) - costs, currency)}</strong></span></div>
    </div>}
    {isRefund && <div className="border-t border-slate-100 pt-5 space-y-4" data-testid="refund-recovery-section">
      <h2 className="font-display font-semibold text-base">İade Sonrası Geri Kazanımlar</h2>
      <CostFields value={form} onChange={setForm} currency={currency} fields={RECOVERY_FIELDS} />
      <div className="flex justify-between gap-4 flex-wrap text-sm"><span className="text-slate-500">Geri alınan toplam: <strong className="text-emerald-700" data-testid="tx-preview-recovered">{formatMoney(recovered, currency)}</strong></span><span>Bu iadenin kâr/zarar etkisi: <strong data-testid="tx-refund-net-impact" className={recovered - Number(form.amount) < 0 ? "text-rose-600" : "text-emerald-700"}>{formatMoney(recovered - Number(form.amount), currency)}</strong></span></div>
    </div>}
    {error && <p role="alert" data-testid="tx-form-error" className="text-sm text-rose-700 bg-rose-50 p-3 rounded-md">{error}</p>}
    <div className="flex justify-end"><Button type="submit" disabled={saving || !activeStoreId} data-testid="tx-submit-button" className={isIncome ? "bg-emerald-600 hover:bg-emerald-700 text-white" : "bg-rose-600 hover:bg-rose-700 text-white"}><Plus className="w-4 h-4 mr-2" />{saving ? "Kaydediliyor…" : isIncome ? "Gelir Kaydet" : "Gider Kaydet"}</Button></div>
  </form>;
};