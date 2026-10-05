import { useMemo, useState } from "react";
import { ChevronDown, ChevronUp, Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { COST_FIELDS, RECOVERY_FIELDS, MP_BY_CODE, formatMoney } from "@/constants/marketplaces";
import { groupOrders } from "@/lib/orderFinance";
import { FxStatus, formatUsd } from "@/components/FxStatus";

const TransactionDetail = ({ row: r, onEdit, onDelete }) => {
  const income = r.type === "income";
  const refund = r.category === "Refunds";
  const fields = income ? COST_FIELDS : refund ? RECOVERY_FIELDS : [];
  return <div className="p-4 border-t border-slate-200 bg-white" data-testid={`tx-row-${r.id}`}>
    <div className="flex flex-wrap gap-3 justify-between items-center">
      <div className="min-w-0"><div className="text-sm font-semibold" data-testid={`tx-category-${r.id}`}>{r.category}</div><p className="text-xs text-slate-500 mt-1">{r.date}{r.source === "amazon_payments_csv" ? " · CSV" : ""}</p></div>
      <div className="flex flex-wrap items-center gap-3"><strong className={`font-mono-num text-sm ${income ? "text-emerald-700" : "text-rose-600"}`} data-testid={`tx-amount-${r.id}`}>{formatMoney(income ? r.amount : -r.amount, r.currency)}</strong><div className="flex">
        {(income || refund) && <Button variant="ghost" size="icon" disabled={r.fx_status !== "ready"} title={refund ? "Geri kazanımları düzenle" : "Maliyetleri düzenle"} aria-label={refund ? "Geri kazanımları düzenle" : "Maliyetleri düzenle"} data-testid={`edit-costs-${r.id}`} onClick={() => onEdit(r)}><Pencil className="w-4 h-4" /></Button>}
        <Button variant="ghost" size="icon" title="İşlemi sil" aria-label="İşlemi sil" data-testid={`delete-tx-${r.id}`} onClick={() => onDelete(r)} className="text-slate-400 hover:text-rose-600"><Trash2 className="w-4 h-4" /></Button>
      </div></div>
    </div>
    {r.description && <p className="text-xs text-slate-500 break-words mt-2">{r.description}</p>}
    <p className="text-xs mt-2 text-slate-500" data-testid={`tx-usd-amount-${r.id}`}>USD karşılığı: {formatUsd(r.amount_usd == null ? null : income ? r.amount_usd : -r.amount_usd)}</p>
    <FxStatus quote={r.fx} error={r.fx_error} prefix={`detail-${r.id}`} />
    {!!fields.length && <dl className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-3">{fields.map(({ key, label }) => <div key={key}><dt className="text-xs text-slate-500">{label} (USD)</dt><dd className={`text-xs font-mono-num mt-1 ${refund ? "text-emerald-700" : "text-slate-700"}`} data-testid={`tx-${key.replaceAll("_", "-")}-${r.id}`}>{refund ? "+" : "−"}{formatUsd(r.usd_costs?.[key])}</dd>{r.cost_currency !== "USD" && <p className="text-xs text-slate-400" data-testid={`tx-original-${key.replaceAll("_", "-")}-${r.id}`}>Orijinal: {formatMoney(r[key], r.cost_currency)}</p>}</div>)}</dl>}
  </div>;
};

export const TransactionList = ({ rows, total, loading, filter, onEdit, onDelete }) => {
  const [expanded, setExpanded] = useState({});
  const groups = useMemo(() => groupOrders(rows).filter(g => filter === "all" || (filter === "profit" ? g.net > 0 : g.net < 0)), [rows, filter]);
  return <section data-testid="tx-records" className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-display font-bold text-lg" data-testid="tx-record-count">İşlem Kayıtları ({groups.length} / {total ?? groups.length})</h2><span className="text-xs text-slate-500" data-testid="order-margin-definition">USD · Siparişin tüm hareketleri · Kâr/Zarar % = Net sonuç / Gelirin USD karşılığı</span></div>
    <div className="space-y-3" data-testid="tx-table-body">
      {loading && <p className="text-sm text-slate-500 py-8 text-center" data-testid="tx-loading">Yükleniyor…</p>}
      {!loading && !groups.length && <p className="text-sm text-slate-500 py-8 text-center border border-dashed rounded-lg" data-testid="tx-empty">Bu görünümde kayıt yok</p>}
      {!loading && groups.map(g => {
        const tone = g.net < 0 ? "bg-rose-50 border-rose-200" : g.net > 0 ? "bg-emerald-50 border-emerald-200" : "bg-white border-slate-200";
        const text = g.net < 0 ? "text-rose-700" : g.net > 0 ? "text-emerald-700" : "text-slate-700";
        return <article key={g.id} className={`rounded-lg border overflow-hidden ${tone}`} data-testid={`order-row-${g.id}`} data-order-id={g.orderId} data-profit-state={g.net < 0 ? "loss" : g.net > 0 ? "profit" : "neutral"}>
          <div className="p-4 sm:p-5 grid grid-cols-2 md:grid-cols-4 xl:grid-cols-[minmax(180px,2fr)_repeat(4,minmax(0,1fr))_auto] gap-4 items-center">
            <div className="col-span-2 md:col-span-4 xl:col-span-1 min-w-0"><h3 className="text-sm font-semibold break-all" data-testid={`order-id-${g.id}`}>{g.orderId || "Siparişsiz işlem"}</h3><p className="text-xs text-slate-500 mt-1">{MP_BY_CODE[g.marketplace]?.flag} {g.marketplace} · {g.date} · {g.records.length} işlem</p></div>
            <div><div className="text-xs text-slate-500">Gelir (USD)</div><strong className="text-sm font-mono-num break-all" data-testid={`order-revenue-${g.id}`}>{formatUsd(g.revenue)}</strong></div>
            <div><div className="text-xs text-slate-500">Gider (USD)</div><strong className="text-sm font-mono-num break-all" data-testid={`order-expenses-${g.id}`}>{formatUsd(g.expenses)}</strong></div>
            <div><div className="text-xs text-slate-500">Net Kâr / Zarar (USD)</div><strong className={`text-sm font-mono-num break-all ${text}`} data-testid={`order-net-${g.id}`}>{formatUsd(g.net)}</strong></div>
            <div><div className="text-xs text-slate-500">Kâr / Zarar %</div><strong className={`text-sm font-mono-num ${text}`} data-testid={`order-margin-${g.id}`}>{g.margin == null ? "—" : `${g.margin > 0 ? "+" : ""}${g.margin.toFixed(2)}%`}</strong></div>
            <Button variant="ghost" size="sm" className="justify-self-start xl:justify-self-end" aria-expanded={!!expanded[g.id]} aria-controls={`order-details-${g.id}`} data-testid={`toggle-order-${g.id}`} onClick={() => setExpanded(e => ({ ...e, [g.id]: !e[g.id] }))}>{expanded[g.id] ? <ChevronUp className="w-4 h-4 mr-1" /> : <ChevronDown className="w-4 h-4 mr-1" />}Detay</Button>
          </div>
          {expanded[g.id] && <div id={`order-details-${g.id}`} data-testid={`order-details-${g.id}`}>
            <div className="px-4 py-3 border-t border-slate-200 bg-white text-xs flex flex-wrap gap-4"><span>Satış maliyetleri (USD): <strong data-testid={`order-costs-${g.id}`}>{formatUsd(g.costs)}</strong></span><span className="text-emerald-700">Geri kazanımlar (USD): <strong data-testid={`order-recoveries-${g.id}`}>+{formatUsd(g.recovered)}</strong></span></div>
            {g.records.map(r => <TransactionDetail key={r.id} row={r} onEdit={onEdit} onDelete={onDelete} />)}
          </div>}
        </article>;
      })}
    </div>
  </section>;
};