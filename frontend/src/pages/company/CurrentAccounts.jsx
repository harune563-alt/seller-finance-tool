import { useMemo, useRef, useState } from "react";
import { Download, CheckCheck, Pencil, Plus, Trash2, X } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { useCompanyResource } from "@/hooks/useCompanyResource";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Checkbox } from "@/components/ui/checkbox";
import { PersonDialog } from "@/components/company/PersonDialog";
import { CurrencyField, SelectField, TextField, FormError, today, companyMoney, apiError } from "@/components/company/Fields";
import LegacyDebts from "@/pages/company/Debts";

const blank = () => ({ person_id: "", store_id: "ALL", direction: "payable", currency: "USD", amount: "", date: today(), due_date: "", cash_effect: "none", cash_status: "pending", note: "" });
const directionLabel = direction => direction === "payable" ? "Borç" : "Alacak";
const cashEffectLabel = effect => ({ none: "Kasa etkisi yok", in: "Kasaya giriş", out: "Kasadan çıkış" }[effect]);
const dueLabel = status => ({ none: "Vade yok", upcoming: "Vadesi var", due_soon: "Vadesi yaklaşıyor", overdue: "Vadesi geçti", completed: "Gerçekleşti" }[status] || status);
const dueTone = status => status === "overdue" ? "text-rose-700 bg-rose-50" : status === "due_soon" ? "text-amber-700 bg-amber-50" : status === "completed" ? "text-emerald-700 bg-emerald-50" : "text-slate-500 bg-slate-50";

export default function CurrentAccounts() {
  const { stores } = useStore();
  const people = useCompanyResource("/company/people");
  const accounts = useCompanyResource("/company/current-accounts");
  const [form, setForm] = useState(blank);
  const [editing, setEditing] = useState(null);
  const [personOpen, setPersonOpen] = useState(false);
  const [personFilter, setPersonFilter] = useState("ALL");
  const [currencyFilter, setCurrencyFilter] = useState("ALL");
  const [dueFilter, setDueFilter] = useState("ALL");
  const [search, setSearch] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [busy, setBusy] = useState(false);
  const [reportBusy, setReportBusy] = useState("");
  const [error, setError] = useState("");
  const requestId = useRef(crypto.randomUUID());
  const change = (key, value) => { setForm(current => ({ ...current, [key]: value })); requestId.current = crypto.randomUUID(); };

  const save = async event => {
    event.preventDefault(); setBusy(true); setError("");
    const payload = { ...form, store_id: form.store_id === "ALL" ? null : form.store_id, due_date: form.due_date || null, amount: Number(form.amount), request_id: requestId.current };
    try {
      if (editing) await api.put(`/company/current-accounts/${editing.id}`, payload);
      else await api.post("/company/current-accounts", payload);
      toast.success(editing ? "Cari hareket güncellendi" : "Cari hareket kaydedildi");
      setForm({ ...blank(), person_id: form.person_id, currency: form.currency, store_id: form.store_id }); setEditing(null); requestId.current = crypto.randomUUID(); accounts.refresh();
    } catch (err) { setError(apiError(err)); } finally { setBusy(false); }
  };

  const edit = entry => { setEditing(entry); setForm({ person_id: entry.person_id, store_id: entry.store_id || "ALL", direction: entry.direction, currency: entry.currency, amount: String(entry.amount), date: entry.date, due_date: entry.due_date || "", cash_effect: entry.cash_effect, cash_status: entry.cash_status, note: entry.note || "" }); requestId.current = crypto.randomUUID(); window.scrollTo({ top: 0, behavior: "smooth" }); };
  const remove = async entry => { if (!window.confirm("Bu cari hareket silinsin mi?")) return; try { await api.delete(`/company/current-accounts/${entry.id}`); toast.success("Cari hareket silindi"); setSelectedIds(current => new Set([...current].filter(id => id !== entry.id))); accounts.refresh(); } catch (err) { toast.error(apiError(err)); } };
  const toggleSelected = id => setSelectedIds(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  const toggleAll = rows => setSelectedIds(current => { const ids = rows.map(row => row.id); const all = ids.length > 0 && ids.every(id => current.has(id)); return all ? new Set([...current].filter(id => !ids.includes(id))) : new Set([...current, ...ids]); });
  const completeSelected = async () => { try { const { data } = await api.post("/company/current-accounts/bulk-complete", { ids: [...selectedIds] }); toast.success(`${data.updated} cari hareket gerçekleşti yapıldı`); setSelectedIds(new Set()); accounts.refresh(); } catch (err) { toast.error(apiError(err)); } };
  const deleteSelected = async () => { if (!window.confirm(`${selectedIds.size} cari hareket silinsin mi?`)) return; try { await api.post("/company/current-accounts/bulk-delete", { ids: [...selectedIds] }); toast.success("Seçili cari hareketler silindi"); setSelectedIds(new Set()); accounts.refresh(); } catch (err) { toast.error(apiError(err)); } };

  const downloadReport = async format => {
    setReportBusy(format);
    try {
      const params = { ...(personFilter !== "ALL" ? { person_id: personFilter } : {}), ...(currencyFilter !== "ALL" ? { currency: currencyFilter } : {}), ...(startDate ? { start_date: startDate } : {}), ...(endDate ? { end_date: endDate } : {}) };
      const { data } = await api.get(`/company/current-accounts/report/${format}`, { params, responseType: "blob" });
      const url = URL.createObjectURL(data); const link = document.createElement("a"); link.href = url; link.download = `cari-ekstre.${format === "excel" ? "xlsx" : "pdf"}`; document.body.appendChild(link); link.click(); link.remove(); URL.revokeObjectURL(url); toast.success(`${format === "excel" ? "Excel" : "PDF"} raporu indirildi`);
    } catch (err) { toast.error(apiError(err)); } finally { setReportBusy(""); }
  };

  const summaries = useMemo(() => (accounts.data?.summaries || []).filter(summary => currencyFilter === "ALL" || summary.currency === currencyFilter), [accounts.data, currencyFilter]);
  const entries = useMemo(() => (accounts.data?.entries || []).filter(entry => (personFilter === "ALL" || entry.person_id === personFilter) && (currencyFilter === "ALL" || entry.currency === currencyFilter) && (dueFilter === "ALL" || entry.due_status === dueFilter) && (!startDate || entry.date >= startDate) && (!endDate || entry.date <= endDate) && `${entry.person_name} ${entry.note}`.toLocaleLowerCase("tr").includes(search.toLocaleLowerCase("tr"))), [accounts.data, personFilter, currencyFilter, dueFilter, startDate, endDate, search]);
  const invalidDates = startDate && endDate && startDate > endDate;

  return <div className="space-y-7" data-testid="current-accounts-page">
    <div className="flex justify-between items-center gap-3 flex-wrap"><div><h2 className="text-lg font-display font-bold">Cari Hesap Ekstresi</h2><p className="text-sm text-slate-500 mt-1">Borç ve alacak hareketleri, vade takibi ve kasa etkisi</p></div><Button onClick={() => setPersonOpen(true)} data-testid="current-add-person"><Plus className="w-4 h-4 mr-2" />Kişi Ekle</Button></div>
    <FormError error={accounts.error || people.error} id="current-load-error" />
    <form onSubmit={save} className="border-y border-slate-200 bg-white p-4 sm:p-6 space-y-5" data-testid="current-entry-form">
      <div className="flex justify-between items-center gap-3"><h3 className="font-display font-bold text-base">{editing ? "Cari Hareketi Düzenle" : "Yeni Cari Hareket"}</h3>{editing && <Button type="button" variant="ghost" onClick={() => { setEditing(null); setForm(blank()); }} data-testid="current-cancel-edit"><X className="w-4 h-4 mr-2" />Düzenlemeyi İptal Et</Button>}</div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <SelectField label="Cari" id="current-person" value={form.person_id} onChange={v => change("person_id", v)} options={(people.data || []).map(person => ({ value: person.id, label: person.name }))} placeholder="Cari seçin" />
        <SelectField label="Hareket Türü" id="current-direction" value={form.direction} onChange={v => change("direction", v)} options={[{ value: "payable", label: "Borç · Şirketin borcu" }, { value: "receivable", label: "Alacak · Şirketin alacağı" }]} />
        <CurrencyField id="current-currency" value={form.currency} onChange={v => change("currency", v)} />
        <TextField label="Tutar" id="current-amount" value={form.amount} onChange={v => change("amount", v)} type="number" min="0.01" step="0.01" required />
        <TextField label="İşlem Tarihi" id="current-date" value={form.date} onChange={v => change("date", v)} type="date" required />
        <TextField label="Vade Tarihi" id="current-due-date" value={form.due_date} onChange={v => change("due_date", v)} type="date" min={form.date} />
        <SelectField label="İlgili Mağaza" id="current-store" value={form.store_id} onChange={v => change("store_id", v)} options={[{ value: "ALL", label: "Şirket geneli" }, ...stores.map(store => ({ value: store.id, label: store.name }))]} />
        <SelectField label="Kasa Etkisi" id="current-cash-effect" value={form.cash_effect} onChange={v => change("cash_effect", v)} options={[{ value: "none", label: "Kasa etkisi yok" }, { value: "in", label: "Kasaya giriş" }, { value: "out", label: "Kasadan çıkış" }]} />
        <SelectField label="Gerçekleşme" id="current-cash-status" value={form.cash_status} onChange={v => change("cash_status", v)} options={[{ value: "pending", label: "Bekliyor · Kasaya yansımaz" }, { value: "completed", label: "Gerçekleşti · Kasaya yansır" }]} />
        <div className="sm:col-span-2 lg:col-span-4"><TextField label="Açıklama / Not" id="current-note" value={form.note} onChange={v => change("note", v)} maxLength={500} /></div>
      </div>
      <p className="text-xs text-slate-500" data-testid="current-cash-help">Kasa etkisi “Yok” ise hareket kasa bakiyesini değiştirmez. “Bekliyor” kayıtlar gerçekleşene kadar kasaya yansımaz.</p><FormError error={error} id="current-entry-error" /><div className="flex justify-end"><Button type="submit" disabled={busy || !form.person_id} data-testid="current-entry-submit">{busy ? "Kaydediliyor…" : editing ? "Hareketi Güncelle" : "Cari Hareketi Kaydet"}</Button></div>
    </form>

    <section className="space-y-4" data-testid="current-summary-section"><div className="flex flex-wrap justify-between items-end gap-3"><div><h3 className="font-display font-bold text-lg">Cari Özetleri</h3><p className="text-xs text-slate-500 mt-1">Net bakiye = Şirketin borcu − Şirketin alacağı</p></div><div className="w-full sm:w-56"><SelectField label="Para Birimi" id="current-summary-currency" value={currencyFilter} onChange={setCurrencyFilter} options={[{ value: "ALL", label: "TL ve USD" }, { value: "USD", label: "USD" }, { value: "TRY", label: "TL" }]} /></div></div>{!summaries.length && <p className="text-sm text-slate-500" data-testid="current-summary-empty">Henüz cari hareketi yok.</p>}<div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">{summaries.map(summary => <button type="button" key={`${summary.person_id}-${summary.currency}`} onClick={() => setPersonFilter(summary.person_id)} className={`text-left border rounded-xl p-4 bg-white transition-colors ${personFilter === summary.person_id ? "border-emerald-500 ring-1 ring-emerald-500" : "border-slate-200 hover:border-emerald-300"}`} data-testid={`current-summary-${summary.person_id}-${summary.currency}`}><div className="flex justify-between gap-3"><strong>{summary.person_name}</strong><span className="text-xs text-slate-500">{summary.currency}</span></div><div className="grid grid-cols-2 gap-3 mt-4 text-sm"><div><p className="text-xs text-slate-500">Toplam borç</p><strong className="text-rose-600">{companyMoney(summary.total_payable, summary.currency)}</strong></div><div><p className="text-xs text-slate-500">Toplam alacak</p><strong className="text-emerald-700">{companyMoney(summary.total_receivable, summary.currency)}</strong></div></div><div className="border-t border-slate-100 mt-4 pt-3 flex justify-between text-sm"><span>Net bakiye</span><strong className={summary.net_balance > 0 ? "text-rose-600" : summary.net_balance < 0 ? "text-emerald-700" : "text-slate-700"}>{companyMoney(summary.net_balance, summary.currency)}</strong></div></button>)}</div></section>

    <section className="space-y-4" data-testid="current-statement-section"><div className="flex flex-wrap items-end gap-4"><div className="flex-1 min-w-[220px]"><TextField label="Cari ekstrede ara" id="current-search" value={search} onChange={setSearch} placeholder="İsim veya açıklama" /></div><div className="w-full sm:w-56"><SelectField label="Cari filtresi" id="current-person-filter" value={personFilter} onChange={setPersonFilter} options={[{ value: "ALL", label: "Tüm cariler" }, ...(people.data || []).map(person => ({ value: person.id, label: person.name }))]} /></div><div className="w-full sm:w-48"><SelectField label="Vade filtresi" id="current-due-filter" value={dueFilter} onChange={setDueFilter} options={[{ value: "ALL", label: "Tüm vadeler" }, { value: "due_soon", label: "Vadesi yaklaşan" }, { value: "overdue", label: "Vadesi geçen" }, { value: "upcoming", label: "Vadesi olan" }, { value: "none", label: "Vadesiz" }, { value: "completed", label: "Gerçekleşen" }]} /></div></div><div className="grid grid-cols-1 sm:grid-cols-2 gap-4"><TextField label="Başlangıç tarihi" id="current-start-date" value={startDate} onChange={setStartDate} type="date" /><TextField label="Bitiş tarihi" id="current-end-date" value={endDate} onChange={setEndDate} type="date" /></div><FormError error={invalidDates ? "Başlangıç tarihi bitişten sonra olamaz." : ""} id="current-filter-error" />
      <div className="flex flex-wrap justify-between items-center gap-3"><div className="flex gap-2 flex-wrap"><Button variant="outline" size="sm" onClick={() => downloadReport("excel")} disabled={!!reportBusy} data-testid="current-report-excel"><Download className="w-4 h-4 mr-2" />{reportBusy === "excel" ? "Hazırlanıyor…" : "Excel İndir"}</Button><Button variant="outline" size="sm" onClick={() => downloadReport("pdf")} disabled={!!reportBusy} data-testid="current-report-pdf"><Download className="w-4 h-4 mr-2" />{reportBusy === "pdf" ? "Hazırlanıyor…" : "PDF İndir"}</Button></div>{selectedIds.size > 0 && <div className="flex gap-2 flex-wrap"><Button variant="outline" size="sm" onClick={completeSelected} data-testid="current-bulk-complete"><CheckCheck className="w-4 h-4 mr-2" />Gerçekleşti yap ({selectedIds.size})</Button><Button variant="destructive" size="sm" onClick={deleteSelected} data-testid="current-bulk-delete"><Trash2 className="w-4 h-4 mr-2" />Seçilenleri sil ({selectedIds.size})</Button></div>}</div>
      <div className="border border-slate-200 rounded-xl overflow-x-auto bg-white"><table className="w-full text-sm" data-testid="current-statement-table"><thead className="bg-slate-50 text-xs text-slate-500"><tr><th className="p-3"><Checkbox checked={entries.length > 0 && entries.every(row => selectedIds.has(row.id))} onCheckedChange={() => toggleAll(entries)} aria-label="Tüm cari hareketleri seç" data-testid="current-select-all" /></th><th className="text-left p-3">Tarih</th><th className="text-left p-3">Cari</th><th className="text-left p-3">Hareket</th><th className="text-right p-3">Tutar</th><th className="text-right p-3">Bakiye</th><th className="text-left p-3">Kasa</th><th className="text-left p-3">Vade</th><th className="text-left p-3">Durum</th><th className="text-right p-3">İşlem</th></tr></thead><tbody>{!entries.length && <tr><td colSpan="10" className="p-5 text-center text-slate-500" data-testid="current-statement-empty">Bu filtrede hareket yok.</td></tr>}{entries.map(entry => <tr key={entry.id} className="border-t border-slate-100" data-testid={`current-entry-row-${entry.id}`}><td className="p-3"><Checkbox checked={selectedIds.has(entry.id)} onCheckedChange={() => toggleSelected(entry.id)} aria-label="Cari hareketini seç" data-testid={`current-select-${entry.id}`} /></td><td className="p-3 text-slate-600">{entry.date}</td><td className="p-3 font-medium">{entry.person_name}<p className="text-xs text-slate-500 mt-1">{entry.store_name || "Şirket geneli"}</p></td><td className="p-3"><span className={entry.direction === "payable" ? "text-rose-700" : "text-emerald-700"}>{directionLabel(entry.direction)}</span><p className="text-xs text-slate-500 mt-1 max-w-[220px] break-words">{entry.note || "—"}</p></td><td className="p-3 text-right font-mono-num">{companyMoney(entry.amount, entry.currency)}</td><td className="p-3 text-right font-mono-num">{companyMoney(entry.balance_after, entry.currency)}</td><td className="p-3 text-xs text-slate-600">{cashEffectLabel(entry.cash_effect)}</td><td className="p-3 text-xs"><span className={`px-2 py-1 rounded ${dueTone(entry.due_status)}`}>{entry.due_date || "—"}{entry.due_date && <span className="block mt-1">{dueLabel(entry.due_status)}</span>}</span></td><td className="p-3 text-xs"><span className={entry.cash_status === "completed" ? "text-emerald-700" : "text-amber-700"}>{entry.cash_status === "completed" ? "Gerçekleşti" : "Bekliyor"}</span></td><td className="p-3 text-right whitespace-nowrap"><Button variant="ghost" size="icon" onClick={() => edit(entry)} data-testid={`current-edit-${entry.id}`} aria-label="Cari hareketi düzenle"><Pencil className="w-4 h-4" /></Button><Button variant="ghost" size="icon" onClick={() => remove(entry)} data-testid={`current-delete-${entry.id}`} aria-label="Cari hareketi sil" className="text-slate-400 hover:text-rose-600"><Trash2 className="w-4 h-4" /></Button></td></tr>)}</tbody></table></div>
    </section>

    <Tabs defaultValue="current" className="pt-3" data-testid="debt-history-tabs"><TabsList><TabsTrigger value="current" data-testid="tab-current-accounts">Cari Ekstre</TabsTrigger><TabsTrigger value="legacy" data-testid="tab-legacy-debts">Eski Borç/Alacak Kayıtları</TabsTrigger></TabsList><TabsContent value="current"><p className="text-xs text-slate-500 mt-3">Yeni cari hareketler yukarıdaki ekstrede tutulur. Eski kayıtlar ayrı sekmede korunur.</p></TabsContent><TabsContent value="legacy"><div className="mt-4"><LegacyDebts /></div></TabsContent></Tabs>
    {personOpen && <PersonDialog onClose={() => setPersonOpen(false)} onSaved={person => { people.refresh(); change("person_id", person.id); }} />}
  </div>;
}
