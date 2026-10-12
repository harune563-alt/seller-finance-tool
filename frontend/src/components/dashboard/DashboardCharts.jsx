import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, BarChart, Bar, Cell } from "recharts";
import { formatUsd } from "@/components/FxStatus";

const Panel = ({ title, hint, children, testId, className = "", legend }) => (
  <section className={`bg-white rounded-2xl p-5 min-w-0 ring-1 ring-slate-200/70 shadow-[0_1px_2px_rgba(15,23,42,0.04),0_8px_24px_-12px_rgba(15,23,42,0.08)] ${className}`} data-testid={testId}>
    <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
      <h2 className="font-display text-base font-bold text-slate-900">{title}</h2>
      <div className="flex flex-wrap items-center gap-3">
        {legend?.map(([label, color]) => <span key={label} className="inline-flex items-center gap-1.5 text-[11px] font-medium text-slate-500"><span className="w-2.5 h-2.5 rounded-full" style={{ background: color }} />{label}</span>)}
        {hint && <span className="text-[11px] text-slate-400">{hint}</span>}
      </div>
    </div>
    {children}
  </section>
);

const C = { revenue: "#10B981", expense: "#F43F5E", profit: "#6366F1", grid: "#EEF2F7", axis: "#94A3B8" };
const compact = v => {
  const n = Number(v), a = Math.abs(n), sign = n < 0 ? "-" : "";
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(1)}K`;
  return `${sign}$${Math.round(a)}`;
};
const withZero = [min => Math.min(0, min), max => Math.max(0, max)];
const axis = { tick: { fontSize: 11, fill: C.axis }, axisLine: false, tickLine: false };
const Empty = () => <div className="h-64 flex flex-col items-center justify-center gap-2 text-sm text-slate-400"><div className="w-10 h-10 rounded-full bg-slate-50 ring-1 ring-slate-100" />Bu kapsamda veri yok</div>;

const ChartTip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null;
  return <div className="rounded-xl bg-slate-900/95 text-white px-3 py-2 shadow-xl ring-1 ring-white/10 text-xs">
    <p className="font-semibold text-white/70 mb-1">{label}</p>
    {payload.map(p => {
      const raw = p.payload?.fill || p.color || p.stroke;
      const dot = !raw || String(raw).startsWith("url") ? (p.value < 0 ? C.expense : C.profit) : raw;
      return <p key={p.dataKey} className="flex items-center gap-2 font-mono-num">
        <span className="w-2 h-2 rounded-full" style={{ background: dot }} />{p.name}: <strong>{formatUsd(p.value)}</strong>
      </p>;
    })}
  </div>;
};

export const RevenueExpenseChart = ({ trend }) => (
  <Panel title="Gelir vs Gider" hint="Aylık · USD" testId="dash-chart-revenue-expense" className="lg:col-span-2" legend={[["Gelir", C.revenue], ["Gider", C.expense]]}>
    {!trend.length ? <Empty /> : trend.length === 1 ? <div className="h-64"><ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 320, height: 200 }}>
      <BarChart data={trend} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barGap={10}>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="month" {...axis} dy={6} />
        <YAxis {...axis} width={56} tickFormatter={compact} />
        <Tooltip content={<ChartTip />} cursor={{ fill: "rgba(148,163,184,0.08)" }} />
        <Bar dataKey="revenue" name="Gelir" fill={C.revenue} radius={[10, 10, 4, 4]} maxBarSize={56} />
        <Bar dataKey="expenses" name="Gider" fill={C.expense} radius={[10, 10, 4, 4]} maxBarSize={56} />
      </BarChart>
    </ResponsiveContainer></div> : <div className="h-64"><ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 320, height: 200 }}>
      <AreaChart data={trend} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="gRev" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={C.revenue} stopOpacity={0.35} /><stop offset="95%" stopColor={C.revenue} stopOpacity={0} /></linearGradient>
          <linearGradient id="gExp" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor={C.expense} stopOpacity={0.25} /><stop offset="95%" stopColor={C.expense} stopOpacity={0} /></linearGradient>
        </defs>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="month" {...axis} dy={6} />
        <YAxis {...axis} width={56} tickFormatter={compact} />
        <Tooltip content={<ChartTip />} cursor={{ stroke: "#CBD5E1", strokeDasharray: "4 4" }} />
        <Area type="monotone" dataKey="revenue" name="Gelir" stroke={C.revenue} fill="url(#gRev)" strokeWidth={2.5} dot={trend.length === 1 ? { r: 4, fill: C.revenue } : false} activeDot={{ r: 5, strokeWidth: 2, stroke: "#fff" }} />
        <Area type="monotone" dataKey="expenses" name="Gider" stroke={C.expense} fill="url(#gExp)" strokeWidth={2.5} dot={trend.length === 1 ? { r: 4, fill: C.expense } : false} activeDot={{ r: 5, strokeWidth: 2, stroke: "#fff" }} />
      </AreaChart>
    </ResponsiveContainer></div>}
  </Panel>
);

export const NetProfitChart = ({ trend }) => (
  <Panel title="Net Kâr" hint="Aylık · USD" testId="dash-chart-net-profit" legend={[["Kâr", C.profit], ["Zarar", C.expense]]}>
    {!trend.length ? <Empty /> : <div className="h-64"><ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 320, height: 200 }}>
      <BarChart data={trend} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="gPos" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#818CF8" /><stop offset="100%" stopColor={C.profit} /></linearGradient>
          <linearGradient id="gNeg" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#FB7185" /><stop offset="100%" stopColor={C.expense} /></linearGradient>
        </defs>
        <CartesianGrid stroke={C.grid} vertical={false} />
        <XAxis dataKey="month" {...axis} dy={6} />
        <YAxis {...axis} width={56} tickFormatter={compact} domain={withZero} />
        <Tooltip content={<ChartTip />} cursor={{ fill: "rgba(148,163,184,0.08)" }} />
        <Bar dataKey="net" name="Net Kâr" radius={[10, 10, 10, 10]} maxBarSize={48}>{trend.map((t, i) => <Cell key={i} fill={t.net >= 0 ? "url(#gPos)" : "url(#gNeg)"} />)}</Bar>
      </BarChart>
    </ResponsiveContainer></div>}
  </Panel>
);

export const ChannelChart = ({ insights }) => {
  const data = insights ? [["FBA", insights.fba], ["FBM", insights.fbm], ["Sınıflandırılmamış", insights.unclassified]]
    .filter(([, v]) => v.revenue || v.expenses).map(([name, v]) => ({ name, revenue: v.revenue, net: v.net_profit })) : [];
  return (
    <Panel title="FBA vs FBM Kârlılık" hint="Sınıflandırılmamış = fulfillment bilgisi olmayan siparişler" testId="dash-chart-channel" className="lg:col-span-3" legend={[["Gelir", C.revenue], ["Net Kâr", C.profit]]}>
      {!data.length ? <Empty /> : <div style={{ height: Math.max(140, data.length * 72) }}><ResponsiveContainer width="100%" height="100%" initialDimension={{ width: 320, height: 200 }}>
        <BarChart data={data} layout="vertical" margin={{ top: 0, right: 16, left: 8, bottom: 0 }} barGap={4}>
          <CartesianGrid stroke={C.grid} horizontal={false} />
          <XAxis type="number" {...axis} tickFormatter={compact} />
          <YAxis type="category" dataKey="name" {...axis} tick={{ fontSize: 12, fill: "#475569", fontWeight: 600 }} width={130} />
          <Tooltip content={<ChartTip />} cursor={{ fill: "rgba(148,163,184,0.08)" }} />
          <Bar dataKey="revenue" name="Gelir" fill={C.revenue} radius={[8, 8, 8, 8]} maxBarSize={18} />
          <Bar dataKey="net" name="Net Kâr" radius={[8, 8, 8, 8]} maxBarSize={18}>{data.map((d, i) => <Cell key={i} fill={d.net >= 0 ? C.profit : C.expense} />)}</Bar>
        </BarChart>
      </ResponsiveContainer></div>}
    </Panel>
  );
};

export { Panel };
