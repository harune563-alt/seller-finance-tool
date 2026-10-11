import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Info, Store as StoreIcon } from "lucide-react";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { FbaFilters } from "@/components/fba/FbaFilters";
import { SelectField, TextField, apiError } from "@/components/company/Fields";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { PpcOverview } from "@/components/ppc/PpcOverview";
import { PpcRecords } from "@/components/ppc/PpcRecords";
import { PpcBreakdown } from "@/components/ppc/PpcBreakdown";
import { PpcReconciliation } from "@/components/ppc/PpcReconciliation";
import { PpcEntryDialog } from "@/components/ppc/PpcEntryDialog";
import { PpcImportDialog } from "@/components/ppc/PpcImportDialog";
import { FINANCE_NOTE } from "@/components/ppc/ppcFormat";

const usePpcData = (stores, storeScope, filters, revision) => {
  const [state, setState] = useState({ data: null, recon: [], financial: {}, loading: false, error: "" });
  useEffect(() => {
    if (!stores.length) return;
    const base = { ...(storeScope !== "ALL" && { store_id: storeScope }), ...(filters.marketplace !== "ALL" && { marketplace: filters.marketplace }) };
    const range = { ...(filters.start && { start_date: filters.start }), ...(filters.end && { end_date: filters.end }) };
    const extra = { ...(filters.asin && { asin: filters.asin }), ...(filters.campaign && { campaign: filters.campaign }) };
    setState(s => ({ ...s, loading: true, error: "" }));
    Promise.all([
      api.get("/ppc/attributions", { params: { ...base, ...range, ...extra } }),
      api.get("/ppc/reconciliation", { params: base }),
      api.get("/ppc/financial-expenses", { params: { ...base, ...range } }),
    ]).then(([a, r, f]) => setState({ data: a.data, recon: r.data.rows || [], financial: f.data, loading: false, error: "" }))
      .catch(() => setState(s => ({ ...s, loading: false, error: "PPC verileri yüklenemedi." })));
  }, [stores.length, storeScope, filters, revision]);
  return state;
};

export default function Ppc() {
  const { stores, activeStoreId } = useStore();
  const [filters, setFilters] = useState({ preset: "all", start: "", end: "", marketplace: "ALL", asin: "", campaign: "" });
  const [storeScope, setStoreScope] = useState(activeStoreId || "ALL");
  const [revision, setRevision] = useState(0);
  const [dialog, setDialog] = useState(null);
  const { data, recon, financial, loading, error } = usePpcData(stores, storeScope, filters, revision);
  const refresh = () => setRevision(v => v + 1);
  const marketplaces = useMemo(() => [...new Set(stores.filter(s => storeScope === "ALL" || s.id === storeScope).flatMap(s => s.marketplaces))], [stores, storeScope]);
  const storeId = storeScope === "ALL" ? null : storeScope;
  const open = (kind) => storeId ? setDialog(kind) : toast.error("Önce tek bir mağaza seçin");

  const remove = async (row) => {
    if (!window.confirm("Bu PPC dağıtım kaydı silinecek. Emin misin?")) return;
    try { await api.delete(`/ppc/attributions/${row.id}`); toast.success("PPC kaydı silindi"); refresh(); }
    catch (err) { toast.error(apiError(err)); }
  };

  if (!stores.length) {
    return (
      <div className="rounded-2xl bg-white border border-slate-200 p-12 text-center" data-testid="ppc-empty">
        <div className="mx-auto w-14 h-14 rounded-2xl bg-pink-50 flex items-center justify-center text-pink-600 mb-4"><StoreIcon className="w-7 h-7" /></div>
        <h2 className="font-display text-2xl font-extrabold text-slate-900">Önce mağaza oluştur</h2>
        <Link to="/stores"><Button className="mt-6 bg-slate-900 hover:bg-slate-800 text-white rounded-xl">Mağaza Ekle</Button></Link>
      </div>
    );
  }
  const rows = data?.rows || [];
  return (
    <div className="space-y-6" data-testid="ppc-page">
      <div>
        <h1 className="font-display text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight">PPC Reklam</h1>
        <p className="text-sm text-slate-500 mt-1">Finansal reklam gideri ve PPC attribution tek ekranda{loading && " · Yükleniyor…"}</p>
      </div>
      <div className="flex gap-3 items-start rounded-xl border border-indigo-100 bg-indigo-50/60 p-4 text-sm text-indigo-900" data-testid="ppc-finance-note">
        <Info className="w-5 h-5 shrink-0 mt-0.5" /><p>{FINANCE_NOTE}</p>
      </div>
      <FbaFilters value={filters} onChange={setFilters} marketplaces={marketplaces} allTime>
        <div className="w-52">
          <SelectField label="Mağaza / Şirket" id="ppc-store-filter" value={storeScope} onChange={setStoreScope}
            options={[{ value: "ALL", label: "Tüm Mağazalar" }, ...stores.map(x => ({ value: x.id, label: x.name }))]} />
        </div>
        <div className="w-40"><TextField label="ASIN" id="ppc-asin-filter" value={filters.asin} onChange={v => setFilters({ ...filters, asin: v })} placeholder="B0..." /></div>
        <div className="w-44"><TextField label="Kampanya" id="ppc-campaign-filter" value={filters.campaign} onChange={v => setFilters({ ...filters, campaign: v })} /></div>
      </FbaFilters>
      {error && <p role="alert" data-testid="ppc-error" className="text-sm text-rose-600">{error}</p>}
      <Tabs defaultValue="overview" className="space-y-4">
        <TabsList className="bg-white border border-slate-200 flex-wrap h-auto" data-testid="ppc-tabs">
          <TabsTrigger value="overview" data-testid="ppc-tab-overview">PPC Genel Bakış</TabsTrigger>
          <TabsTrigger value="records" data-testid="ppc-tab-records">PPC Kayıtları</TabsTrigger>
          <TabsTrigger value="breakdown" data-testid="ppc-tab-breakdown">ASIN / Kampanya Dağılımı</TabsTrigger>
          <TabsTrigger value="recon" data-testid="ppc-tab-recon">Amazon Payments Mutabakatı</TabsTrigger>
        </TabsList>
        <TabsContent value="overview"><PpcOverview summary={data?.summary} /></TabsContent>
        <TabsContent value="records"><PpcRecords rows={rows} onAdd={() => open("entry")} onImport={() => open("import")} onDelete={remove} /></TabsContent>
        <TabsContent value="breakdown"><PpcBreakdown rows={rows} /></TabsContent>
        <TabsContent value="recon"><PpcReconciliation recon={recon} financial={financial} /></TabsContent>
      </Tabs>
      <PpcEntryDialog open={dialog === "entry"} onOpenChange={v => !v && setDialog(null)} storeId={storeId} marketplaces={marketplaces} onSaved={refresh} />
      <PpcImportDialog open={dialog === "import"} onOpenChange={v => !v && setDialog(null)} storeId={storeId} marketplaces={marketplaces} onSaved={refresh} />
    </div>
  );
}
