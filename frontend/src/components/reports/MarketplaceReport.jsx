import { MP_BY_CODE } from "@/constants/marketplaces";
import { formatUsd } from "@/components/FxStatus";

export const MarketplaceReport = ({ data }) => <section><h2 className="font-display text-lg font-bold mb-4">Pazar Yeri Karşılaştırması · USD</h2>
  {!data?.by_marketplace.length && <p className="text-sm text-slate-500" data-testid="report-empty">Bu aralıkta veri yok.</p>}
  {data?.by_marketplace.map(m => <div key={m.marketplace} className="border-b border-slate-200 py-4 grid grid-cols-2 lg:grid-cols-4 gap-4" data-testid={`report-marketplace-${m.marketplace.toLowerCase()}`}><strong className="text-sm col-span-2 lg:col-span-1">{MP_BY_CODE[m.marketplace]?.flag} {MP_BY_CODE[m.marketplace]?.name}</strong>{[["Gelir", m.revenue], ["Gider", m.expenses], ["Net Kâr", m.net]].map(([label, amount], i) => <div key={label}><p className="text-xs text-slate-500">{label}</p><strong className={`text-sm font-mono-num break-all ${i === 2 ? amount < 0 ? "text-rose-700" : "text-emerald-700" : ""}`} data-testid={`report-${m.marketplace.toLowerCase()}-${i}`}>{formatUsd(amount)}</strong></div>)}</div>)}
</section>;