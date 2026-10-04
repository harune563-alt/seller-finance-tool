import { useEffect, useState, useRef } from "react";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { MP_BY_CODE, INCOME_CATEGORIES, EXPENSE_CATEGORIES, formatMoney } from "@/constants/marketplaces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { Trash2, Upload, Plus } from "lucide-react";
import { toast } from "sonner";

const todayISO = () => new Date().toISOString().slice(0, 10);

export default function Transactions() {
  const { activeStore, activeStoreId, activeMarketplace } = useStore();
  const [type, setType] = useState("income");
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  const [form, setForm] = useState({
    marketplace: "US", category: "", amount: "", currency: "USD",
    date: todayISO(), description: "", order_id: "", sku: "",
  });

  const fileRef = useRef(null);
  const [importOpen, setImportOpen] = useState(false);

  const fetchRows = async () => {
    if (!activeStoreId) return;
    setLoading(true);
    try {
      const params = { store_id: activeStoreId, type };
      if (activeMarketplace !== "ALL") params.marketplace = activeMarketplace;
      const { data } = await api.get("/transactions", { params });
      setRows(data);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchRows(); /* eslint-disable-next-line */ }, [activeStoreId, activeMarketplace, type]);

  useEffect(() => {
    const mp = form.marketplace;
    const info = MP_BY_CODE[mp];
    if (info) setForm((f) => ({ ...f, currency: info.currency }));
  }, [form.marketplace]);

  useEffect(() => {
    if (activeStore?.marketplaces?.length) {
      const first = activeMarketplace !== "ALL" ? activeMarketplace : activeStore.marketplaces[0];
      setForm((f) => ({ ...f, marketplace: first }));
    }
  }, [activeStore, activeMarketplace]);

  const submit = async (e) => {
    e.preventDefault();
    if (!activeStoreId) { toast.error("Önce bir mağaza seç"); return; }
    if (!form.category) { toast.error("Kategori seçin"); return; }
    try {
      await api.post("/transactions", {
        store_id: activeStoreId, type,
        ...form, amount: parseFloat(form.amount),
      });
      toast.success(type === "income" ? "Gelir eklendi" : "Gider eklendi");
      setForm((f) => ({ ...f, amount: "", description: "", order_id: "", sku: "" }));
      fetchRows();
    } catch (err) {
      toast.error("Kayıt başarısız");
    }
  };

  const removeRow = async (id) => {
    await api.delete(`/transactions/${id}`);
    toast.success("İşlem silindi");
    fetchRows();
  };

  const doImport = async () => {
    const f = fileRef.current?.files?.[0];
    if (!f) { toast.error("Dosya seçin"); return; }
    const fd = new FormData();
    fd.append("file", f);
    try {
      const { data } = await api.post("/transactions/import", fd, {
        params: { store_id: activeStoreId, type },
        headers: { "Content-Type": "multipart/form-data" },
      });
      toast.success(`${data.inserted} kayıt içe aktarıldı`);
      setImportOpen(false);
      fetchRows();
    } catch (err) {
      toast.error(err?.response?.data?.detail || "İçe aktarma başarısız");
    }
  };

  const categories = type === "income" ? INCOME_CATEGORIES : EXPENSE_CATEGORIES;
  const storeMps = activeStore?.marketplaces || [];

  return (
    <div className="space-y-6" data-testid="transactions-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="font-display text-3xl font-extrabold text-slate-900">Gelir / Gider Kaydı</h1>
          <p className="text-sm text-slate-500 mt-1">Her pazar yeri için gelir ve giderlerini kaydet veya CSV ile içe aktar.</p>
        </div>

        <Dialog open={importOpen} onOpenChange={setImportOpen}>
          <DialogTrigger asChild>
            <Button variant="outline" className="rounded-xl bg-white" data-testid="open-csv-import">
              <Upload className="w-4 h-4 mr-2" /> CSV İçe Aktar
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-white">
            <DialogHeader>
              <DialogTitle>CSV İçe Aktarma — {type === "income" ? "Gelir" : type === "expense" ? "Gider" : "Ödeme"}</DialogTitle>
            </DialogHeader>
            <div className="space-y-3 text-sm">
              <p className="text-slate-600">
                CSV sütunları: <code className="font-mono-num bg-slate-100 px-1.5 py-0.5 rounded">date, amount, marketplace, category, currency, order_id, sku, description</code>
              </p>
              <Input type="file" accept=".csv" ref={fileRef} data-testid="csv-file-input" />
            </div>
            <DialogFooter>
              <Button onClick={doImport} data-testid="csv-import-submit" className="bg-slate-900 hover:bg-slate-800 text-white">
                İçe Aktar
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <Tabs value={type} onValueChange={setType}>
        <TabsList className="bg-slate-100">
          <TabsTrigger value="income" data-testid="tab-income" className="data-[state=active]:bg-emerald-600 data-[state=active]:text-white">
            Gelir
          </TabsTrigger>
          <TabsTrigger value="expense" data-testid="tab-expense" className="data-[state=active]:bg-rose-600 data-[state=active]:text-white">
            Gider
          </TabsTrigger>
        </TabsList>

        <TabsContent value={type} className="mt-4">
          <form onSubmit={submit} className="bg-white border border-slate-200 rounded-2xl p-6 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div>
              <Label className="text-xs font-semibold uppercase tracking-wider text-slate-600">Tarih</Label>
              <Input type="date" value={form.date} onChange={(e) => setForm({ ...form, date: e.target.value })}
                     required data-testid="tx-date-input" className="mt-1" />
            </div>
            <div>
              <Label className="text-xs font-semibold uppercase tracking-wider text-slate-600">Pazar Yeri</Label>
              <Select value={form.marketplace} onValueChange={(v) => setForm({ ...form, marketplace: v })}>
                <SelectTrigger data-testid="tx-marketplace-select" className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-white">
                  {storeMps.map((c) => {
                    const m = MP_BY_CODE[c];
                    return <SelectItem key={c} value={c}>{m?.flag} {m?.name}</SelectItem>;
                  })}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs font-semibold uppercase tracking-wider text-slate-600">Kategori</Label>
              <Select value={form.category} onValueChange={(v) => setForm({ ...form, category: v })}>
                <SelectTrigger data-testid="tx-category-select" className="mt-1">
                  <SelectValue placeholder="Kategori seç" />
                </SelectTrigger>
                <SelectContent className="bg-white">
                  {categories.map((c) => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label className="text-xs font-semibold uppercase tracking-wider text-slate-600">Tutar ({form.currency})</Label>
              <Input type="number" step="0.01" value={form.amount}
                     onChange={(e) => setForm({ ...form, amount: e.target.value })}
                     required data-testid="tx-amount-input" className="mt-1 font-mono-num" />
            </div>
            <div>
              <Label className="text-xs font-semibold uppercase tracking-wider text-slate-600">Order ID</Label>
              <Input value={form.order_id} onChange={(e) => setForm({ ...form, order_id: e.target.value })}
                     data-testid="tx-order-input" className="mt-1" />
            </div>
            <div>
              <Label className="text-xs font-semibold uppercase tracking-wider text-slate-600">SKU</Label>
              <Input value={form.sku} onChange={(e) => setForm({ ...form, sku: e.target.value })}
                     data-testid="tx-sku-input" className="mt-1" />
            </div>
            <div className="md:col-span-2">
              <Label className="text-xs font-semibold uppercase tracking-wider text-slate-600">Açıklama</Label>
              <Textarea rows={1} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })}
                        data-testid="tx-description-input" className="mt-1" />
            </div>

            <div className="lg:col-span-4 flex justify-end">
              <Button type="submit" data-testid="tx-submit-button"
                      className={`rounded-xl text-white ${type === "income" ? "bg-emerald-600 hover:bg-emerald-700" : "bg-rose-600 hover:bg-rose-700"}`}>
                <Plus className="w-4 h-4 mr-1" /> {type === "income" ? "Gelir Ekle" : "Gider Ekle"}
              </Button>
            </div>
          </form>
        </TabsContent>
      </Tabs>

      <div className="bg-white border border-slate-200 rounded-2xl overflow-hidden">
        <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
          <h2 className="font-display text-lg font-bold text-slate-900">
            {type === "income" ? "Gelir Kayıtları" : "Gider Kayıtları"} ({rows.length})
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider">
              <tr>
                <th className="text-left px-6 py-3 font-semibold">Tarih</th>
                <th className="text-left px-4 py-3 font-semibold">Pazar</th>
                <th className="text-left px-4 py-3 font-semibold">Kategori</th>
                <th className="text-left px-4 py-3 font-semibold">Order / SKU</th>
                <th className="text-left px-4 py-3 font-semibold">Açıklama</th>
                <th className="text-right px-4 py-3 font-semibold">Tutar</th>
                <th className="text-right px-6 py-3 font-semibold">—</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100" data-testid="tx-table-body">
              {loading && (
                <tr><td colSpan={7} className="px-6 py-8 text-center text-slate-400">Yükleniyor...</td></tr>
              )}
              {!loading && rows.length === 0 && (
                <tr><td colSpan={7} className="px-6 py-8 text-center text-slate-400">Henüz kayıt yok</td></tr>
              )}
              {rows.map((r) => {
                const mp = MP_BY_CODE[r.marketplace];
                return (
                  <tr key={r.id} className="hover:bg-slate-50">
                    <td className="px-6 py-3 font-mono-num text-slate-700">{r.date}</td>
                    <td className="px-4 py-3">{mp?.flag} <span className="text-slate-600 font-medium">{r.marketplace}</span></td>
                    <td className="px-4 py-3">{r.category}</td>
                    <td className="px-4 py-3 text-xs text-slate-500">
                      {r.order_id || "—"} {r.sku && <span className="block">SKU: {r.sku}</span>}
                    </td>
                    <td className="px-4 py-3 text-slate-600 max-w-[260px] truncate">{r.description || "—"}</td>
                    <td className={`px-4 py-3 text-right font-mono-num font-bold ${type === "income" ? "text-emerald-600" : "text-rose-600"}`}>
                      {type === "income" ? "+" : "−"}{formatMoney(r.amount, r.currency)}
                    </td>
                    <td className="px-6 py-3 text-right">
                      <Button variant="ghost" size="icon" onClick={() => removeRow(r.id)}
                              data-testid={`delete-tx-${r.id}`}
                              className="text-slate-400 hover:text-rose-600 hover:bg-rose-50">
                        <Trash2 className="w-4 h-4" />
                      </Button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
