import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { MP_BY_CODE, formatMoney } from "@/constants/marketplaces";
import KpiCard from "@/components/KpiCard";
import { FinanceCurrency } from "@/components/FinanceCurrency";
import { MissingFxAlert, NativeBalances, formatUsd } from "@/components/FxStatus";
import { Button } from "@/components/ui/button";
import {
  TrendingUp, TrendingDown, DollarSign, Percent, Wallet, Receipt,
  Store as StoreIcon,
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
  const [selectedCurrency, setSelectedCurrency] = useState("");
  const [error, setError] = useState("");

  useEffect(() => { setSelectedCurrency(""); }, [activeMarketplace, activeStoreId]);

  useEffect(() => {
    let current = true;
    setSummary(null); setRecent([]); setError("");
    if (!activeStoreId) { setLoading(false); return; }
    (async () => {
      setLoading(true);
      try {
        const params = { store_id: activeStoreId, ...(selectedCurrency ? { currency: selectedCurrency } : {}) };
        if (activeMarketplace !== "ALL") params.marketplace = activeMarketplace;
        const s = await api.get("/dashboard/summary", { params });
        const t = await api.get("/transactions", { params: { ...params, limit: 8 } });
        if (current) { setSummary(s.data); setRecent(t.data); }
      } catch {
        if (current) setError("Özet yüklenemedi. Lütfen tekrar deneyin.");
      } finally {
        if (current) setLoading(false);
      }
    })();
    return () => { current = false; };
  }, [activeStoreId, activeMarketplace, selectedCurrency]);

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
        <Link to="/stores" data-testid="dashboard-create-store-link">
          <Button data-testid="empty-create-store-btn" className="mt-6 bg-slate-900 hover:bg-slate-800 text-white rounded-xl">
            Mağaza Ekle
          </Button>
        </Link>
      </div>
    );
  }

  const kpis = summary || {};
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
        <div className="flex gap-2 flex-wrap">
          <Link to="/transactions" data-testid="dashboard-transactions-link">
            <Button variant="outline" className="rounded-xl bg-white" data-testid="quick-add-income">
              <Receipt className="w-4 h-4 mr-2" /> Gelir / Gider Ekle
            </Button>
          </Link>
          <Link to="/payouts" data-testid="dashboard-payouts-link">
            <Button className="bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl" data-testid="quick-add-payout">
              <Wallet className="w-4 h-4 mr-2" /> Amazon Ödemesi
            </Button>
          </Link>
        </div>
      </div>

      <FinanceCurrency summary={summary} value={selectedCurrency} onChange={setSelectedCurrency} prefix="dashboard" />
      <MissingFxAlert summary={summary} prefix="dashboard" />
      {error && <p role="alert" data-testid="dashboard-error" className="text-sm text-rose-600">{error}</p>}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-5 gap-4">
        <KpiCard testId="kpi-revenue" label="Toplam Satış (USD)" accent="emerald" icon={TrendingUp}
                 value={formatUsd(kpis.revenue)} hint="İşlem tarihindeki kurla" />
        <KpiCard testId="kpi-expenses" label="Toplam Gider (USD)" accent="rose" icon={TrendingDown}
                 value={formatUsd(kpis.expenses)} hint="İadeler, ücretler, net maliyetler" />
        <KpiCard testId="kpi-net-profit" label="Net Kâr (USD)" accent="indigo" icon={DollarSign}
                 value={formatUsd(kpis.net_profit)} hint="Gelir − Gider" />
        <KpiCard testId="kpi-margin" label="Kar Marjı" accent="amber" icon={Percent}
                 value={kpis.margin == null ? "—" : `${kpis.margin.toFixed(1)}%`} hint="Net Kar / Gelir" />
        <KpiCard testId="kpi-amazon-balance" label="Amazon Bakiye" accent="amazon" icon={Wallet}
                 value={<NativeBalances summary={summary} prefix="dashboard-amazon" />} hint="Yerel para birimi · Tahmini" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="min-w-0 lg:col-span-2 bg-white border border-slate-200 rounded-2xl p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display text-lg font-bold text-slate-900">Gelir ve Kâr Trendi (USD)</h2>
            <span className="text-xs text-slate-500 font-mono-num">Aylık</span>
          </div>
          <div className="h-72">
            {loading ? (
              <div className="h-full flex items-center justify-center text-sm text-slate-400">Yükleniyor...</div>
            ) : trendData.length === 0 ? (
              <div className="h-full flex items-center justify-center text-sm text-slate-400">Henüz veri yok</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{ width: 320, height: 288 }}>
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

        <div className="min-w-0 bg-white border border-slate-200 rounded-2xl p-6">
          <h2 className="font-display text-lg font-bold text-slate-900 mb-4">Pazar Yeri Dağılımı</h2>
          <div className="h-72">
            {pieData.length === 0 ? (
              <div className="h-full flex items-center justify-center text-sm text-slate-400">Veri yok</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{ width: 320, height: 288 }}>
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
        <div className="min-w-0 bg-white border border-slate-200 rounded-2xl p-6">
          <h2 className="font-display text-lg font-bold text-slate-900 mb-4">Gider Kategorileri</h2>
          <div className="h-64">
            {catData.length === 0 ? (
              <div className="h-full flex items-center justify-center text-sm text-slate-400">Veri yok</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{ width: 320, height: 256 }}>
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
            <Link to="/transactions" data-testid="dashboard-all-transactions" className="text-xs font-semibold text-emerald-600 hover:underline">
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

    </div>
  );
}
