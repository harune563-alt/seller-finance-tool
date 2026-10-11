import { formatUsd } from "@/components/FxStatus";

export const STATUS = {
  costed: { label: "FBA FIFO", cls: "bg-emerald-100 text-emerald-800" },
  partial: { label: "Kısmi FBA Maliyeti", cls: "bg-amber-100 text-amber-800" },
  missing: { label: "Missing FBA Cost", cls: "bg-rose-100 text-rose-700" },
};

export const CostStatusBadge = ({ status, testId }) => {
  const s = STATUS[status] || STATUS.missing;
  return <span className={`px-1.5 py-0.5 rounded-full text-[10px] font-semibold whitespace-nowrap ${s.cls}`} data-testid={testId}>{s.label}</span>;
};

export const pct = v => v == null ? "—" : `${v > 0 ? "+" : ""}${Number(v).toFixed(2)}%`;
export const usd = formatUsd;
export const unitUsd = v => v == null ? "—" : `$${Number(v).toFixed(4).replace(/0{1,2}$/, "")}`;
export const tone = v => v == null ? "text-slate-500" : v < 0 ? "text-rose-600" : v > 0 ? "text-emerald-700" : "text-slate-700";

export const Th = ({ children, right }) => <th className={`py-2 px-3 font-semibold whitespace-nowrap ${right ? "text-right" : "text-left"}`}>{children}</th>;
export const Td = ({ children, right, className = "", ...p }) => <td className={`py-2 px-3 whitespace-nowrap ${right ? "text-right font-mono-num" : ""} ${className}`} {...p}>{children}</td>;

export const Metric = ({ label, value, hint, valueClass = "text-slate-900", testId }) => (
  <div className="border border-slate-200 bg-white rounded-xl px-4 py-4 min-w-0" data-testid={testId}>
    <p className="text-xs text-slate-500">{label}</p>
    <p className={`font-display text-2xl font-bold break-all ${valueClass}`} data-testid={`${testId}-value`}>{value}</p>
    {hint && <p className="text-xs text-slate-400 mt-1">{hint}</p>}
  </div>
);

export const TableCard = ({ children, testId }) => (
  <div className="border border-slate-200 rounded-xl bg-white overflow-x-auto">
    <table className="w-full text-sm" data-testid={testId}>{children}</table>
  </div>
);

export const THead = ({ cols }) => (
  <thead className="bg-slate-50 text-xs uppercase text-slate-500">
    <tr>{cols.map(([label, right]) => <Th key={label} right={right}>{label}</Th>)}</tr>
  </thead>
);

export const EmptyRow = ({ cols, text, testId }) => <tr><td colSpan={cols} className="text-center text-slate-500 py-6" data-testid={testId}>{text}</td></tr>;
