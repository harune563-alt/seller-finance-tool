import { TrendingUp, TrendingDown, DollarSign } from "lucide-react";
import KpiCard from "@/components/KpiCard";
import { formatUsd } from "@/components/FxStatus";

export const FinanceSummary = ({ summary, prefix = "tx", loading = false }) => (
  <div className="grid grid-cols-1 sm:grid-cols-3 gap-4" data-testid={`${prefix}-summary`} aria-live="polite">
    <KpiCard label="Toplam Gelir (USD)" value={loading ? "…" : formatUsd(summary?.revenue)}
      accent="emerald" icon={TrendingUp} testId={`${prefix}-total-income`} />
    <KpiCard label="Toplam Gider (USD)" value={loading ? "…" : formatUsd(summary?.expenses)}
      hint="İadeler, ücretler ve maliyetler" accent="rose" icon={TrendingDown} testId={`${prefix}-total-expenses`} />
    <KpiCard label="Net Kâr (USD)" value={loading ? "…" : formatUsd(summary?.net_profit)}
      hint="Toplam gelir − toplam gider" accent="indigo" icon={DollarSign} testId={`${prefix}-net-profit`} />
  </div>
);