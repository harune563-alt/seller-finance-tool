import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import KpiCard from "@/components/KpiCard";
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
    return () => { current = false; };
  }, [stores.length, storeScope, filters, currency]);

  if (!stores.length) return <EmptyStores />;
  const k = summary || {};
  const trend = summary?.trend || [];
  const scopeName = storeScope === "ALL" ? "Tüm Mağazalar" : stores.find(s => s.id === storeScope)?.name;

  return (
    <div className="space-y-6" data-testid="dashboard-page">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-extrabold text-slate-900 tracking-tight">Ana Dashboard</h1>
          <p className="text-sm text-slate-500 mt-1" data-testid="dashboard-scope-label">{scopeName} · {filters.marketplace === "ALL" ? "Tüm Pazarlar" : filters.marketplace}{loading && " · Yükleniyor…"}</p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Link to="/transactions" data-testid="dashboard-transactions-link"><Button variant="outline" className="rounded-xl bg-white" data-testid="quick-add-income"><Receipt className="w-4 h-4 mr-2" /> Gelir / Gider Ekle</Button></Link>
          <Link to="/payouts" data-testid="dashboard-payouts-link"><Button className="bg-emerald-600 hover:bg-emerald-700 text-white rounded-xl" data-testid="quick-add-payout"><Wallet className="w-4 h-4 mr-2" /> Amazon Ödemesi</Button></Link>
        </div>
      </div>

      <FbaFilters value={filters} onChange={setFilters} marketplaces={marketplaces} allTime>
        <div className="w-56"><SelectField label="Mağaza / Şirket" id="dashboard-store-filter" value={storeScope} onChange={setStoreScope}
          options={[{ value: "ALL", label: "Tüm Mağazalar" }, ...stores.map(s => ({ value: s.id, label: s.name }))]} /></div>
      </FbaFilters>
      <div className="flex flex-wrap items-center gap-3">
        <FinanceCurrency summary={summary} value={currency} onChange={setCurrency} prefix="dashboard" />
      </div>
      <MissingFxAlert summary={summary} prefix="dashboard" />
      {error && <p role="alert" data-testid="dashboard-error" className="text-sm text-rose-600">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4" data-testid="dashboard-primary-kpis">
        <KpiCard testId="kpi-revenue" label="Toplam Gelir (USD)" accent="emerald" icon={TrendingUp} value={formatUsd(k.revenue)} hint="İşlem tarihindeki kurla" />
        <KpiCard testId="kpi-expenses" label="Toplam Gider (USD)" accent="rose" icon={TrendingDown} value={formatUsd(k.expenses)} hint="İadeler, ücretler, gerçekleşen maliyetler (FBA FIFO dahil)" />
        <KpiCard testId="kpi-net-profit" label="Net Kâr (USD)" accent="indigo" icon={DollarSign} value={formatUsd(k.net_profit)} hint="Gelir − Gider" />
        <KpiCard testId="kpi-margin" label="Kâr Marjı" accent="amber" icon={Percent} value={pct(k.margin)} hint="Net Kâr / Gelir" />
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4" data-testid="dashboard-secondary-kpis">
        <KpiCard testId="kpi-fba-profit" label="FBA Kâr" accent="indigo" icon={Package} value={formatUsd(insights?.fba?.net_profit)} hint={`Gelir ${formatUsd(insights?.fba?.revenue)}`} />
        <KpiCard testId="kpi-fbm-profit" label="FBM Kâr" accent="slate" icon={Truck} value={formatUsd(insights?.fbm?.net_profit)} hint={`Gelir ${formatUsd(insights?.fbm?.revenue)}`} />
        <KpiCard testId="kpi-fba-inventory" label="FBA Stok Değeri" accent="amber" icon={Boxes} value={formatUsd(insights?.fba_inventory_value_usd)} hint="Varlık — gider değildir" />
        <KpiCard testId="kpi-orders" label="Toplam Sipariş" accent="emerald" icon={ShoppingCart} value={insights?.order_count ?? "—"} hint="Order ID'li siparişler" />
        <KpiCard testId="kpi-amazon-balance" label="Amazon Bakiye" accent="amazon" icon={Wallet} value={<NativeBalances summary={summary} prefix="dashboard-amazon" />} hint="Yerel para birimi · Tahmini" />
      </div>

      {cashflow && (
        <div className="rounded-2xl border border-dashed border-slate-300 bg-slate-50/60 p-4 space-y-3" data-testid="dashboard-cashflow-section">
          <div className="flex flex-wrap items-baseline gap-2">
            <h2 className="font-display text-lg font-bold text-slate-900">Nakit Akışı (Cash Flow)</h2>
            <span className="text-xs text-slate-500">Gelir/Gider/Net Kâr kartlarından ayrıdır — gerçek nakit hareketini gösterir</span>
            <Link to="/cashflow" className="text-xs font-semibold text-indigo-600 hover:text-indigo-800 ml-auto" data-testid="dashboard-cashflow-link">Nakit Akışı sayfası →</Link>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4" data-testid="dashboard-cashflow-cards">
            <KpiCard testId="cf-period-in" label="Dönem Nakit Girişi" accent="emerald" icon={TrendingUp} value={formatUsd(cashflow.cash_in)} hint="Amazon tahsilatı + manuel girişler" />
            <KpiCard testId="cf-period-out" label="Dönem Nakit Çıkışı" accent="rose" icon={TrendingDown} value={formatUsd(cashflow.cash_out)} hint="Envanter, FBM, ekstra, manuel çıkışlar" />
            <KpiCard testId="cf-net" label="Net Nakit Akışı" accent="indigo" icon={DollarSign} value={formatUsd(cashflow.net_cash_flow)} hint="Nakit Giriş − Nakit Çıkış" />
            <KpiCard testId="cf-capital-tied" label="Envanterdeki Sermaye" accent="amazon" icon={Boxes} value={formatUsd(cashflow.capital_tied_in_inventory)} hint="Kalan FBA stok değeri — varlık, gider değil" />
          </div>
        </div>
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
