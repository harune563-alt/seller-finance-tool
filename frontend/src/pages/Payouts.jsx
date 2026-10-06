import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { MP_BY_CODE } from "@/constants/marketplaces";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
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
import { TransactionEditDialog } from "@/components/transactions/TransactionEditDialog";
import { BulkEditDialog } from "@/components/BulkEditDialog";

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
  const [bulkEditing, setBulkEditing] = useState(false);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [deleting, setDeleting] = useState([]);
  const [deletingBusy, setDeletingBusy] = useState(false);
  const history = useRecordSearch({ storeId: activeStoreId, marketplace: activeMarketplace, currency: selectedCurrency, view: "payouts", revision });
  const [form, setForm] = useState({
    amount: "",
    date: todayISO(), description: "", category: STATUSES[0], payment_reference: "",
  });

  const fetchData = () => setRevision(v => v + 1);
  const toggleSelected = id => setSelectedIds(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  const toggleAll = () => setSelectedIds(current => { const ids = history.items.map(row => row.id); const allSelected = ids.length > 0 && ids.every(id => current.has(id)); return allSelected ? new Set([...current].filter(id => !ids.includes(id))) : new Set([...current, ...ids]); });
  const remove = async ids => {
    setDeletingBusy(true);
    try {
      if (ids.length === 1) await api.delete(`/transactions/${ids[0]}`);
      else await api.post("/transactions/bulk-delete", { ids });
      setDeleting([]); setSelectedIds(current => new Set([...current].filter(id => !ids.includes(id))));
      toast.success(`${ids.length} ödeme silindi`); fetchData();
    } catch { toast.error("Ödeme(ler) silinemedi"); }
    finally { setDeletingBusy(false); }
  };
  useEffect(() => { setSelectedCurrency(""); setEditingReference(null); setSelectedIds(new Set()); setDeleting([]); }, [activeStoreId, activeMarketplace]);
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

  return (
    <div className="space-y-6" data-testid="payouts-page">
      <div>
        <h1 className="font-display text-3xl font-extrabold text-slate-900">Amazon Ödemeleri & Bakiye</h1>
        <p className="text-sm text-slate-500 mt-1">Amazon hesabına gelen disbursement (ödeme) tutarlarını kaydet, bekleyen bakiyeni takip et.</p>
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
      {selectedIds.size > 0 && <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3" data-testid="payout-selection-toolbar"><span className="text-sm font-medium text-rose-800">{selectedIds.size} ödeme seçildi</span><div className="flex gap-2"><Button variant="outline" onClick={() => setBulkEditing(true)} data-testid="bulk-edit-payouts">Toplu Düzenle</Button><Button variant="destructive" onClick={() => setDeleting([...selectedIds])} data-testid="bulk-delete-payouts">Seçilenleri Sil</Button></div></div>}
      <PayoutHistory history={history} onEdit={setEditingReference} onDelete={id => setDeleting([id])} selectedIds={selectedIds} onToggle={toggleSelected} onToggleAll={toggleAll} />
      <RecordPagination history={history} prefix="payout" />
      {editingReference && <TransactionEditDialog key={editingReference.id} row={editingReference} onClose={() => setEditingReference(null)} onSaved={fetchData} />}
      {bulkEditing && <BulkEditDialog title="Ödemeleri Toplu Düzenle" description="Yalnızca doldurulan alanlar uygulanır" endpoint="/transactions/bulk-update" ids={[...selectedIds]} fields={[{ key: "date", label: "Tarih", type: "date" }, { key: "marketplace", label: "Pazar Yeri", type: "select", options: (activeStore?.marketplaces || []).map(code => ({ value: code, label: code })) }, { key: "category", label: "Ödeme Durumu", type: "select", options: STATUSES.map(value => ({ value, label: value })) }, { key: "amount", label: "Tutar", type: "number" }, { key: "currency", label: "Para Birimi", type: "select", options: ["USD", "CAD", "MXN", "GBP", "EUR", "AUD", "JPY", "AED", "SAR", "TRY", "SEK", "PLN"].map(value => ({ value, label: value })) }, { key: "payment_reference", label: "Ödeme Referansı" }, { key: "description", label: "Not" }]} onClose={() => setBulkEditing(false)} onSaved={() => { setBulkEditing(false); setSelectedIds(new Set()); fetchData(); }} />}
      <Dialog open={deleting.length > 0} onOpenChange={open => { if (!open && !deletingBusy) setDeleting([]); }}><DialogContent className="bg-white" data-testid="delete-payout-dialog"><DialogHeader><DialogTitle>{deleting.length} ödeme silinsin mi?</DialogTitle><DialogDescription>Seçilen Amazon ödeme kayıtları kalıcı olarak silinecek.</DialogDescription></DialogHeader><DialogFooter><Button variant="outline" disabled={deletingBusy} onClick={() => setDeleting([])}>Vazgeç</Button><Button variant="destructive" disabled={deletingBusy} onClick={() => remove(deleting)} data-testid="confirm-delete-payout">{deletingBusy ? "Siliniyor…" : "Sil"}</Button></DialogFooter></DialogContent></Dialog>
    </div>
  );
}
