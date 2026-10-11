import KpiCard from "@/components/KpiCard";
import { formatUsd } from "@/components/FxStatus";
import { DollarSign, Megaphone, AlertCircle, TrendingUp, ShoppingCart, MousePointerClick, Eye, Percent, Target, BarChart3 } from "lucide-react";
import { pct, roasFmt, num, StatusPill } from "./ppcFormat";

export const PpcOverview = ({ summary: s = {} }) => (
  <div className="space-y-6" data-testid="ppc-overview">
    <div>
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">Finansal (Amazon Payments)</p>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <KpiCard testId="ppc-financial" label="Finansal Reklam Gideri" accent="rose" icon={DollarSign} value={formatUsd(s.financial_ad_expense_usd)} hint="Amazon Payments'taki gerçek gider (tek kayıt)" />
        <KpiCard testId="ppc-allocated" label="Dağıtılan PPC Harcaması" accent="amber" icon={Megaphone} value={formatUsd(s.allocated_ppc_spend_usd)} hint="ASIN/kampanyaya dağıtım — ekstra gider değil" />
        <KpiCard testId="ppc-unallocated" label="Dağıtılmayan PPC Harcaması" accent="slate" icon={AlertCircle} value={formatUsd(s.unallocated_ppc_spend_usd)} hint="Finansal gider − dağıtılan" />
      </div>
    </div>
    <div>
      <p className="text-xs font-semibold uppercase tracking-wider text-slate-500 mb-3">PPC Performansı (Attribution)</p>
      <div className="grid grid-cols-2 lg:grid-cols-4 xl:grid-cols-7 gap-4">
        <KpiCard testId="ppc-sales" label="PPC Satışları" accent="emerald" icon={TrendingUp} value={formatUsd(s.attributed_ppc_sales_usd)} />
        <KpiCard testId="ppc-orders" label="PPC Siparişleri" accent="indigo" icon={ShoppingCart} value={num(s.orders)} />
        <KpiCard testId="ppc-clicks" label="Tıklama" accent="slate" icon={MousePointerClick} value={num(s.clicks)} />
        <KpiCard testId="ppc-impressions" label="Gösterim" accent="slate" icon={Eye} value={num(s.impressions)} />
        <KpiCard testId="ppc-ctr" label="CTR" accent="indigo" icon={Percent} value={pct(s.ctr_percent)} />
        <KpiCard testId="ppc-acos" label="ACoS" accent="amber" icon={Target} value={pct(s.acos_percent)} />
        <KpiCard testId="ppc-roas" label="ROAS" accent="emerald" icon={BarChart3} value={roasFmt(s.roas)} />
      </div>
    </div>
    {s.status_counts && (
      <div className="flex flex-wrap gap-2 items-center" data-testid="ppc-status-counts">
        <span className="text-xs text-slate-500 mr-1">Kayıt durumları:</span>
        {Object.entries(s.status_counts).map(([k, v]) => (
          <StatusPill key={k} status={k} label={`${s.status_labels?.[k] || k}: ${v}`} testId={`ppc-count-${k}`} />
        ))}
      </div>
    )}
  </div>
);
