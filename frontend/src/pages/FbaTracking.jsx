import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FbaFilters, fbaRange } from "@/components/fba/FbaFilters";
import { FbaOverview } from "@/components/fba/FbaOverview";
import { FbaOrdersTable } from "@/components/fba/FbaOrdersTable";
import { FbaLotsPanel } from "@/components/fba/FbaLotsPanel";
import { AsinReport, InventoryReport } from "@/components/fba/FbaReports";
import SectionLedger from "@/pages/SectionLedger";

const TABS = [["overview", "FBA Genel Bakış"], ["orders", "FBA Siparişleri"], ["lots", "FBA Stok Lotları"], ["asin", "ASIN Kâr Raporu"], ["inventory", "Stok Değeri Raporu"], ["manual", "Manuel FBA Kayıtları"]];

export default function FbaTracking() {
  const { activeStore, activeStoreId } = useStore();
  const [filters, setFilters] = useState(() => { const [start, end] = fbaRange("month"); return { preset: "month", start, end, marketplace: "ALL" }; });
  const [report, setReport] = useState(null);
  const [lots, setLots] = useState([]);
  const [inventory, setInventory] = useState(null);
  const [loading, setLoading] = useState(false);

  const load = useCallback(async () => {
    if (!activeStoreId) return;
    setLoading(true);
    try {
      const params = { store_id: activeStoreId, start_date: filters.start, end_date: filters.end, marketplace: filters.marketplace };
      const [o, l, i] = await Promise.all([
        api.get("/fba/orders", { params }), api.get("/fba/lots", { params: { store_id: activeStoreId } }), api.get("/fba/inventory", { params: { store_id: activeStoreId } }),
      ]);
      setReport(o.data); setLots(l.data); setInventory(i.data);
    } finally { setLoading(false); }
  }, [activeStoreId, filters]);
  useEffect(() => { load(); }, [load]);

  if (!activeStoreId) return <Link to="/stores" className="text-emerald-700 underline">Mağaza oluştur</Link>;
  return (
    <div className="space-y-6" data-testid="fba-page">
      <div>
        <h1 className="font-display text-3xl sm:text-4xl font-extrabold">FBA Takibi</h1>
        <p className="mt-2 text-sm text-slate-500">{activeStore?.name} · FIFO stok maliyeti, FBA kârlılığı ve stok değeri · Gelir kaynağı: mevcut Amazon Payments kayıtları {loading && "· Yükleniyor…"}</p>
      </div>
      <Tabs defaultValue="overview">
        <TabsList className="flex-wrap h-auto" data-testid="fba-tabs">
          {TABS.map(([id, label]) => <TabsTrigger key={id} value={id} data-testid={`fba-tab-${id}`}>{label}</TabsTrigger>)}
        </TabsList>
        <TabsContent value="overview" className="space-y-4 mt-4">
          <FbaFilters value={filters} onChange={setFilters} marketplaces={activeStore?.marketplaces || []} />
          <FbaOverview summary={report?.summary} />
        </TabsContent>
        <TabsContent value="orders" className="space-y-4 mt-4">
          <FbaFilters value={filters} onChange={setFilters} marketplaces={activeStore?.marketplaces || []} />
          <FbaOrdersTable orders={report?.orders || []} />
        </TabsContent>
        <TabsContent value="lots" className="mt-4">
          <FbaLotsPanel lots={lots} storeId={activeStoreId} marketplaces={activeStore?.marketplaces || []} onChanged={load} />
        </TabsContent>
        <TabsContent value="asin" className="space-y-4 mt-4">
          <FbaFilters value={filters} onChange={setFilters} marketplaces={activeStore?.marketplaces || []} />
          <AsinReport rows={report?.asin_report || []} summary={report?.summary} />
        </TabsContent>
        <TabsContent value="inventory" className="mt-4">
          <InventoryReport data={inventory} />
        </TabsContent>
        <TabsContent value="manual" className="mt-4">
          <SectionLedger section="fba" title="Manuel FBA Kayıtları" subtitle="FBA gelir ve giderleri (önceki kayıt ekranı)" />
        </TabsContent>
      </Tabs>
    </div>
  );
}
