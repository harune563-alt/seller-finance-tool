import { useEffect, useState } from "react";
import { useCompanyResource } from "@/hooks/useCompanyResource";
import { FormError } from "@/components/company/Fields";
import { formatUsd } from "@/components/FxStatus";
import { Button } from "@/components/ui/button";
import { ChevronLeft, ChevronRight } from "lucide-react";

export const DetailedOrders = ({ query }) => {
  const [page, setPage] = useState(1);
  useEffect(() => { setPage(1); }, [query]);
  const resource = useCompanyResource(query ? `/reports/orders?${query}&page=${page}` : null);
  useEffect(() => { if (resource.data && resource.data.page !== page) setPage(resource.data.page); }, [resource.data, page]);
  return <section className="space-y-4" data-testid="detailed-order-report"><div className="flex flex-wrap justify-between gap-3"><h2 className="font-display font-bold text-lg">Sipariş Ayrıntıları</h2><span className="text-xs text-slate-500" data-testid="report-order-count">{resource.data?.total ?? "—"} sipariş/kayıt · Dönem içi hareketler</span></div><FormError error={resource.error} id="report-orders-error" />
    {resource.loading ? <p data-testid="report-orders-loading">Yükleniyor…</p> : !resource.data?.items.length ? <p className="text-sm text-slate-500" data-testid="report-orders-empty">Bu aralıkta sipariş hareketi yok.</p> : resource.data.items.map((o, i) => <article key={`${o.store_id}-${o.marketplace}-${o.order_id}-${i}`} data-testid={`report-order-${i}`} data-order-id={o.order_id} className={`border rounded-lg p-4 grid grid-cols-2 lg:grid-cols-6 gap-4 ${o.net_profit < 0 ? "bg-rose-50 border-rose-200" : "bg-white border-slate-200"}`}>
      <div className="col-span-2"><strong className="text-sm break-all">{o.order_id || "Siparişsiz işlem"}</strong><p className="text-xs text-slate-500 mt-1">{o.store_name} · {o.marketplace} · {o.currency}</p><p className="text-xs text-slate-500 mt-1">{o.first_date} — {o.last_date} · {o.records} hareket</p></div>
      {[["Gelir USD", o.revenue], ["Gider USD", o.expenses], ["Net Kâr USD", o.net_profit]].map(([label, value], index) => <div key={label}><p className="text-xs text-slate-500">{label}</p><strong className={`text-sm font-mono-num break-all ${index === 2 ? value < 0 ? "text-rose-700" : "text-emerald-700" : ""}`} data-testid={`report-order-${i}-metric-${index}`}>{formatUsd(value)}</strong></div>)}
      <div><p className="text-xs text-slate-500">Marj</p><strong className="text-sm font-mono-num" data-testid={`report-order-${i}-margin`}>{o.revenue > 0 && o.margin != null ? `${o.margin.toFixed(2)}%` : "—"}</strong></div>
    </article>)}
    {(resource.data?.total_pages || 0) > 1 && <div className="flex flex-wrap justify-between items-center gap-3" data-testid="report-orders-pagination"><span className="text-xs text-slate-500">Sayfa {page} / {resource.data.total_pages}</span><div className="flex gap-2"><Button variant="outline" disabled={page <= 1 || resource.loading} onClick={() => setPage(p => p - 1)} data-testid="report-orders-previous"><ChevronLeft className="w-4 h-4" /></Button><Button variant="outline" disabled={page >= resource.data.total_pages || resource.loading} onClick={() => setPage(p => p + 1)} data-testid="report-orders-next"><ChevronRight className="w-4 h-4" /></Button></div></div>}
  </section>;
};