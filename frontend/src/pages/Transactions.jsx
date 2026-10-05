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
import { CostDialog } from "@/components/transactions/CostDialog";
import { CsvImport } from "@/components/transactions/CsvImport";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";

export default function Transactions() {
  const { activeStore, activeStoreId, activeMarketplace } = useStore();
  const [rows, setRows] = useState([]);
  const [summary, setSummary] = useState(null);
  const [currency, setCurrency] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [filter, setFilter] = useState("all");
  const [revision, setRevision] = useState(0);
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);
  const [deletingBusy, setDeletingBusy] = useState(false);
  const refresh = () => setRevision(v => v + 1);
  useEffect(() => { setCurrency(""); setEditing(null); setDeleting(null); }, [activeStoreId, activeMarketplace]);
  useEffect(() => {
    let current = true;
    setRows([]); setSummary(null); setError("");
    if (!activeStoreId) return;
    setLoading(true);
    const params = { store_id: activeStoreId, marketplace: activeMarketplace, ...(currency ? { currency } : {}) };
    (async () => {
      try {
        const { data: totals } = await api.get("/dashboard/summary", { params });
        const { data } = await api.get("/transactions", { params: { ...params, limit: 10000 } });
        if (current) { setSummary(totals); setRows(data.filter(t => t.type !== "payout")); }
      } catch { if (current) setError("Kayıtlar yüklenemedi. Yeniden deneyin."); }
      finally { if (current) setLoading(false); }
    })();
    return () => { current = false; };
  }, [activeStoreId, activeMarketplace, currency, revision]);
  const remove = async () => {
    setDeletingBusy(true);
    try { await api.delete(`/transactions/${deleting.id}`); setDeleting(null); toast.success("İşlem silindi"); refresh(); }
    catch { toast.error("İşlem silinemedi"); }
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
      <Tabs value={filter} onValueChange={setFilter}><TabsList data-testid="tx-record-filters"><TabsTrigger value="all" data-testid="tab-all">Tüm İşlemler</TabsTrigger><TabsTrigger value="profit" data-testid="tab-profit">Kârlı</TabsTrigger><TabsTrigger value="loss" data-testid="tab-loss">Zararlı</TabsTrigger></TabsList></Tabs>
      <TransactionList rows={rows} filter={filter} loading={loading} onEdit={setEditing} onDelete={setDeleting} />
    </>}
    {editing && <CostDialog key={editing.id} row={editing} onClose={() => setEditing(null)} onSaved={refresh} />}
    <Dialog open={!!deleting} onOpenChange={open => { if (!open && !deletingBusy) setDeleting(null); }}><DialogContent data-testid="delete-transaction-dialog" className="bg-white"><DialogHeader><DialogTitle>İşlem silinsin mi?</DialogTitle><DialogDescription>Bu kayıt ve bağlı maliyetleri toplamlarınızdan kaldırılacak.</DialogDescription></DialogHeader><DialogFooter><Button variant="outline" disabled={deletingBusy} onClick={() => setDeleting(null)} data-testid="cancel-delete-transaction">Vazgeç</Button><Button variant="destructive" disabled={deletingBusy} onClick={remove} data-testid="confirm-delete-transaction">{deletingBusy ? "Siliniyor…" : "Sil"}</Button></DialogFooter></DialogContent></Dialog>
  </div>;
}