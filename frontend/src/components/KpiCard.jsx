export default function KpiCard({ label, value, hint, icon: Icon, accent = "slate", testId }) {
  const accents = {
    emerald: { bg: "bg-emerald-50", text: "text-emerald-700", ring: "ring-emerald-200" },
    rose: { bg: "bg-rose-50", text: "text-rose-700", ring: "ring-rose-200" },
    indigo: { bg: "bg-indigo-50", text: "text-indigo-700", ring: "ring-indigo-200" },
    amber: { bg: "bg-amber-50", text: "text-amber-700", ring: "ring-amber-200" },
    slate: { bg: "bg-slate-100", text: "text-slate-700", ring: "ring-slate-200" },
    amazon: { bg: "bg-orange-50", text: "text-orange-700", ring: "ring-orange-200" },
  };
  const a = accents[accent] || accents.slate;
  return (
    <div className="kpi-card" data-testid={testId}>
      <div className="flex items-start justify-between">
        <div className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          {label}
        </div>
        {Icon && (
          <div className={`w-9 h-9 rounded-xl flex items-center justify-center ${a.bg} ${a.text} ring-1 ${a.ring}`}>
            <Icon className="w-4 h-4" />
          </div>
        )}
      </div>
      <div className="mt-3 font-mono-num text-2xl sm:text-3xl font-extrabold text-slate-900">
        {value}
      </div>
      {hint && <div className="mt-1 text-xs text-slate-500">{hint}</div>}
    </div>
  );
}
