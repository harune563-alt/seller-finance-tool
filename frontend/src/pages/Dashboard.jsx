import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { HeroMetric, StatCard, delta, previousRange } from "@/components/dashboard/DashboardHero";
import { FinanceCurrency } from "@/components/FinanceCurrency";
import { MissingFxAlert, NativeBalances, formatUsd } from "@/components/FxStatus";
import { PortfolioPanel } from "@/components/reports/PortfolioPanel";
import { SelectField } from "@/components/company/Fields";
import { FbaFilters } from "@/components/fba/FbaFilters";
import { RevenueExpenseChart, NetProfitChart, ChannelChart } from "@/components/dashboard/DashboardCharts";
import { DashboardInsights } from "@/components/dashboard/DashboardInsights";
import { Button } from "@/components/ui/button";
import { TrendingUp, TrendingDown, DollarSign, Percent, Wallet, Receipt, Package, Truck, Boxes, ShoppingCart, Store as StoreIcon } from "lucide-react";

const pct = v => v == null ? "—" : `${Number(v).toFixed(1)}%`;

const EmptyStores = () => (
  <div className="rounded-2xl bg-white border border-slate-200 p-12 text-center">
    <div className="mx-auto w-14 h-14 rounded-2xl bg-emerald-50 flex items-center justify-center text-emerald-600 mb-4"><StoreIcon className="w-7 h-7" /></div>
    <h2 className="font-display text-2xl font-extrabold text-slate-900">İlk mağazanı oluştur</h2>
    <p className="text-sm text-slate-500 mt-2 max-w-md mx-auto">Takibe başlamak için bir Amazon satıcı mağazası ekle ve içine satış yaptığın pazar yerlerini seç.</p>
    <Link to="/stores" data-testid="dashboard-create-store-link"><Button data-testid="empty-create-store-btn" className="mt-6 bg-slate-900 hover:bg-slate-800 text-white rounded-xl">Mağaza Ekle</Button></Link>
  </div>
);

export default function Dashboard() {
  const { stores } = useStore();
  const [filters, setFilters] = useState({ preset: "all", start: "", end: "", marketplace: "ALL" });
  const [storeScope, setStoreScope] = useState("ALL");
  const [currency, setCurrency] = useState("");
  const [summary, setSummary] = useState(null);
  const [insights, setInsights] = useState(null);
  const [cashflow, setCashflow] = useState(null);
  const [prev, setPrev] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const marketplaces = useMemo(() => [...new Set(stores.filter(s => storeScope === "ALL" || s.id === storeScope).flatMap(s => s.marketplaces))], [stores, storeScope]);
  useEffect(() => { setCurrency(""); if (filters.marketplace !== "ALL" && !marketplaces.includes(filters.marketplace)) setFilters(f => ({ ...f, marketplace: "ALL" })); }, [storeScope]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!stores.length) return;
    let current = true;
    const params = {
      ...(storeScope !== "ALL" && { store_id: storeScope }), ...(filters.marketplace !== "ALL" && { marketplace: filters.marketplace }),
      ...(filters.start && { start_date: filters.start }), ...(filters.end && { end_date: filters.end }),
    };
    setLoading(true); setError("");
    Promise.all([api.get("/dashboard/summary", { params: { ...params, ...(currency && { currency }) } }), api.get("/dashboard/insights", { params })])
      .then(([s, i]) => { if (current) { setSummary(s.data); setInsights(i.data); } })
      .catch(() => { if (current) setError("Özet yüklenemedi. Lütfen tekrar deneyin."); })
      .finally(() => { if (current) setLoading(false); });
    // Nakit Akışı kartları ayrı tutulur; mevcut kâr/zarar özetine karışmaz.
    api.get("/cashflow/summary", { params })
      .then(r => { if (current) setCashflow(r.data); })
      .catch(() => { if (current) setCashflow(null); });
    // Önceki eşit uzunluktaki dönem — yalnızca değişim rozetleri için (görsel karşılaştırma).
    const prevRange = previousRange(filters.start, filters.end);
    setPrev(null);
    if (prevRange) {
      const prevParams = { ...params, start_date: prevRange[0], end_date: prevRange[1] };
      Promise.all([
        api.get("/dashboard/summary", { params: { ...prevParams, ...(currency && { currency }) } }),
        api.get("/dashboard/insights", { params: prevParams }),
        api.get("/cashflow/summary", { params: prevParams }).catch(() => ({ data: null })),
      ]).then(([s, i, c]) => { if (current) setPrev({ summary: s.data, insights: i.data, cashflow: c.data, range: prevRange }); })
        .catch(() => { if (current) setPrev(null); });
    }
    return () => { current = false; };
  }, [stores.length, storeScope, filters, currency]);

  if (!stores.length) return <EmptyStores />;
  const k = summary || {};
  const trend = summary?.trend || [];
  const scopeName = storeScope === "ALL" ? "Tüm Mağazalar" : stores.find(s => s.id === storeScope)?.name;
  const p = prev?.summary, pi = prev?.insights, pc = prev?.cashflow;
  const fx = (cur, old, kind) => (prev ? delta(cur, old, kind) : null);

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      {/* Üst özet bandı */}
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-emerald-950 via-slate-900 to-slate-950 text-white p-6 sm:p-8 shadow-[0_24px_48px_-24px_rgba(2,44,34,0.6)]" data-testid="dashboard-hero">
        <div aria-hidden className="pointer-events-none absolute -top-24 -right-16 w-80 h-80 rounded-full bg-emerald-500/20 blur-3xl" />
        <div aria-hidden className="pointer-events-none absolute -bottom-32 left-1/3 w-96 h-96 rounded-full bg-indigo-500/10 blur-3xl" />
        <div className="relative flex flex-wrap items-end justify-between gap-4">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-emerald-300/80">Genel Bakış</p>
            <h1 className="font-display text-3xl sm:text-4xl font-extrabold tracking-tight mt-1">Ana Dashboard</h1>
            <p className="text-sm text-emerald-100/70 mt-2" data-testid="dashboard-scope-label">{scopeName} · {filters.marketplace === "ALL" ? "Tüm Pazarlar" : filters.marketplace}{loading && " · Yükleniyor…"}</p>
          </div>
          <div className="flex gap-2 flex-wrap">
            <Link to="/transactions" data-testid="dashboard-transactions-link"><Button variant="outline" className="rounded-xl bg-white/5 border-white/20 text-white hover:bg-white/15 hover:text-white" data-testid="quick-add-income"><Receipt className="w-4 h-4 mr-2" /> Gelir / Gider Ekle</Button></Link>
            <Link to="/payouts" data-testid="dashboard-payouts-link"><Button className="bg-emerald-500 hover:bg-emerald-400 text-emerald-950 font-semibold rounded-xl" data-testid="quick-add-payout"><Wallet className="w-4 h-4 mr-2" /> Amazon Ödemesi</Button></Link>
          </div>
        </div>
        <div className="relative mt-7 grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 sm:gap-4" data-testid="dashboard-primary-kpis">
          <HeroMetric testId="kpi-revenue" label="Toplam Gelir" icon={TrendingUp} value={formatUsd(k.revenue)} d={fx(k.revenue, p?.revenue)} hint="USD · işlem tarihi kuru" />
          <HeroMetric testId="kpi-expenses" label="Toplam Gider" icon={TrendingDown} value={formatUsd(k.expenses)} d={fx(k.expenses, p?.expenses)} inverse hint="FBA FIFO dahil" />
          <HeroMetric testId="kpi-net-profit" label="Net Kâr" icon={DollarSign} value={formatUsd(k.net_profit)} d={fx(k.net_profit, p?.net_profit)} tone={k.net_profit < 0 ? "text-rose-300" : "text-white"} hint="Gelir − Gider" />
          <HeroMetric testId="kpi-margin" label="Kâr Marjı" icon={Percent} value={pct(k.margin)} d={p?.revenue ? fx(k.margin, p?.margin, "pp") : null} tone={k.margin < 0 ? "text-rose-300" : "text-white"} hint="Net Kâr / Gelir" />
        </div>
        <p className="relative mt-4 text-[11px] text-emerald-100/50" data-testid="dashboard-compare-note">
          {prev ? `Rozetler önceki döneme göre değişimi gösterir (${prev.range[0]} → ${prev.range[1]}).` : "Önceki döneme göre değişim için bir tarih aralığı seçin."}
        </p>
      </section>

      <FbaFilters value={filters} onChange={setFilters} marketplaces={marketplaces} allTime>
        <div className="w-56"><SelectField label="Mağaza / Şirket" id="dashboard-store-filter" value={storeScope} onChange={setStoreScope}
          options={[{ value: "ALL", label: "Tüm Mağazalar" }, ...stores.map(s => ({ value: s.id, label: s.name }))]} /></div>
      </FbaFilters>
      <div className="flex flex-wrap items-center gap-3">
        <FinanceCurrency summary={summary} value={currency} onChange={setCurrency} prefix="dashboard" />
      </div>
      <MissingFxAlert summary={summary} prefix="dashboard" />
      {error && <p role="alert" data-testid="dashboard-error" className="text-sm text-rose-600">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-4" data-testid="dashboard-secondary-kpis">
        <StatCard testId="kpi-fba-profit" label="FBA Kâr" accent="indigo" icon={Package} value={formatUsd(insights?.fba?.net_profit)} d={fx(insights?.fba?.net_profit, pi?.fba?.net_profit)} hint={`Gelir ${formatUsd(insights?.fba?.revenue)}`} />
        <StatCard testId="kpi-fbm-profit" label="FBM Kâr" accent="slate" icon={Truck} value={formatUsd(insights?.fbm?.net_profit)} d={fx(insights?.fbm?.net_profit, pi?.fbm?.net_profit)} hint={`Gelir ${formatUsd(insights?.fbm?.revenue)}`} />
        <StatCard testId="kpi-fba-inventory" label="FBA Stok Değeri" accent="amber" icon={Boxes} value={formatUsd(insights?.fba_inventory_value_usd)} hint="Varlık — gider değildir" />
        <StatCard testId="kpi-orders" label="Toplam Sipariş" accent="emerald" icon={ShoppingCart} value={insights?.order_count ?? "—"} d={fx(insights?.order_count, pi?.order_count)} hint="Order ID'li siparişler" />
        <StatCard testId="kpi-amazon-balance" label="Amazon Bakiye" accent="amazon" icon={Wallet} value={<NativeBalances summary={summary} prefix="dashboard-amazon" />} hint="Yerel para birimi · Tahmini" />
      </div>

      {cashflow && (
        <section className="rounded-2xl bg-gradient-to-br from-slate-50 to-white ring-1 ring-slate-200/70 p-5 space-y-4" data-testid="dashboard-cashflow-section">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="w-1.5 h-6 rounded-full bg-gradient-to-b from-emerald-500 to-indigo-500" aria-hidden />
            <h2 className="font-display text-lg font-bold text-slate-900">Nakit Akışı</h2>
            <span className="text-xs text-slate-500">Gerçek nakit hareketi · kâr/zarardan ayrıdır</span>
            <Link to="/cashflow" className="text-xs font-semibold text-emerald-700 hover:text-emerald-900 ml-auto" data-testid="dashboard-cashflow-link">Nakit Akışı sayfası →</Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4" data-testid="dashboard-cashflow-cards">
            <StatCard testId="cf-period-in" label="Dönem Nakit Girişi" accent="emerald" icon={TrendingUp} value={formatUsd(cashflow.cash_in)} d={fx(cashflow.cash_in, pc?.cash_in)} hint="Amazon, Sermaye & Kasa, manuel" />
            <StatCard testId="cf-period-out" label="Dönem Nakit Çıkışı" accent="rose" icon={TrendingDown} value={formatUsd(cashflow.cash_out)} d={fx(cashflow.cash_out, pc?.cash_out)} inverse hint="Envanter, FBM, ekstra, kasa çıkışları" />
            <StatCard testId="cf-net" label="Net Nakit Akışı" accent="indigo" icon={DollarSign} value={formatUsd(cashflow.net_cash_flow)} d={fx(cashflow.net_cash_flow, pc?.net_cash_flow)} hint="Giriş − Çıkış" />
            <StatCard testId="cf-capital-tied" label="Envanterdeki Sermaye" accent="amazon" icon={Boxes} value={formatUsd(cashflow.capital_tied_in_inventory)} hint="Kalan FBA stok değeri" />
          </div>
        </section>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <RevenueExpenseChart trend={trend} />
        <NetProfitChart trend={trend} />
        <ChannelChart insights={insights} />
      </div>
      <DashboardInsights insights={insights} />
      {storeScope === "ALL" && <PortfolioPanel />}
    </div>
  );
}
