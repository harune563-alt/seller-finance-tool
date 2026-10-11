import { formatUsd } from "@/components/FxStatus";
import { StockBadge } from "@/components/fba/StockStatus";
import { Panel } from "@/components/dashboard/DashboardCharts";

const pct = v => v == null ? "—" : `${v > 0 ? "+" : ""}${Number(v).toFixed(1)}%`;

const AsinList = ({ title, rows, testId }) => (
  <Panel title={title} hint="FBA · FIFO" testId={testId}>
    {!rows.length ? <p className="text-sm text-slate-400 py-6 text-center">FBA satışı yok</p> : (
      <ul className="divide-y divide-slate-100">
        {rows.map(r => <li key={r.asin} className="py-2.5 flex items-center justify-between gap-3" data-testid={`${testId}-${r.asin}`}>
          <div className="min-w-0">
            <p className="text-sm font-medium text-slate-900 truncate" title={r.product_name}>{r.product_name || r.asin}</p>
            <p className="text-[11px] text-slate-500 font-mono">{r.asin} · {r.units_sold} adet · {r.orders} sipariş</p>
          </div>
          <div className="text-right shrink-0">
            <p className={`text-sm font-mono-num font-semibold ${r.net_profit_usd < 0 ? "text-rose-600" : "text-emerald-700"}`}>{formatUsd(r.net_profit_usd)}</p>
            <p className="text-[11px] text-slate-400">{pct(r.margin_percent)}</p>
          </div>
        </li>)}
      </ul>
    )}
  </Panel>
);

export const DashboardInsights = ({ insights }) => (
  <div className="grid grid-cols-1 lg:grid-cols-3 gap-4" data-testid="dash-insights">
    <AsinList title="En Kârlı ASIN'ler" rows={insights?.top_asins || []} testId="dash-top-asins" />
    <AsinList title="En Düşük Kârlı ASIN'ler" rows={insights?.bottom_asins || []} testId="dash-bottom-asins" />
    <Panel title="Düşük Stoklu FBA Ürünleri" testId="dash-low-stock">
      {!insights?.low_stock?.length ? <p className="text-sm text-slate-400 py-6 text-center">Stok uyarısı yok</p> : (
        <ul className="divide-y divide-slate-100">
          {insights.low_stock.map(r => <li key={`${r.store_id}-${r.sku}`} className="py-2.5 flex items-center justify-between gap-3" data-testid={`dash-low-stock-${r.sku}`}>
            <div className="min-w-0">
              <p className="text-sm font-medium text-slate-900 truncate">{r.product_name || r.sku}</p>
              <p className="text-[11px] text-slate-500"><span className="font-mono">{r.sku}</span> · {r.store_name}</p>
            </div>
            <div className="text-right shrink-0">
              <StockBadge status={r.stock_status} />
              <p className="text-[11px] text-slate-500 mt-1">{r.remaining_units} adet{r.threshold != null && ` / eşik ${r.threshold}`}</p>
            </div>
          </li>)}
        </ul>
      )}
    </Panel>
  </div>
);
