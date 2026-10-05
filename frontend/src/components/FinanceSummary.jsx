import { TrendingUp, TrendingDown, DollarSign } from "lucide-react";
import KpiCard from "@/components/KpiCard";
import { formatMoney } from "@/constants/marketplaces";

export const FinanceSummary = ({ summary, currency, prefix = "tx", loading = false }) => (
  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4" data-testid={`${prefix}-summary`} aria-live="polite">
    <KpiCard label="Toplam Gelir" value={loading ? "…" : formatMoney(summary?.revenue, currency)}
      accent="emerald" icon={TrendingUp} testId={`${prefix}-total-income`} />
    <KpiCard label="Toplam Gider" value={loading ? "…" : formatMoney(summary?.expenses, currency)}
      hint="İadeler, ücretler ve maliyetler" accent="rose" icon={TrendingDown} testId={`${prefix}-total-expenses`} />
    <KpiCard label="Net Kâr" value={loading ? "…" : formatMoney(summary?.net_profit, currency)}
      hint="Toplam gelir − toplam gider" accent="indigo" icon={DollarSign} testId={`${prefix}-net-profit`} />
  </div>
);