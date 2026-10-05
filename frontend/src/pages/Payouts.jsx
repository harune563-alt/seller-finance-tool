import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { MP_BY_CODE } from "@/constants/marketplaces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Wallet, Plus } from "lucide-react";
import { toast } from "sonner";
import KpiCard from "@/components/KpiCard";
import { FinanceCurrency } from "@/components/FinanceCurrency";
import { useFormMarketplace } from "@/hooks/useFormMarketplace";
import { MissingFxAlert, NativeBalances, formatUsd } from "@/components/FxStatus";
import { useRecordSearch } from "@/hooks/useRecordSearch";
import { RecordFilters, RecordPagination } from "@/components/RecordFilters";
import { PayoutHistory } from "@/components/payouts/PayoutHistory";
import { PaymentReferenceDialog } from "@/components/payouts/PaymentReferenceDialog";

const todayISO = () => new Date().toISOString().slice(0, 10);

const STATUSES = ["Oluşturuldu", "İşleniyor", "Bankada"];

export default function Payouts() {
  const { activeStore, activeStoreId, activeMarketplace } = useStore();
  const { marketplace, currency: formCurrency, selectMarketplace } = useFormMarketplace();
  const [summary, setSummary] = useState(null);
  const [selectedCurrency, setSelectedCurrency] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [editingReference, setEditingReference] = useState(null);
  const history = useRecordSearch({ storeId: activeStoreId, marketplace: activeMarketplace, currency: selectedCurrency, view: "payouts", revision });
  const [form, setForm] = useState({
    amount: "",
    date: todayISO(), description: "", category: STATUSES[0], payment_reference: "",
  });

  const fetchData = () => setRevision(v => v + 1);
  useEffect(() => { setSelectedCurrency(""); setEditingReference(null); }, [activeStoreId, activeMarketplace]);
  useEffect(() => {
    let current = true;
    setSummary(null); setError("");
    if (!activeStoreId) return;
    const params = { store_id: activeStoreId, marketplace: activeMarketplace, ...(selectedCurrency ? { currency: selectedCurrency } : {}) };
    (async () => {
      try {
        const s = await api.get("/dashboard/summary", { params });
        if (current) setSummary(s.data);
      } catch { if (current) setError("Ödemeler yüklenemedi."); }
    })();
    return () => { current = false; };
  }, [activeStoreId, activeMarketplace, selectedCurrency, revision]);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (!activeStoreId || !activeStore?.marketplaces.includes(marketplace)) { setError("Geçerli mağaza ve pazar yeri seçin."); return; }
    if (!form.date || !Number.isFinite(Number(form.amount)) || Number(form.amount) <= 0) { setError("Tarih ve sıfırdan büyük bir tutar girin."); return; }
    setSaving(true);
    try {
      await api.post("/transactions", { store_id: activeStoreId, type: "payout", ...form, marketplace, currency: formCurrency, amount: Number(form.amount) });
      toast.success("Ödeme kaydı eklendi");
      setForm((f) => ({ ...f, amount: "", description: "", payment_reference: "" })); fetchData();
    } catch (err) { const detail = err.response?.data?.detail; setError(typeof detail === "string" ? detail : "Ödeme kaydedilemedi."); }
    finally { setSaving(false); }
  };

  const remove = async (id) => {
    try { await api.delete(`/transactions/${id}`); toast.success("Ödeme silindi"); fetchData(); }
    catch { toast.error("Ödeme silinemedi"); }
  };

  return (
    <div className="space-y-6" data-testid="payouts-page">
      <div>
        <h1 className="font-display text-3xl font-extrabold text-slate-900">Amazon Ödemeleri & Bakiye</h1>
        <p className="text-sm text-slate-500 mt-1">Amazon'dan hesabına gelen disbursement (ödeme) tutarlarını kaydet, bekleyen bakiyeni takip et.</p>
      </div>

      <FinanceCurrency summary={summary} value={selectedCurrency} onChange={setSelectedCurrency} prefix="payout" />
      <MissingFxAlert summary={summary} prefix="payout" />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KpiCard testId="pk-balance" label="Bekleyen Amazon Bakiye" accent="amazon" icon={Wallet}
                 value={<NativeBalances summary={summary} prefix="payout-amazon" />}
                 hint="Tahmini · rezervler hariç" />
        <KpiCard testId="pk-received" label="Toplam Alınan Ödeme" accent="emerald" icon={Wallet}
                 value={<NativeBalances summary={summary} field="payouts_received" prefix="payout-received" />}
                 hint="Hesaba düşen toplam" />
        <KpiCard testId="pk-net" label="Net Kâr (USD)" accent="indigo" icon={Wallet}
                 value={formatUsd(summary?.net_profit)}
                 hint="Gelir − Gider" />
      </div>

      {error && <p role="alert" data-testid="payout-form-error" className="text-sm text-rose-700">{error}</p>}
      <form onSubmit={submit} noValidate className="bg-white border border-slate-200 rounded-2xl p-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <div>
          <Label className="text-xs font-semibold uppercase tracking-wider text-slate-600">Ödeme Tarihi</Label>
          <Input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })}
                 required data-testid="payout-date-input" className="mt-1" />
        </div>
        <div>
          <Label className="text-xs font-semibold uppercase tracking-wider text-slate-600">Pazar Yeri</Label>
          <Select value={marketplace} onValueChange={selectMarketplace}>
            <SelectTrigger data-testid="payout-marketplace-select" className="mt-1"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-white" data-testid="payout-marketplace-options">
              {(activeStore?.marketplaces || []).map((c) => {
                const m = MP_BY_CODE[c];
                return <SelectItem key={c} value={c} data-testid={`payout-marketplace-${c.toLowerCase()}`}>{m?.flag} {m?.name}</SelectItem>;
              })}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label className="text-xs font-semibold uppercase tracking-wider text-slate-600">Tutar ({formCurrency})</Label>
          <Input type="number" step="0.01" min="0.01" value={form.amount}
                 onChange={(e) => setForm({ ...form, amount: e.target.value })}
                 required data-testid="payout-amount-input" className="mt-1 font-mono-num" />
        </div>
        <div>
          <Label className="text-xs font-semibold uppercase tracking-wider text-slate-600">Durum</Label>
          <Select value={form.category} onValueChange={(v) => { if (STATUSES.includes(v)) setForm({ ...form, category: v }); }}>
            <SelectTrigger data-testid="payout-status-select" className="mt-1"><SelectValue /></SelectTrigger>
            <SelectContent className="bg-white" data-testid="payout-status-options">
              {STATUSES.map((s, i) => <SelectItem key={s} value={s} data-testid={`payout-status-${i}`}>{s}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor="payout-reference">Ödeme Referansı (isteğe bağlı)</Label>
          <Input id="payout-reference" value={form.payment_reference} maxLength={200} onChange={e => setForm({ ...form, payment_reference: e.target.value })} placeholder="Örn. TRANSFER-2026-001" data-testid="payout-reference-input" className="mt-1" />
        </div>
        <div className="lg:col-span-2">
          <Label className="text-xs font-semibold uppercase tracking-wider text-slate-600">Not</Label>
          <Textarea rows={1} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
                    data-testid="payout-note-input" className="mt-1" />
        </div>
        <div className="lg:col-span-1 flex items-end">
          <Button type="submit" data-testid="payout-submit-button" disabled={saving || !activeStoreId}
                  className="w-full bg-orange-600 hover:bg-orange-700 text-white rounded-xl">
            <Plus className="w-4 h-4 mr-1" /> {saving ? "Kaydediliyor…" : "Ödeme Kaydet"}
          </Button>
        </div>
      </form>

      <RecordFilters history={history} prefix="payout" searchLabel="Ödeme referansı veya not" categoryLabel="Ödeme Durumu" options={STATUSES} unit="ödeme" />
      <PayoutHistory history={history} onEditReference={setEditingReference} onDelete={remove} />
      <RecordPagination history={history} prefix="payout" />
      {editingReference && <PaymentReferenceDialog key={editingReference.id} row={editingReference} onClose={() => setEditingReference(null)} onSaved={fetchData} />}
    </div>
  );
}
