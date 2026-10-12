import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

const DAY = 86400000;
const iso = d => d.toISOString().slice(0, 10);

/** Same-length period immediately before [start, end]; null for "all time". */
export const previousRange = (start, end) => {
  if (!start || !end || start > end) return null;
  const s = new Date(`${start}T00:00:00Z`), e = new Date(`${end}T00:00:00Z`);
  const days = Math.round((e - s) / DAY) + 1;
  const prevEnd = new Date(s.getTime() - DAY);
  const prevStart = new Date(prevEnd.getTime() - (days - 1) * DAY);
  return [iso(prevStart), iso(prevEnd)];
};

/** Change vs previous period. kind "pp" = percentage-point diff (margins). */
export const delta = (cur, prev, kind = "pct") => {
  if (cur == null || prev == null) return null;
  if (kind === "pp") return { value: cur - prev, unit: "pp" };
  if (prev === 0) return cur === 0 ? null : { value: null, unit: "new" };
  return { value: ((cur - prev) / Math.abs(prev)) * 100, unit: "%" };
};

export const DeltaBadge = ({ d, inverse = false, dark = false, testId }) => {
  if (!d) return null;
  if (d.unit === "new") {
    return <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold ${dark ? "bg-white/10 text-white/80" : "bg-slate-100 text-slate-600"}`} data-testid={testId}>Yeni</span>;
  }
  const flat = Math.abs(d.value) < 0.05;
  const good = flat ? null : (d.value > 0) !== inverse;
  const Icon = flat ? Minus : d.value > 0 ? ArrowUpRight : ArrowDownRight;
  const palette = dark
    ? flat ? "bg-white/10 text-white/70" : good ? "bg-emerald-400/15 text-emerald-300" : "bg-rose-400/15 text-rose-300"
    : flat ? "bg-slate-100 text-slate-500" : good ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700";
  const text = `${d.value > 0 ? "+" : ""}${d.value.toFixed(1)}${d.unit === "pp" ? " pp" : "%"}`;
  return <span className={`inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-[11px] font-semibold font-mono-num ${palette}`} data-testid={testId} title="Önceki döneme göre">
    <Icon className="w-3 h-3" />{text}
  </span>;
};

export const HeroMetric = ({ label, value, hint, icon: Icon, d, inverse, testId, tone }) => (
  <div className="relative min-w-0 rounded-2xl bg-white/[0.06] ring-1 ring-white/10 p-5 backdrop-blur-sm transition-colors hover:bg-white/[0.09]" data-testid={testId}>
    <div className="flex items-center justify-between gap-2">
      <span className="text-[11px] font-semibold uppercase tracking-[0.14em] text-emerald-100/70">{label}</span>
      {Icon && <span className="w-8 h-8 rounded-xl bg-white/10 flex items-center justify-center text-emerald-200"><Icon className="w-4 h-4" /></span>}
    </div>
    <div className={`mt-4 font-mono-num text-3xl xl:text-[2rem] font-bold tracking-tight break-all ${tone || "text-white"}`} data-testid={`${testId}-value`}>{value}</div>
    <div className="mt-2 flex flex-wrap items-center gap-2 min-h-[22px]">
      <DeltaBadge d={d} inverse={inverse} dark testId={`${testId}-delta`} />
      {hint && <span className="text-xs text-emerald-100/60">{hint}</span>}
    </div>
  </div>
);

const ACCENTS = {
  emerald: "bg-emerald-50 text-emerald-600", rose: "bg-rose-50 text-rose-600", indigo: "bg-indigo-50 text-indigo-600",
  amber: "bg-amber-50 text-amber-600", slate: "bg-slate-100 text-slate-600", amazon: "bg-orange-50 text-orange-600",
};

export const StatCard = ({ label, value, hint, icon: Icon, accent = "slate", d, inverse, testId }) => (
  <div className="group min-w-0 rounded-2xl bg-white p-4 ring-1 ring-slate-200/70 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_-12px_rgba(15,23,42,0.08)] transition-all hover:-translate-y-0.5 hover:shadow-[0_1px_2px_rgba(15,23,42,0.04),0_16px_32px_-12px_rgba(15,23,42,0.16)]" data-testid={testId}>
    <div className="flex items-center gap-3">
      {Icon && <span className={`w-9 h-9 shrink-0 rounded-xl flex items-center justify-center ${ACCENTS[accent] || ACCENTS.slate}`}><Icon className="w-4 h-4" /></span>}
      <span className="text-xs font-medium text-slate-500 leading-tight">{label}</span>
    </div>
    <div className="mt-3 font-mono-num text-xl font-bold text-slate-900 break-all" data-testid={`${testId}-value`}>{value}</div>
    <div className="mt-1.5 flex flex-wrap items-center gap-2 min-h-[20px]">
      <DeltaBadge d={d} inverse={inverse} testId={`${testId}-delta`} />
      {hint && <span className="text-[11px] text-slate-400">{hint}</span>}
    </div>
  </div>
);
