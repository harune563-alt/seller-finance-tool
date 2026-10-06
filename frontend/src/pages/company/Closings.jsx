import { useState } from "react";
import { RefreshCw, CalendarCheck, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useCompanyResource } from "@/hooks/useCompanyResource";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { ClosingEditDialog } from "@/components/company/ClosingEditDialog";
import { BulkEditDialog } from "@/components/BulkEditDialog";
import { companyMoney, FormError, apiError } from "@/components/company/Fields";

const states = { pending: "Sırada", running: "Hesaplanıyor", completed: "Tamamlandı", failed: "Başarısız", interrupted: "Yeniden eşitlendi" };
export default function Closings() {
  const closings = useCompanyResource("/company/closings"), jobs = useCompanyResource("/company/jobs");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const [editingClosing, setEditingClosing] = useState(null), [bulkEditing, setBulkEditing] = useState(false), [selectedIds, setSelectedIds] = useState(() => new Set());
  const refresh = () => { closings.refresh(); jobs.refresh(); };
  const run = async () => { setBusy(true); setError(""); try { await api.post("/company/closings/run"); toast.success("Kapanış eşitlemesi sıraya alındı"); refresh(); } catch (e) { setError(apiError(e)); } finally { setBusy(false); } };
  const toggleSelected = id => setSelectedIds(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  const removeClosings = async ids => { if (!window.confirm(`${ids.length} kapanış kaydı kalıcı olarak silinsin mi?`)) return; try { if (ids.length === 1) await api.delete(`/company/closings/${ids[0]}`); else await api.post("/company/closings/bulk-delete", { ids }); setSelectedIds(new Set()); toast.success(`${ids.length} kapanış kaydı silindi`); closings.refresh(); } catch (e) { toast.error(apiError(e)); } };
  return <div className="space-y-6" data-testid="closings-page">
    <div className="flex flex-wrap justify-between gap-4 items-start"><div><h2 className="text-lg font-display font-bold">Aylık Mağaza Kapanışları</h2><p className="mt-2 text-sm text-slate-500" data-testid="closing-policy">Kapalı aylar · Her mağaza/ay için tek muhasebe kaydı · USD</p></div><div className="flex gap-2 flex-wrap"><Button variant="outline" onClick={refresh} data-testid="refresh-closings"><RefreshCw className="w-4 h-4 mr-2" />Durumu Yenile</Button><Button onClick={run} disabled={busy} data-testid="run-monthly-close-button"><CalendarCheck className="w-4 h-4 mr-2" />{busy ? "Başlatılıyor…" : "Kapanışları Eşitle"}</Button></div></div>
    <div className="border-y border-slate-200 py-4 text-xs text-slate-500 space-y-2" data-testid="closing-accounting-note"><p>Otomatik kontrol: her gün 03:00 UTC. İçinde bulunulan ay aktarılmaz. Geçmiş değişiklikler aynı kapanış kaydını revize eder.</p><p>Bu kayıt gerçek banka/Amazon transferi değildir; nakit kasasından ayrı muhasebe bakiyesidir.</p></div>
    <FormError error={error || closings.error || jobs.error} id="closing-error" />
    {jobs.data?.[0] && <div className="flex flex-wrap justify-between gap-3 text-sm border-l-4 border-emerald-500 bg-white p-4" data-testid="latest-closing-job"><span>Son eşitleme: <strong data-testid="closing-job-status">{states[jobs.data[0].status] || jobs.data[0].status}</strong></span><span className="text-xs text-slate-500">{new Date(jobs.data[0].updated_at).toLocaleString("tr-TR")} · {jobs.data[0].processed} mağaza/ay</span>{jobs.data[0].error && <span role="alert" className="text-rose-700" data-testid="closing-job-error">{jobs.data[0].error}</span>}</div>}
    <div className="space-y-3" data-testid="treasury-ledger-table"><div className="flex justify-end">{selectedIds.size > 0 && <div className="flex gap-2"><Button variant="outline" size="sm" onClick={() => setBulkEditing(true)}>Toplu Düzenle</Button><Button variant="destructive" size="sm" onClick={() => removeClosings([...selectedIds])}>Seçilenleri Sil ({selectedIds.size})</Button></div>}</div>{closings.loading ? <p data-testid="closings-loading">Yükleniyor…</p> : !closings.data?.length ? <p className="text-sm text-slate-500 py-8 text-center border border-dashed rounded-lg" data-testid="closings-empty">Henüz kapanmış ay kaydı yok.</p> : closings.data.map(c => <article key={c.id} className={`rounded-lg border p-5 grid grid-cols-2 lg:grid-cols-5 gap-4 ${c.net_profit < 0 ? "bg-rose-50 border-rose-200" : "bg-white border-slate-200"}`} data-testid={`closing-${c.id}`}>
      <div className="col-span-2 lg:col-span-1 flex items-start gap-3"><Checkbox checked={selectedIds.has(c.id)} onCheckedChange={() => toggleSelected(c.id)} aria-label="Kapanış kaydını seç" /><div><strong className="text-sm break-words">{c.store_name}</strong><p className="text-xs text-slate-500 mt-1">{c.period} · Revizyon {c.revision}</p></div></div>
      <div><p className="text-xs text-slate-500">Gelir USD</p><strong className="text-sm font-mono-num">{companyMoney(c.revenue)}</strong></div><div><p className="text-xs text-slate-500">Gider USD</p><strong className="text-sm font-mono-num">{companyMoney(c.expenses)}</strong></div>
      <div><p className="text-xs text-slate-500">Kasaya Muhasebe Kaydı</p><strong className={`text-sm font-mono-num ${c.net_profit < 0 ? "text-rose-700" : "text-emerald-700"}`} data-testid={`closing-net-${c.id}`}>{companyMoney(c.net_profit)}</strong></div><div><p className="text-xs text-slate-500">Durum</p><strong className="text-sm" data-testid={`closing-status-${c.id}`}>{c.status === "posted" ? "Kaydedildi" : "Kur Bekliyor"}</strong><div className="flex justify-end gap-1 mt-2"><Button variant="ghost" size="icon" onClick={() => setEditingClosing(c)} aria-label="Kapanış kaydını düzenle" data-testid={`edit-closing-${c.id}`}><Pencil className="w-4 h-4" /></Button><Button variant="ghost" size="icon" onClick={() => removeClosings([c.id])} aria-label="Kapanış kaydını sil" data-testid={`delete-closing-${c.id}`} className="text-slate-400 hover:text-rose-600"><Trash2 className="w-4 h-4" /></Button></div></div>
      {c.error && <p className="col-span-2 lg:col-span-5 text-xs text-rose-700" data-testid={`closing-error-${c.id}`}>{c.error}</p>}
    </article>)}</div>
    {editingClosing && <ClosingEditDialog row={editingClosing} onClose={() => setEditingClosing(null)} onSaved={closings.refresh} />}
    {bulkEditing && <BulkEditDialog title="Kapanışları Toplu Düzenle" description="Yalnızca doldurulan muhasebe alanları uygulanır" endpoint="/company/closings/bulk-update" ids={[...selectedIds]} fields={[{ key: "revenue", label: "Gelir (USD)", type: "number" }, { key: "expenses", label: "Gider (USD)", type: "number" }, { key: "net_profit", label: "Net Kâr / Zarar (USD)", type: "number" }]} onClose={() => setBulkEditing(false)} onSaved={() => { setBulkEditing(false); setSelectedIds(new Set()); closings.refresh(); }} />}

  </div>;
}