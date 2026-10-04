import { useEffect, useState, useMemo } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { MP_BY_CODE, formatMoney } from "@/constants/marketplaces";
import KpiCard from "@/components/KpiCard";
import { Button } from "@/components/ui/button";
import {
  TrendingUp, TrendingDown, DollarSign, Percent, Wallet, Receipt,
  Sparkles, Store as StoreIcon,
} from "lucide-react";
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  PieChart, Pie, Cell, Legend, BarChart, Bar,
} from "recharts";

const CHART_COLORS = ["#10B981", "#6366F1", "#F59E0B", "#EF4444", "#8B5CF6", "#06B6D4", "#F97316", "#14B8A6"];

export default function Dashboard() {
  const { activeStore, activeStoreId, activeMarketplace, stores } = useStore();
  const [summary, setSummary] = useState(null);
  const [recent, setRecent] = useState([]);
  const [loading, setLoading] = useState(true);

  const currency = useMemo(() => {
    if (activeMarketplace && activeMarketplace !== "ALL") return MP_BY_CODE[activeMarketplace]?.currency || "USD";
    return activeStore?.default_currency || "USD";
  }, [activeMarketplace, activeStore]);

  useEffect(() => {
    if (!activeStoreId) { setLoading(false); return; }
    (async () => {
      setLoading(true);
      try {
        const params = { store_id: activeStoreId };
        if (activeMarketplace !== "ALL") params.marketplace = activeMarketplace;
        const [s, t] = await Promise.all([
          api.get("/dashboard/summary", { params }),
          api.get("/transactions", { params: { ...params, limit: 8 } }),
        ]);
        setSummary(s.data);
        setRecent(t.data);
      } finally {
        setLoading(false);
      }
    })();
  }, [activeStoreId, activeMarketplace]);

  if (!stores.length) {
    return (
      <div className="rounded-2xl bg-white border border-slate-200 p-12 text-center">
        <div className="mx-auto w-14 h-14 rounded-2xl bg-emerald-50 flex items-center justify-center text-emerald-600 mb-4">
          <StoreIcon className="w-7 h-7" />
        </div>
        <h2 className="font-display text-2xl font-extrabold text-slate-900">İlk mağazanı oluştur</h2>
        <p className="text-sm text-slate-500 mt-2 max-w-md mx-auto">
          Takibe başlamak için bir Amazon satıcı mağazası ekle ve içine satış yaptığın pazar yerlerini seç.
        </p>
        <Link to="/stores">
          <Button data-testid="empty-create-store-btn" className="mt-6 bg-slate-900 hover:bg-slate-800 text-white rounded-xl">
            Mağaza Ekle
          </Button>
        </Link>
      </div>
    );
  }

  const kpis = summary || { revenue: 0, expenses: 0, net_profit: 0, margin: 0, amazon_balance: 0 };
  const trendData = (summary?.trend || []).map((t) => ({ ...t, label: t.month }));
  const pieData = (summary?.by_marketplace || [])
    .filter((m) => m.revenue > 0)
    .map((m) => ({ name: m.marketplace, value: m.revenue }));
  const catData = (summary?.by_category || []).sort((a,b) => b.amount - a.amount).slice(0, 8);

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-extrabold text-slate-900 tracking-tight">
            Ana Dashboard
          </h1>
          <p className="text-sm text-slate-500 mt-1">
            {activeStore?.name} · {activeMarketplace === "ALL" ? "Tüm Pazarlar" : `${MP_BY_CODE[activeMarketplace]?.flag} ${MP_BY_CODE[activeMarketplace]?.name}`}
          </p>
        </div>
        <div className="flex gap-2">
          <Link to="/transactions">
            <Button variant="outline" className="rounded-xl bg-white" data-testid="quick-add-income">
              <Receipt className="w-4 h-4 mr-2" /> Gelir / Gider Ekle
            </Button>
          </Link>
          <Link to="/payouts">
            <Button className="bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl" data-testid="quick-add-payout">
              <Wallet className="w-4 h-4 mr-2" /> Amazon Ödemesi
            </Button>
          </Link>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        <KpiCard testId="kpi-revenue" label="Toplam Satış" accent="emerald" icon={TrendingUp}
                 value={formatMoney(kpis.revenue, currency)} hint="Gelir toplamı" />
        <KpiCard testId="kpi-expenses" label="Toplam Gider" accent="rose" icon={TrendingDown}
                 value={formatMoney(kpis.expenses, currency)} hint="FBA, PPC, COGS vb." />
        <KpiCard testId="kpi-net-profit" label="Net Kar" accent="indigo" icon={DollarSign}
                 value={formatMoney(kpis.net_profit, currency)} hint="Gelir − Gider" />
        <KpiCard testId="kpi-margin" label="Kar Marjı" accent="amber" icon={Percent}
                 value={`${(kpis.margin || 0).toFixed(1)}%`} hint="Net Kar / Gelir" />
        <KpiCard testId="kpi-amazon-balance" label="Amazon Bakiye" accent="amazon" icon={Wallet}
                 value={formatMoney(kpis.amazon_balance, currency)} hint="Bekleyen (çekilmemiş)" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white border border-slate-200 rounded-2xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display text-lg font-bold text-slate-900">Gelir ve Kar Trendi</h2>
            <span className="text-xs text-slate-500 font-mono-num">Aylık</span>
          </div>
          <div className="h-72">
            {loading ? (
              <div className="h-full flex items-center justify-center text-sm text-slate-400">Yükleniyor...</div>
            ) : trendData.length === 0 ? (
              <div className="h-full flex items-center justify-center text-sm text-slate-400">Henüz veri yok</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trendData}>
                  <defs>
                    <linearGradient id="revGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#10B981" stopOpacity={0.4} />
                      <stop offset="100%" stopColor="#10B981" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="profGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="#6366F1" stopOpacity={0.35} />
                      <stop offset="100%" stopColor="#6366F1" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" />
                  <XAxis dataKey="label" stroke="#64748B" fontSize={12} />
                  <YAxis stroke="#64748B" fontSize={12} />
                  <Tooltip contentStyle={{ background: "#fff", border: "1px solid #E2E8F0", borderRadius: 12 }} />
                  <Legend />
                  <Area type="monotone" dataKey="revenue" name="Gelir" stroke="#10B981" strokeWidth={2.5} fill="url(#revGrad)" />
                  <Area type="monotone" dataKey="net" name="Net Kar" stroke="#6366F1" strokeWidth={2.5} fill="url(#profGrad)" />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="bg-white border border-slate-200 rounded-2xl p-6">
          <h2 className="font-display text-lg font-bold text-slate-900 mb-4">Pazar Yeri Dağılımı</h2>
          <div className="h-72">
            {pieData.length === 0 ? (
              <div className="h-full flex items-center justify-center text-sm text-slate-400">Veri yok</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={pieData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={95} paddingAngle={3}>
                    {pieData.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
                  </Pie>
                  <Tooltip contentStyle={{ background: "#fff", border: "1px solid #E2E8F0", borderRadius: 12 }} />
                  <Legend iconType="circle" />
                </PieChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="bg-white border border-slate-200 rounded-2xl p-6">
          <h2 className="font-display text-lg font-bold text-slate-900 mb-4">Gider Kategorileri</h2>
          <div className="h-64">
            {catData.length === 0 ? (
              <div className="h-full flex items-center justify-center text-sm text-slate-400">Veri yok</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={catData} layout="vertical" margin={{ left: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#E2E8F0" horizontal={false} />
                  <XAxis type="number" stroke="#64748B" fontSize={11} />
                  <YAxis type="category" dataKey="category" stroke="#64748B" fontSize={11} width={110} />
                  <Tooltip contentStyle={{ background: "#fff", border: "1px solid #E2E8F0", borderRadius: 12 }} />
                  <Bar dataKey="amount" fill="#EF4444" radius={[0, 6, 6, 0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="lg:col-span-2 bg-white border border-slate-200 rounded-2xl p-6" data-testid="recent-transactions">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display text-lg font-bold text-slate-900">Son İşlemler</h2>
            <Link to="/transactions" className="text-xs font-semibold text-emerald-600 hover:underline">
              Tümünü gör →
            </Link>
          </div>
          <div className="divide-y divide-slate-100">
            {recent.length === 0 && (
              <div className="py-8 text-center text-sm text-slate-400">Henüz işlem yok</div>
            )}
            {recent.map((t) => {
              const mp = MP_BY_CODE[t.marketplace];
              const positive = t.type === "income" || t.type === "payout";
              return (
                <div key={t.id} className="py-3 flex items-center justify-between gap-3">
                  <div className="flex items-center gap-3 min-w-0">
                    <div className={`w-9 h-9 rounded-xl flex items-center justify-center text-sm ${
                      t.type === "income" ? "bg-emerald-50 text-emerald-600"
                      : t.type === "expense" ? "bg-rose-50 text-rose-600"
                      : "bg-orange-50 text-orange-600"
                    }`}>
                      {t.type === "income" ? "↑" : t.type === "expense" ? "↓" : "⇄"}
                    </div>
                    <div className="min-w-0">
                      <div className="font-semibold text-sm text-slate-800 truncate">
                        {t.category} <span className="text-slate-400 font-normal">· {mp?.flag} {t.marketplace}</span>
                      </div>
                      <div className="text-xs text-slate-500 truncate">
                        {t.date} {t.description && `· ${t.description}`}
                      </div>
                    </div>
                  </div>
                  <div className={`font-mono-num font-bold text-sm whitespace-nowrap ${positive ? "text-emerald-600" : "text-rose-600"}`}>
                    {positive ? "+" : "−"}{formatMoney(t.amount, t.currency)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      <div className="rounded-2xl border border-dashed border-slate-300 bg-white p-5 flex items-start gap-3">
        <Sparkles className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
        <div className="text-sm text-slate-600">
          <span className="font-semibold text-slate-900">İpucu:</span>{" "}
          CSV import ile Amazon rapor dosyalarını yükleyebilirsin. Gerekli sütunlar:{" "}
          <code className="font-mono-num bg-slate-100 px-1.5 py-0.5 rounded">date, amount, marketplace, category, currency, order_id, sku, description</code>.
        </div>
      </div>
    </div>
  );
}
