import { useEffect, useRef, useState } from "react";
import { Plus, Pencil, Trash2, ArrowDownToLine } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { useCompanyResource } from "@/hooks/useCompanyResource";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { CapitalEditDialog } from "@/components/company/CapitalEditDialog";
import { PersonDialog } from "@/components/company/PersonDialog";
import { CurrencyField, TextField, SelectField, FormError, today, companyMoney, currencyName, apiError } from "@/components/company/Fields";

export default function Capital() {
  const { stores, activeStoreId } = useStore();
  const [storeId, setStoreId] = useState(activeStoreId);
  useEffect(() => { setStoreId(activeStoreId); }, [activeStoreId]);
  const people = useCompanyResource("/company/people");
  const capital = useCompanyResource(storeId ? `/company/capital?store_id=${storeId}` : null);
  const [personModal, setPersonModal] = useState(null);
  const [editingEntry, setEditingEntry] = useState(null);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [form, setForm] = useState({ person_id: "", direction: "contribution", currency: "USD", amount: "", date: today(), note: "" });
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const requestId = useRef(crypto.randomUUID());
  const change = (key, value) => { setForm(f => ({ ...f, [key]: value })); requestId.current = crypto.randomUUID(); };
  const submit = async e => {
    e.preventDefault(); if (!storeId || !form.person_id || Number(form.amount) <= 0) { setError("Mağaza, kişi ve pozitif tutar seçin."); return; }
    setBusy(true); setError("");
    try { await api.post("/company/capital", { ...form, amount: Number(form.amount), store_id: storeId, request_id: requestId.current }); toast.success("Sermaye kaydedildi"); capital.refresh(); change("amount", ""); }
    catch (e) { setError(apiError(e)); } finally { setBusy(false); }
  };
  const toggleSelected = id => setSelectedIds(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  const removeEntries = async ids => { if (!window.confirm(`${ids.length} sermaye kaydı kalıcı olarak silinsin mi?`)) return; try { if (ids.length === 1) await api.delete(`/company/capital/${ids[0]}`); else await api.post("/company/capital/bulk-delete", { ids }); setSelectedIds(new Set()); toast.success(`${ids.length} sermaye kaydı silindi`); capital.refresh(); } catch (e) { toast.error(apiError(e)); } };
  return <div className="space-y-7" data-testid="capital-page">
    <div className="flex flex-wrap justify-between items-end gap-4"><div className="w-full sm:w-72"><SelectField label="Mağaza" id="capital-store" value={storeId} onChange={setStoreId} options={stores.map(s => ({ value: s.id, label: s.name }))} /></div><Button onClick={() => setPersonModal({})} data-testid="add-company-person"><Plus className="w-4 h-4 mr-2" />Kişi Ekle</Button></div>
    <FormError error={people.error || capital.error} id="capital-load-error" />
    <section><div className="flex flex-wrap justify-between gap-3 mb-4"><h2 className="font-display font-bold text-lg">Sermaye Bazlı Hisseler</h2><strong className="font-mono-num" data-testid="capital-total">{companyMoney(capital.data?.total_usd)}</strong></div>
      <p className="text-xs text-slate-500 mb-4" data-testid="capital-basis-note">Paylar bu mağazadaki net sermayeye göre hesaplanır. TL yatırımları işlem tarihindeki USD karşılığıyla karşılaştırılır; borçlar hisse oluşturmaz.</p>
      <div className="space-y-3">{capital.loading ? <p data-testid="capital-loading">Yükleniyor…</p> : !capital.data?.ownership.length ? <p className="text-sm text-slate-500 py-4" data-testid="capital-empty">Bu mağazada sermaye kaydı yok.</p> : capital.data.ownership.map(p => <article key={p.person_id} className="bg-white border border-slate-200 rounded-lg p-5" data-testid={`ownership-${p.person_id}`}>
        <div className="flex justify-between items-start flex-wrap gap-3"><div><strong>{p.person_name}</strong><p className="text-xs text-slate-500 mt-1">{p.role === "partner" ? "Ortak" : p.role === "investor" ? "Dış Yatırımcı" : "Kişi"}</p></div><div className="text-right"><strong className="text-2xl font-mono-num text-emerald-700" data-testid={`share-${p.person_id}`}>%{p.share_percent.toFixed(2)}</strong><p className="text-sm font-mono-num" data-testid={`capital-net-${p.person_id}`}>{companyMoney(p.net_capital_usd)}</p></div></div>
        <div className="h-2 rounded-full bg-slate-100 my-4 overflow-hidden"><div className="h-full bg-emerald-500 transition-[width] duration-300" style={{ width: `${p.share_percent}%` }} /></div><div className="flex flex-wrap gap-5 text-xs text-slate-500">{Object.entries(p.balances).map(([c, v]) => <span key={c} data-testid={`capital-balance-${p.person_id}-${c.toLowerCase()}`}>{currencyName(c)} net sermaye: <strong>{companyMoney(v, c)}</strong></span>)}</div>
      </article>)}</div>
    </section>
    <form onSubmit={submit} className="border-y border-slate-200 bg-white p-4 sm:p-6 space-y-5" data-testid="capital-form"><h2 className="text-lg font-display font-bold">Sermaye Hareketi</h2><div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
      <SelectField label="Kişi" id="capital-person" value={form.person_id} onChange={v => change("person_id", v)} options={(people.data || []).map(p => ({ value: p.id, label: p.name }))} />
      <SelectField label="Hareket" id="capital-direction" value={form.direction} onChange={v => change("direction", v)} options={[{ value: "contribution", label: "Sermaye Girişi" }, { value: "withdrawal", label: "Sermaye İadesi" }]} />
      <CurrencyField id="capital-currency" value={form.currency} onChange={v => change("currency", v)} />
      <TextField label="Tutar" id="capital-amount" value={form.amount} onChange={v => change("amount", v)} type="number" min="0.01" step="0.01" required />
      <TextField label="Tarih" id="capital-date" value={form.date} onChange={v => change("date", v)} type="date" required />
      <TextField label="Not" id="capital-note" value={form.note} onChange={v => change("note", v)} maxLength={500} />
    </div><FormError error={error} id="capital-form-error" /><div className="flex justify-end"><Button disabled={busy || !storeId} type="submit" data-testid="capital-submit"><ArrowDownToLine className="w-4 h-4 mr-2" />{busy ? "Kaydediliyor…" : "Hareketi Kaydet"}</Button></div></form>
    <section className="space-y-3"><div className="flex flex-wrap justify-between items-center gap-3"><h2 className="text-lg font-display font-bold">Sermaye Geçmişi</h2>{selectedIds.size > 0 && <Button variant="destructive" size="sm" onClick={() => removeEntries([...selectedIds])}>Seçilenleri Sil ({selectedIds.size})</Button>}</div>{capital.data?.entries.map(e => <div key={e.id} className="border-b border-slate-200 py-3 flex flex-wrap justify-between gap-3" data-testid={`capital-entry-${e.id}`}><div className="flex items-start gap-3"><Checkbox checked={selectedIds.has(e.id)} onCheckedChange={() => toggleSelected(e.id)} aria-label="Sermaye kaydını seç" /><div><strong className="text-sm">{e.person_name}</strong><p className="text-xs text-slate-500 mt-1">{e.date} · {e.direction === "contribution" ? "Sermaye girişi" : "Sermaye iadesi"} · {e.note}</p></div></div><div className="text-right"><strong className={e.direction === "contribution" ? "text-emerald-700" : "text-rose-600"}>{e.direction === "withdrawal" ? "−" : "+"}{companyMoney(e.amount, e.currency)}</strong><p className="text-xs text-slate-500 mt-1">Sermaye karşılığı: {companyMoney(e.usd_basis)}</p><div className="flex justify-end gap-1 mt-2"><Button variant="ghost" size="icon" onClick={() => setEditingEntry(e)} aria-label="Sermaye kaydını düzenle" data-testid={`edit-capital-${e.id}`}><Pencil className="w-4 h-4" /></Button><Button variant="ghost" size="icon" onClick={() => removeEntries([e.id])} aria-label="Sermaye kaydını sil" data-testid={`delete-capital-${e.id}`} className="text-slate-400 hover:text-rose-600"><Trash2 className="w-4 h-4" /></Button></div></div></div>)}</section>
    <section><h2 className="text-lg font-display font-bold mb-3">Kişiler</h2><div className="flex flex-wrap gap-3">{people.data?.map(p => <Button key={p.id} variant="outline" onClick={() => setPersonModal(p)} data-testid={`edit-person-${p.id}`}><Pencil className="w-3 h-3 mr-2" />{p.name}</Button>)}</div></section>
    {editingEntry && <CapitalEditDialog entry={editingEntry} people={people.data || []} storeId={storeId} onClose={() => setEditingEntry(null)} onSaved={capital.refresh} />}
    {personModal && <PersonDialog person={personModal.id ? personModal : null} onClose={() => setPersonModal(null)} onSaved={p => { people.refresh(); capital.refresh(); change("person_id", p.id); }} />}
  </div>;
}