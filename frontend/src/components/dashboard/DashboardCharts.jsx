import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, Legend, BarChart, Bar, Cell } from "recharts";
import { formatUsd } from "@/components/FxStatus";

const Panel = ({ title, hint, children, testId, className = "" }) => (
  <section className={`bg-white border border-slate-200 rounded-2xl p-5 min-w-0 ${className}`} data-testid={testId}>
    <div className="flex items-baseline justify-between gap-2 mb-4">
      <h2 className="font-display text-base font-bold text-slate-900">{title}</h2>
      {hint && <span className="text-[11px] text-slate-400">{hint}</span>}
    </div>
    {children}
  </section>
);

const Empty = () => <div className="h-64 flex items-center justify-center text-sm text-slate-400">Bu kapsamda veri yok</div>;
const tip = v => formatUsd(v);

export const RevenueExpenseChart = ({ trend }) => (
  <Panel title="Gelir vs Gider (aylık)" hint="USD" testId="dash-chart-revenue-expense" className="lg:col-span-2">
    {!trend.length ? <Empty /> : <div className="h-64"><ResponsiveContainer>
      <AreaChart data={trend}>
        <defs>
          <linearGradient id="gRev" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#10B981" stopOpacity={0.3} /><stop offset="100%" stopColor="#10B981" stopOpacity={0} /></linearGradient>
          <linearGradient id="gExp" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#F43F5E" stopOpacity={0.25} /><stop offset="100%" stopColor="#F43F5E" stopOpacity={0} /></linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
        <XAxis dataKey="month" tick={{ fontSize: 11 }} stroke="#94A3B8" />
        <YAxis tick={{ fontSize: 11 }} stroke="#94A3B8" width={60} />
        <Tooltip formatter={tip} />
        <Legend wrapperStyle={{ fontSize: 12 }} />
        <Area type="monotone" dataKey="revenue" name="Gelir" stroke="#10B981" fill="url(#gRev)" strokeWidth={2} />
        <Area type="monotone" dataKey="expenses" name="Gider" stroke="#F43F5E" fill="url(#gExp)" strokeWidth={2} />
      </AreaChart>
    </ResponsiveContainer></div>}
  </Panel>
);

export const NetProfitChart = ({ trend }) => (
  <Panel title="Net Kâr (aylık)" hint="USD" testId="dash-chart-net-profit">
    {!trend.length ? <Empty /> : <div className="h-64"><ResponsiveContainer>
      <BarChart data={trend}>
        <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" vertical={false} />
        <XAxis dataKey="month" tick={{ fontSize: 11 }} stroke="#94A3B8" />
        <YAxis tick={{ fontSize: 11 }} stroke="#94A3B8" width={60} />
        <Tooltip formatter={tip} />
        <Bar dataKey="net" name="Net Kâr" radius={[6, 6, 0, 0]}>{trend.map((t, i) => <Cell key={i} fill={t.net >= 0 ? "#6366F1" : "#F43F5E"} />)}</Bar>
      </BarChart>
    </ResponsiveContainer></div>}
  </Panel>
);

export const ChannelChart = ({ insights }) => {
  const data = insights ? [["FBA", insights.fba], ["FBM", insights.fbm], ["Sınıflandırılmamış", insights.unclassified]]
    .filter(([, v]) => v.revenue || v.expenses).map(([name, v]) => ({ name, revenue: v.revenue, net: v.net_profit })) : [];
  return (
    <Panel title="FBA vs FBM Kârlılık" hint="Sınıflandırılmamış = fulfillment bilgisi olmayan siparişler" testId="dash-chart-channel" className="lg:col-span-3">
      {!data.length ? <Empty /> : <div className="h-56"><ResponsiveContainer>
        <BarChart data={data} layout="vertical" margin={{ left: 40 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" horizontal={false} />
          <XAxis type="number" tick={{ fontSize: 11 }} stroke="#94A3B8" />
          <YAxis type="category" dataKey="name" tick={{ fontSize: 12 }} stroke="#94A3B8" width={110} />
          <Tooltip formatter={tip} />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="revenue" name="Gelir" fill="#10B981" radius={[0, 6, 6, 0]} />
          <Bar dataKey="net" name="Net Kâr" fill="#6366F1" radius={[0, 6, 6, 0]} />
        </BarChart>
      </ResponsiveContainer></div>}
    </Panel>
  );
};

export { Panel };
