import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { FinanceSummary } from "@/components/FinanceSummary";
import { FinanceCurrency } from "@/components/FinanceCurrency";
import { MissingFxAlert, NativeBalances } from "@/components/FxStatus";
import { TransactionForm } from "@/components/transactions/TransactionForm";
import { TransactionList } from "@/components/transactions/TransactionList";
import { TransactionEditDialog } from "@/components/transactions/TransactionEditDialog";
import { CsvImport } from "@/components/transactions/CsvImport";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { useRecordSearch } from "@/hooks/useRecordSearch";
import { RecordFilters, RecordPagination } from "@/components/RecordFilters";
import { TRANSACTION_CATEGORIES } from "@/constants/marketplaces";

export default function Transactions() {
  const { activeStore, activeStoreId, activeMarketplace } = useStore();
  const [summary, setSummary] = useState(null);
  const [currency, setCurrency] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const [revision, setRevision] = useState(0);
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState([]);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [deletingBusy, setDeletingBusy] = useState(false);
  const history = useRecordSearch({ storeId: activeStoreId, marketplace: activeMarketplace, currency, view: "orders", revision, outcome: filter });
  const refresh = () => setRevision(v => v + 1);
  const toggleSelected = id => setSelectedIds(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  const toggleGroup = ids => setSelectedIds(current => { const next = new Set(current); const shouldSelect = ids.some(id => !next.has(id)); ids.forEach(id => shouldSelect ? next.add(id) : next.delete(id)); return next; });
  const toggleAll = () => setSelectedIds(current => { const ids = history.items.map(row => row.id); const allSelected = ids.length > 0 && ids.every(id => current.has(id)); return allSelected ? new Set([...current].filter(id => !ids.includes(id))) : new Set([...current, ...ids]); });
  useEffect(() => { setCurrency(""); setEditing(null); setDeleting([]); setSelectedIds(new Set()); }, [activeStoreId, activeMarketplace]);
  useEffect(() => {
    let current = true;
    setSummary(null); setError("");
    if (!activeStoreId) return;
    setLoading(true);
    const params = { store_id: activeStoreId, marketplace: activeMarketplace, ...(currency ? { currency } : {}) };
    (async () => {
      try {
        const { data: totals } = await api.get("/dashboard/summary", { params });
        if (current) setSummary(totals);
      } catch { if (current) setError("Kayıtlar yüklenemedi. Yeniden deneyin."); }
      finally { if (current) setLoading(false); }
    })();
    return () => { current = false; };
  }, [activeStoreId, activeMarketplace, currency, revision]);
  const remove = async () => {
    if (!deleting.length) return;
    setDeletingBusy(true);
    try {
      if (deleting.length === 1) await api.delete(`/transactions/${deleting[0]}`);
      else await api.post("/transactions/bulk-delete", { ids: deleting });
      setDeleting([]); setSelectedIds(current => new Set([...current].filter(id => !deleting.includes(id))));
      toast.success(`${deleting.length} işlem silindi`); refresh();
    } catch { toast.error("İşlem(ler) silinemedi"); }
    finally { setDeletingBusy(false); }
  };
  return <div className="space-y-6" data-testid="transactions-page">
    <div className="flex items-end justify-between flex-wrap gap-4"><div><h1 className="font-display text-3xl sm:text-4xl font-extrabold" data-testid="transactions-title">Gelir / Gider</h1><p className="mt-2 text-sm text-slate-500" data-testid="transactions-store-name">{activeStore?.name || "Mağaza seçilmedi"}</p></div><CsvImport key={`${activeStoreId}-${activeMarketplace}`} onSaved={refresh} /></div>
    {!activeStoreId ? <Link to="/stores" data-testid="tx-create-store" className="text-emerald-700 underline">Mağaza oluştur</Link> : <>
      <FinanceCurrency summary={summary} value={currency} onChange={setCurrency} prefix="tx" />
      <FinanceSummary summary={summary} currency={summary?.currency} loading={loading} />
      <MissingFxAlert summary={summary} prefix="tx" />
      <div className="border-y border-slate-200 py-3 flex flex-wrap items-center justify-between gap-3" data-testid="tx-amazon-balances"><span className="text-sm text-slate-500">Amazon Bakiyesi · Yerel para birimi · Tahmini</span><NativeBalances summary={summary} prefix="tx-amazon" /></div>
      {error && <div role="alert" data-testid="tx-load-error" className="text-rose-700 text-sm">{error}<Button variant="ghost" onClick={refresh} data-testid="tx-retry">Tekrar dene</Button></div>}
      <TransactionForm onSaved={refresh} />
      <RecordFilters history={history} prefix="tx" searchLabel="Order ID ile ara" categoryLabel="İşlem Türü" options={TRANSACTION_CATEGORIES} unit="sipariş / kayıt" />
      {selectedIds.size > 0 && <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3" data-testid="tx-selection-toolbar"><span className="text-sm font-medium text-rose-800">{selectedIds.size} işlem seçildi</span><Button variant="destructive" onClick={() => setDeleting([...selectedIds])} data-testid="bulk-delete-tx"><span aria-hidden="true">×</span> Seçilenleri Sil</Button></div>}
      <Tabs value={filter} onValueChange={setFilter}><TabsList data-testid="tx-record-filters"><TabsTrigger value="all" data-testid="tab-all">Tüm İşlemler</TabsTrigger><TabsTrigger value="profit" data-testid="tab-profit">Kârlı</TabsTrigger><TabsTrigger value="loss" data-testid="tab-loss">Zararlı</TabsTrigger></TabsList></Tabs>
      <TransactionList rows={history.items} total={history.total} filter="all" loading={history.loading} onEdit={setEditing} onDelete={row => setDeleting([row.id])} selectedIds={selectedIds} onToggle={toggleSelected} onToggleGroup={toggleGroup} onToggleAll={toggleAll} />
      <RecordPagination history={history} prefix="tx" />
    </>}
    {editing && <TransactionEditDialog key={editing.id} row={editing} onClose={() => setEditing(null)} onSaved={refresh} />}
    <Dialog open={deleting.length > 0} onOpenChange={open => { if (!open && !deletingBusy) setDeleting([]); }}><DialogContent data-testid="delete-transaction-dialog" className="bg-white"><DialogHeader><DialogTitle>{deleting.length} işlem silinsin mi?</DialogTitle><DialogDescription>Seçilen kayıtlar ve bağlı maliyetleri toplamlarınızdan kalıcı olarak kaldırılacak.</DialogDescription></DialogHeader><DialogFooter><Button variant="outline" disabled={deletingBusy} onClick={() => setDeleting([])} data-testid="cancel-delete-transaction">Vazgeç</Button><Button variant="destructive" disabled={deletingBusy} onClick={remove} data-testid="confirm-delete-transaction">{deletingBusy ? "Siliniyor…" : "Sil"}</Button></DialogFooter></DialogContent></Dialog>
  </div>;
}