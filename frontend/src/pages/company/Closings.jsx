import { useState } from "react";
import { RefreshCw, CalendarCheck } from "lucide-react";
import { toast } from "sonner";
import api from "@/lib/api";
import { useCompanyResource } from "@/hooks/useCompanyResource";
import { Button } from "@/components/ui/button";
import { companyMoney, FormError, apiError } from "@/components/company/Fields";

const states = { pending: "Sırada", running: "Hesaplanıyor", completed: "Tamamlandı", failed: "Başarısız", interrupted: "Yeniden eşitlendi" };
export default function Closings() {
  const closings = useCompanyResource("/company/closings"), jobs = useCompanyResource("/company/jobs");
  const [busy, setBusy] = useState(false), [error, setError] = useState("");
  const refresh = () => { closings.refresh(); jobs.refresh(); };
  const run = async () => { setBusy(true); setError(""); try { await api.post("/company/closings/run"); toast.success("Kapanış eşitlemesi sıraya alındı"); refresh(); } catch (e) { setError(apiError(e)); } finally { setBusy(false); } };
  return <div className="space-y-6" data-testid="closings-page">
    <div className="flex flex-wrap justify-between gap-4 items-start"><div><h2 className="text-lg font-display font-bold">Aylık Mağaza Kapanışları</h2><p className="mt-2 text-sm text-slate-500" data-testid="closing-policy">Kapalı aylar · Her mağaza/ay için tek muhasebe kaydı · USD</p></div><div className="flex gap-2 flex-wrap"><Button variant="outline" onClick={refresh} data-testid="refresh-closings"><RefreshCw className="w-4 h-4 mr-2" />Durumu Yenile</Button><Button onClick={run} disabled={busy} data-testid="run-monthly-close-button"><CalendarCheck className="w-4 h-4 mr-2" />{busy ? "Başlatılıyor…" : "Kapanışları Eşitle"}</Button></div></div>
    <div className="border-y border-slate-200 py-4 text-xs text-slate-500 space-y-2" data-testid="closing-accounting-note"><p>Otomatik kontrol: her gün 03:00 UTC. İçinde bulunulan ay aktarılmaz. Geçmiş değişiklikler aynı kapanış kaydını revize eder.</p><p>Bu kayıt gerçek banka/Amazon transferi değildir; nakit kasasından ayrı muhasebe bakiyesidir.</p></div>
    <FormError error={error || closings.error || jobs.error} id="closing-error" />
    {jobs.data?.[0] && <div className="flex flex-wrap justify-between gap-3 text-sm border-l-4 border-emerald-500 bg-white p-4" data-testid="latest-closing-job"><span>Son eşitleme: <strong data-testid="closing-job-status">{states[jobs.data[0].status] || jobs.data[0].status}</strong></span><span className="text-xs text-slate-500">{new Date(jobs.data[0].updated_at).toLocaleString("tr-TR")} · {jobs.data[0].processed} mağaza/ay</span>{jobs.data[0].error && <span role="alert" className="text-rose-700" data-testid="closing-job-error">{jobs.data[0].error}</span>}</div>}
    <div className="space-y-3" data-testid="treasury-ledger-table">{closings.loading ? <p data-testid="closings-loading">Yükleniyor…</p> : !closings.data?.length ? <p className="text-sm text-slate-500 py-8 text-center border border-dashed rounded-lg" data-testid="closings-empty">Henüz kapanmış ay kaydı yok.</p> : closings.data.map(c => <article key={c.id} className={`rounded-lg border p-5 grid grid-cols-2 lg:grid-cols-5 gap-4 ${c.net_profit < 0 ? "bg-rose-50 border-rose-200" : "bg-white border-slate-200"}`} data-testid={`closing-${c.id}`}>
      <div className="col-span-2 lg:col-span-1"><strong className="text-sm break-words">{c.store_name}</strong><p className="text-xs text-slate-500 mt-1">{c.period} · Revizyon {c.revision}</p></div>
      <div><p className="text-xs text-slate-500">Gelir USD</p><strong className="text-sm font-mono-num">{companyMoney(c.revenue)}</strong></div><div><p className="text-xs text-slate-500">Gider USD</p><strong className="text-sm font-mono-num">{companyMoney(c.expenses)}</strong></div>
      <div><p className="text-xs text-slate-500">Kasaya Muhasebe Kaydı</p><strong className={`text-sm font-mono-num ${c.net_profit < 0 ? "text-rose-700" : "text-emerald-700"}`} data-testid={`closing-net-${c.id}`}>{companyMoney(c.net_profit)}</strong></div><div><p className="text-xs text-slate-500">Durum</p><strong className="text-sm" data-testid={`closing-status-${c.id}`}>{c.status === "posted" ? "Kaydedildi" : "Kur Bekliyor"}</strong></div>
      {c.error && <p className="col-span-2 lg:col-span-5 text-xs text-rose-700" data-testid={`closing-error-${c.id}`}>{c.error}</p>}
    </article>)}</div>
  </div>;
}