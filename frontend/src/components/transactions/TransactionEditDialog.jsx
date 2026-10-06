import { useState } from "react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { MP_BY_CODE, TRANSACTION_CATEGORIES, COST_FIELDS, RECOVERY_FIELDS, formatMoney } from "@/constants/marketplaces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { CostFields } from "./CostFields";
import { FxStatus, formatUsd } from "@/components/FxStatus";
import { useFxQuote } from "@/hooks/useFxQuote";

const PAYOUT_STATUSES = ["Oluşturuldu", "İşleniyor", "Bankada"];

const initialForm = row => ({
  date: row.date || "",
  marketplace: row.marketplace || "",
  category: row.category || "",
  amount: row.amount ?? "",
  order_id: row.order_id || "",
  payment_reference: row.payment_reference || "",
  description: row.description || "",
  product_cost: row.usd_costs?.product_cost ?? 0,
  shipping_cost: row.usd_costs?.shipping_cost ?? 0,
  extra_cost: row.usd_costs?.extra_cost ?? 0,
  product_cost_recovery: row.usd_costs?.product_cost_recovery ?? 0,
  shipping_cost_recovery: row.usd_costs?.shipping_cost_recovery ?? 0,
});

export const TransactionEditDialog = ({ row, onClose, onSaved }) => {
  const { activeStoreId, activeStore } = useStore();
  const [form, setForm] = useState(() => initialForm(row));
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const isPayout = row.type === "payout";
  const currency = MP_BY_CODE[form.marketplace]?.currency || row.currency || "";
  const isIncome = !isPayout && form.category === "Order payments";
  const isRefund = !isPayout && form.category === "Refunds";
  const fields = isIncome ? COST_FIELDS : isRefund ? RECOVERY_FIELDS : [];
  const fx = useFxQuote(isPayout ? "" : currency, form.date);
  const costs = fields.reduce((sum, { key }) => sum + (Number(form[key]) || 0), 0);
  const amountUsd = isPayout || !fx.quote ? null : Math.round(Number(form.amount || 0) * Number(fx.quote.rate) * 100) / 100;
  const change = (key, value) => { setForm(current => ({ ...current, [key]: value })); setError(""); };
  const setCategory = value => {
    if (!isPayout && TRANSACTION_CATEGORIES.includes(value)) change("category", value);
    if (isPayout && PAYOUT_STATUSES.includes(value)) change("category", value);
  };
  const save = async event => {
    event.preventDefault();
    const amount = Number(form.amount);
    if (!activeStoreId || !activeStore?.marketplaces?.includes(form.marketplace)) { setError("Geçerli bir mağaza ve pazar yeri seçin."); return; }
    if (!form.date || !Number.isFinite(amount) || amount <= 0) { setError("Tarih ve sıfırdan büyük bir tutar girin."); return; }
    if (!isPayout && !fx.quote) { setError("Güncelleme için otomatik kurun alınması gerekiyor."); return; }
    if (isIncome && fields.some(({ key }) => !Number.isFinite(Number(form[key])) || Number(form[key]) < 0)) { setError("Maliyetler sıfır veya pozitif olmalıdır."); return; }
    if (isRefund && fields.some(({ key }) => !Number.isFinite(Number(form[key])) || Number(form[key]) < 0)) { setError("Geri kazanımlar sıfır veya pozitif olmalıdır."); return; }
    setSaving(true); setError("");
    const payload = {
      store_id: activeStoreId,
      marketplace: form.marketplace,
      type: isPayout ? "payout" : isIncome ? "income" : "expense",
      category: form.category,
      amount,
      currency,
      date: form.date,
      description: form.description,
      order_id: isPayout ? "" : form.order_id.trim(),
      payment_reference: isPayout ? form.payment_reference.trim() : "",
      ...Object.fromEntries(COST_FIELDS.map(({ key }) => [key, isIncome ? Number(form[key]) : 0])),
      ...Object.fromEntries(RECOVERY_FIELDS.map(({ key }) => [key, isRefund ? Number(form[key]) : 0])),
    };
    try {
      await api.put(`/transactions/${row.id}`, payload);
      toast.success(isPayout ? "Ödeme güncellendi" : "İşlem güncellendi");
      onSaved(); onClose();
    } catch (err) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Kayıt güncellenemedi. Alanları kontrol edin.");
    } finally { setSaving(false); }
  };
  return <Dialog open onOpenChange={open => { if (!open && !saving) onClose(); }}>
    <DialogContent className="bg-white max-w-3xl" data-testid="transaction-edit-dialog">
      <DialogHeader><DialogTitle>{isPayout ? "Amazon Ödemesini Düzenle" : "Gelir / Gider İşlemini Düzenle"}</DialogTitle><DialogDescription>{row.order_id || row.payment_reference || row.category} · {row.date} · {formatMoney(row.amount, row.currency)}</DialogDescription></DialogHeader>
      <form onSubmit={save} noValidate className="space-y-5 max-h-[70vh] overflow-y-auto pr-1">
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div><Label htmlFor="edit-tx-date">Tarih</Label><Input id="edit-tx-date" type="date" value={form.date} onChange={event => change("date", event.target.value)} className="mt-2" data-testid="edit-tx-date" /></div>
          <div><Label htmlFor="edit-tx-marketplace">Pazar Yeri</Label><Select value={form.marketplace} onValueChange={value => change("marketplace", value)}><SelectTrigger id="edit-tx-marketplace" className="mt-2" data-testid="edit-tx-marketplace"><SelectValue /></SelectTrigger><SelectContent className="bg-white">{(activeStore?.marketplaces || []).map(code => <SelectItem key={code} value={code}>{MP_BY_CODE[code]?.flag} {MP_BY_CODE[code]?.name}</SelectItem>)}</SelectContent></Select></div>
          <div><Label htmlFor="edit-tx-category">{isPayout ? "Ödeme Durumu" : "İşlem Türü"}</Label><Select value={form.category} onValueChange={setCategory}><SelectTrigger id="edit-tx-category" className="mt-2" data-testid="edit-tx-category"><SelectValue /></SelectTrigger><SelectContent className="bg-white">{(isPayout ? PAYOUT_STATUSES : TRANSACTION_CATEGORIES).map(value => <SelectItem key={value} value={value}>{value}</SelectItem>)}</SelectContent></Select></div>
          <div><Label htmlFor="edit-tx-amount">Tutar ({currency})</Label><Input id="edit-tx-amount" type="number" min="0.01" step="0.01" value={form.amount} onChange={event => change("amount", event.target.value)} className="mt-2 font-mono-num" data-testid="edit-tx-amount" /></div>
          {isPayout ? <div><Label htmlFor="edit-tx-reference">Ödeme Referansı</Label><Input id="edit-tx-reference" maxLength={200} value={form.payment_reference} onChange={event => change("payment_reference", event.target.value)} className="mt-2" data-testid="edit-tx-reference" /></div> : <div><Label htmlFor="edit-tx-order">Order ID</Label><Input id="edit-tx-order" value={form.order_id} onChange={event => change("order_id", event.target.value)} className="mt-2" data-testid="edit-tx-order" /></div>}
          <div className="sm:col-span-2"><Label htmlFor="edit-tx-description">Açıklama / Not</Label><Input id="edit-tx-description" value={form.description} onChange={event => change("description", event.target.value)} className="mt-2" data-testid="edit-tx-description" /></div>
        </div>
        {!isPayout && <FxStatus quote={fx.quote} loading={fx.loading} error={fx.error} retry={fx.retry} />}
        {isIncome && <div className="border-t border-slate-100 pt-4 space-y-4"><h3 className="font-display font-semibold">Maliyetler (USD)</h3><CostFields value={form} onChange={setForm} currency="USD" prefix="edit-tx" /><p className="text-sm text-slate-500">Güncel net kâr önizlemesi: <strong className={amountUsd - costs < 0 ? "text-rose-600" : "text-emerald-700"}>{formatUsd(amountUsd == null ? null : amountUsd - costs)}</strong></p></div>}
        {isRefund && <div className="border-t border-slate-100 pt-4 space-y-4"><h3 className="font-display font-semibold">İade Sonrası Geri Kazanımlar (USD)</h3><CostFields value={form} onChange={setForm} currency="USD" prefix="edit-tx" fields={RECOVERY_FIELDS} /><p className="text-sm text-slate-500">İadenin net etkisi: <strong className={costs - amountUsd < 0 ? "text-rose-600" : "text-emerald-700"}>{formatUsd(amountUsd == null ? null : costs - amountUsd)}</strong></p></div>}
        {error && <p role="alert" className="text-sm text-rose-700 bg-rose-50 p-3 rounded-md" data-testid="transaction-edit-error">{error}</p>}
        <DialogFooter><Button type="button" variant="outline" disabled={saving} onClick={onClose}>Vazgeç</Button><Button type="submit" disabled={saving || (!isPayout && (!fx.quote || fx.loading))} data-testid="save-transaction-edit">{saving ? "Kaydediliyor…" : "Güncelle"}</Button></DialogFooter>
      </form>
    </DialogContent>
  </Dialog>;
};
