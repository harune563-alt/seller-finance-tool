export const pct = v => v == null ? "—" : `${Number(v).toFixed(1)}%`;
export const roasFmt = v => v == null ? "—" : `${Number(v).toFixed(2)}x`;
export const num = v => new Intl.NumberFormat("tr-TR").format(Number(v || 0));

export const STATUS_STYLES = {
  reconciled: "bg-emerald-50 text-emerald-700",
  partially_reconciled: "bg-amber-50 text-amber-700",
  pending_match: "bg-sky-50 text-sky-700",
  financial_only: "bg-rose-50 text-rose-700",
  ppc_only: "bg-indigo-50 text-indigo-700",
  unmatched: "bg-slate-100 text-slate-600",
};

export const StatusPill = ({ status, label, testId }) => (
  <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-semibold whitespace-nowrap ${STATUS_STYLES[status] || "bg-slate-100 text-slate-600"}`} data-testid={testId}>
    {label || status}
  </span>
);

export const FINANCE_NOTE = "Finansal reklam gideri Amazon Payments kaydından gelir. PPC kayıtları bu gideri ASIN ve kampanyalara dağıtır; ikinci kez gider oluşturmaz.";
