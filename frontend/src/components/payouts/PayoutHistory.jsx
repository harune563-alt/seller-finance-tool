import { Pencil, Trash2 } from "lucide-react";
import { MP_BY_CODE, formatMoney } from "@/constants/marketplaces";
import { Button } from "@/components/ui/button";

export const PayoutHistory = ({ history, onEditReference, onDelete }) => (
  <section className="space-y-4" data-testid="payout-history">
    <h2 className="font-display text-lg font-bold text-slate-900" data-testid="payout-history-count">Ödeme Geçmişi ({history.items.length} / {history.total})</h2>
    {history.loading ? <p className="text-sm text-slate-500 py-6" data-testid="payout-history-loading">Yükleniyor…</p> : !history.items.length ? <p className="text-sm text-slate-500 py-8 text-center border border-dashed rounded-lg" data-testid="payout-history-empty">Filtrelerle eşleşen ödeme bulunamadı.</p> : history.items.map(r => <article key={r.id} className="bg-white border border-slate-200 rounded-lg p-4 sm:p-5 grid grid-cols-2 lg:grid-cols-[1fr_1.5fr_1fr_1.5fr_1fr_auto] gap-4 items-center" data-testid={`payout-row-${r.id}`}>
      <div><p className="text-xs text-slate-500">Tarih / Pazar</p><p className="text-sm mt-1" data-testid={`payout-date-${r.id}`}>{r.date}</p><p className="text-xs text-slate-500 mt-1" data-testid={`payout-marketplace-${r.id}`}>{MP_BY_CODE[r.marketplace]?.flag} {r.marketplace}</p></div>
      <div className="min-w-0"><p className="text-xs text-slate-500">Ödeme Referansı</p><p className="text-sm font-semibold mt-1 break-all" data-testid={`payout-reference-${r.id}`}>{r.payment_reference || "Referans yok"}</p></div>
      <div><p className="text-xs text-slate-500">Durum</p><span className={`inline-flex text-xs font-semibold mt-1 px-2 py-1 rounded-md ${r.category === "Bankada" ? "bg-emerald-50 text-emerald-700" : "bg-orange-50 text-orange-700"}`} data-testid={`payout-status-${r.id}`}>{r.category}</span></div>
      <div className="min-w-0"><p className="text-xs text-slate-500">Not</p><p className="text-sm text-slate-600 mt-1 break-words" data-testid={`payout-note-${r.id}`}>{r.description || "—"}</p></div>
      <strong className="text-sm font-mono-num text-orange-600 break-all" data-testid={`payout-amount-${r.id}`}>{formatMoney(r.amount, r.currency)}</strong>
      <div className="flex justify-end"><Button type="button" variant="ghost" size="icon" title="Ödeme referansını düzenle" aria-label="Ödeme referansını düzenle" data-testid={`edit-payout-reference-${r.id}`} onClick={() => onEditReference(r)}><Pencil className="w-4 h-4" /></Button><Button type="button" variant="ghost" size="icon" title="Ödemeyi sil" aria-label="Ödemeyi sil" data-testid={`delete-payout-${r.id}`} onClick={() => onDelete(r.id)} className="text-slate-400 hover:text-rose-600"><Trash2 className="w-4 h-4" /></Button></div>
    </article>)}
  </section>
);