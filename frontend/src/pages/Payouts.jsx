import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { MP_BY_CODE, formatMoney } from "@/constants/marketplaces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Trash2, Wallet, Plus } from "lucide-react";
import { toast } from "sonner";
import KpiCard from "@/components/KpiCard";
import { FinanceCurrency } from "@/components/FinanceCurrency";
import { useFormMarketplace } from "@/hooks/useFormMarketplace";

const todayISO = () => new Date().toISOString().slice(0, 10);

const STATUSES = ["Oluşturuldu", "İşleniyor", "Bankada"];

export default function Payouts() {
  const { activeStore, activeStoreId, activeMarketplace } = useStore();
  const { marketplace, currency: formCurrency, selectMarketplace } = useFormMarketplace();
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [selectedCurrency, setSelectedCurrency] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  const [form, setForm] = useState({
    amount: "",
    date: todayISO(), description: "", category: STATUSES[0],
  });

  const fetchData = () => setRevision(v => v + 1);
  useEffect(() => { setSelectedCurrency(""); }, [activeStoreId, activeMarketplace]);
  useEffect(() => {
    let current = true;
    setRows([]); setSummary(null); setError("");
    if (!activeStoreId) return;
    const params = { store_id: activeStoreId, marketplace: activeMarketplace, ...(selectedCurrency ? { currency: selectedCurrency } : {}) };
    (async () => {
      try {
        const s = await api.get("/dashboard/summary", { params });
        const t = await api.get("/transactions", { params: { ...params, currency: s.data.currency, type: "payout" } });
        if (current) { setRows(t.data); setSummary(s.data); }
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
      setForm((f) => ({ ...f, amount: "", description: "" })); fetchData();
    } catch (err) { const detail = err.response?.data?.detail; setError(typeof detail === "string" ? detail : "Ödeme kaydedilemedi."); }
    finally { setSaving(false); }
  };

  const remove = async (id) => {
    try { await api.delete(`/transactions/${id}`); toast.success("Ödeme silindi"); fetchData(); }
    catch { toast.error("Ödeme silinemedi"); }
  };

  const currency = summary?.currency || (activeMarketplace !== "ALL"
    ? MP_BY_CODE[activeMarketplace]?.currency || "USD"
    : activeStore?.default_currency || "USD");

  return (
    <div className="space-y-6" data-testid="payouts-page">
      <div>
        <h1 className="font-display text-3xl font-extrabold text-slate-900">Amazon Ödemeleri & Bakiye</h1>
        <p className="text-sm text-slate-500 mt-1">Amazon'dan hesabına gelen disbursement (ödeme) tutarlarını kaydet, bekleyen bakiyeni takip et.</p>
      </div>

      <FinanceCurrency summary={summary} value={selectedCurrency} onChange={setSelectedCurrency} prefix="payout" />
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <KpiCard testId="pk-balance" label="Bekleyen Amazon Bakiye" accent="amazon" icon={Wallet}
                 value={formatMoney(summary?.amazon_balance || 0, currency)}
                 hint="Tahmini · rezervler hariç" />
        <KpiCard testId="pk-received" label="Toplam Alınan Ödeme" accent="emerald" icon={Wallet}
                 value={formatMoney(summary?.payouts_received || 0, currency)}
                 hint="Hesaba düşen toplam" />
        <KpiCard testId="pk-net" label="Net Kar" accent="indigo" icon={Wallet}
                 value={formatMoney(summary?.net_profit || 0, currency)}
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
        <div className="md:col-span-2 lg:col-span-3">
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

      <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200">
          <h2 className="font-display text-lg font-bold text-slate-900">Ödeme Geçmişi ({rows.length})</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
              <tr>
                <th className="text-left px-6 py-3 font-semibold">Tarih</th>
                <th className="text-left px-4 py-3 font-semibold">Pazar</th>
                <th className="text-left px-4 py-3 font-semibold">Durum</th>
                <th className="text-left px-4 py-3 font-semibold">Not</th>
                <th className="text-right px-4 py-3 font-semibold">Tutar</th>
                <th className="text-right px-6 py-3 font-semibold">—</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {rows.length === 0 && (
                <tr><td colSpan={6} className="px-6 py-8 text-center text-slate-400">Ödeme kaydı yok</td></tr>
              )}
              {rows.map((r) => {
                const mp = MP_BY_CODE[r.marketplace];
                return (
                  <tr key={r.id} className="hover:bg-slate-50">
                    <td className="px-6 py-3 font-mono-num text-slate-700">{r.date}</td>
                    <td className="px-4 py-3">{mp?.flag} {r.marketplace}</td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center text-xs font-semibold px-2 py-0.5 rounded-full bg-orange-50 text-orange-700 border border-orange-200">
                        {r.category}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-slate-600 max-w-[320px] truncate">{r.description || "—"}</td>
                    <td className="px-4 py-3 text-right font-mono-num font-bold text-orange-600">
                      {formatMoney(r.amount, r.currency)}
                    </td>
                    <td className="px-6 py-3 text-right">
                      <Button variant="ghost" size="icon" onClick={() => remove(r.id)}
                              data-testid={`delete-payout-${r.id}`}
                              className="text-slate-400 hover:text-rose-600 hover:bg-rose-50">
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
