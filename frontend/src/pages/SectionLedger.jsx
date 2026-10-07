import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import { Pencil, Plus, Trash2 } from "lucide-react";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { useCategories } from "@/hooks/useCategories";
import { useFormMarketplace } from "@/hooks/useFormMarketplace";
import { useFxQuote } from "@/hooks/useFxQuote";
import { FxStatus, formatUsd } from "@/components/FxStatus";
import { PpcForm } from "@/components/transactions/PpcForm";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { MP_BY_CODE } from "@/constants/marketplaces";

const Metric = ({ label, value, hint, tone = "default" }) => (
  <div className="border border-slate-200 bg-white rounded-xl px-4 py-4">
    <p className="text-xs text-slate-500">{label}</p>
    <p className={`font-display text-2xl font-bold ${tone === "profit" ? "text-emerald-700" : tone === "loss" ? "text-rose-600" : "text-slate-900"}`}>{value}</p>
    {hint && <p className="text-xs text-slate-400 mt-1">{hint}</p>}
  </div>
);

const useSectionRecords = (storeId, section, revision) => {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!storeId) { setRows([]); return; }
    let active = true;
    setLoading(true);
    api.get("/transactions", { params: { store_id: storeId, section, limit: 500 } })
      .then(({ data }) => { if (active) setRows(data); })
      .catch(() => { if (active) setRows([]); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [storeId, section, revision]);
  return { rows, loading };
};

const GenericForm = ({ section, onSaved }) => {
  const { activeStore, activeStoreId } = useStore();
  const { byType } = useCategories(activeStoreId);
  const options = byType(undefined, section);
  const { marketplace, currency, selectMarketplace } = useFormMarketplace();
  const [form, setForm] = useState({
    date: new Date().toISOString().slice(0, 10),
    category: "", amount: "", description: "", order_id: "",
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const fx = useFxQuote(currency, form.date);
  const activeCat = options.find((c) => c.name === form.category) || options[0];

  const change = (k, v) => { setForm((f) => ({ ...f, [k]: v })); setError(""); };
  const submit = async (e) => {
    e.preventDefault(); setError("");
    if (!activeStoreId || !activeStore?.marketplaces?.includes(marketplace)) { setError("Mağaza ve pazar seçin."); return; }
    if (!fx.quote) { setError("Kurun alınması gerekiyor."); return; }
    if (!activeCat) { setError("Önce bir kategori seçin."); return; }
    if (!Number.isFinite(Number(form.amount)) || Number(form.amount) <= 0) { setError("Tutar 0'dan büyük olmalı."); return; }
    setSaving(true);
    try {
      await api.post("/transactions", {
        store_id: activeStoreId, marketplace, currency,
        type: activeCat.type, category: activeCat.name, section,
        amount: Number(form.amount), date: form.date,
        description: form.description, order_id: form.order_id.trim(),
      });
      toast.success("Kayıt eklendi");
      setForm({ ...form, amount: "", description: "", order_id: "" });
      onSaved?.();
    } catch (err) { setError(err?.response?.data?.detail || "Kayıt başarısız"); }
    finally { setSaving(false); }
  };
  const amountUsd = fx.quote ? Math.round(Number(form.amount || 0) * Number(fx.quote.rate) * 100) / 100 : null;

  return (
    <form onSubmit={submit} noValidate className="border-y border-slate-200 bg-white px-4 sm:px-6 py-6 space-y-6" data-testid={`${section}-form`}>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div>
          <Label htmlFor={`${section}-date`}>Tarih</Label>
          <Input id={`${section}-date`} type="date" value={form.date} onChange={(e) => change("date", e.target.value)} data-testid={`${section}-date-input`} className="mt-2" />
        </div>
        <div>
          <Label htmlFor={`${section}-mp`}>Pazar Yeri</Label>
          <Select value={marketplace} onValueChange={selectMarketplace}>
            <SelectTrigger id={`${section}-mp`} data-testid={`${section}-marketplace-select`} className="mt-2"><SelectValue placeholder="Pazar" /></SelectTrigger>
            <SelectContent>
              {(activeStore?.marketplaces || []).map((c) => <SelectItem key={c} value={c}>{MP_BY_CODE[c]?.flag} {MP_BY_CODE[c]?.name}</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor={`${section}-cat`}>Kategori</Label>
          <Select value={form.category} onValueChange={(v) => change("category", v)}>
            <SelectTrigger id={`${section}-cat`} data-testid={`${section}-category-select`} className="mt-2"><SelectValue placeholder="Kategori" /></SelectTrigger>
            <SelectContent>
              {options.map((c) => <SelectItem key={c.id} value={c.name}>{c.name} ({c.type === "income" ? "Gelir" : "Gider"})</SelectItem>)}
            </SelectContent>
          </Select>
        </div>
        <div>
          <Label htmlFor={`${section}-amount`}>Tutar ({currency || "—"})</Label>
          <Input id={`${section}-amount`} type="number" step="0.01" min="0.01" value={form.amount} onChange={(e) => change("amount", e.target.value)} data-testid={`${section}-amount-input`} className="mt-2 font-mono-num" placeholder="0.00" />
          <p className="text-xs text-slate-500 mt-1">USD karşılığı: {formatUsd(amountUsd)}</p>
        </div>
        <div className="sm:col-span-2">
          <Label htmlFor={`${section}-desc`}>Açıklama</Label>
          <Input id={`${section}-desc`} value={form.description} onChange={(e) => change("description", e.target.value)} data-testid={`${section}-desc-input`} className="mt-2" />
        </div>
        <div className="sm:col-span-2">
          <Label htmlFor={`${section}-order`}>Order ID (opsiyonel)</Label>
          <Input id={`${section}-order`} value={form.order_id} onChange={(e) => change("order_id", e.target.value)} data-testid={`${section}-order-input`} className="mt-2" />
        </div>
      </div>
      <FxStatus quote={fx.quote} loading={fx.loading} error={fx.error} retry={fx.retry} />
      {error && <p role="alert" className="text-sm text-rose-700 bg-rose-50 p-3 rounded-md" data-testid={`${section}-form-error`}>{error}</p>}
      <div className="flex justify-end">
        <Button type="submit" disabled={saving || !activeStoreId || !fx.quote || options.length === 0} data-testid={`${section}-submit`} className="bg-emerald-600 hover:bg-emerald-700 text-white">
          <Plus className="w-4 h-4 mr-2" /> {saving ? "Kaydediliyor…" : "Kaydet"}
        </Button>
      </div>
    </form>
  );
};

const RowItem = ({ row, section, onDelete }) => (
  <tr className="border-b border-slate-100 hover:bg-slate-50" data-testid={`${section}-row-${row.id}`}>
    <td className="py-2 px-3 text-sm text-slate-700">{row.date}</td>
    <td className="py-2 px-3 text-sm text-slate-700">{row.marketplace}</td>
    <td className="py-2 px-3 text-sm font-medium text-slate-900">{row.category}</td>
    {section === "ppc" && (
      <>
        <td className="py-2 px-3 text-xs text-slate-600" data-testid={`${section}-campaign-${row.id}`}>{row.campaign_name || "—"}</td>
        <td className="py-2 px-3 text-xs text-slate-600">{row.ad_type || "—"}</td>
        <td className="py-2 px-3 text-xs text-slate-600 font-mono-num">{row.asin_sku || "—"}</td>
        <td className="py-2 px-3 text-right text-xs font-mono-num text-slate-600">{row.clicks ?? 0}</td>
        <td className="py-2 px-3 text-right text-xs font-mono-num text-slate-600">{row.impressions ?? 0}</td>
        <td className="py-2 px-3 text-right text-xs font-mono-num text-slate-600">{row.orders_count ?? 0}</td>
      </>
    )}
    <td className="py-2 px-3 text-right font-mono-num">{Number(row.amount).toFixed(2)} {row.currency}</td>
    <td className="py-2 px-3 text-right font-mono-num text-slate-500 text-xs">{row.amount_usd != null ? formatUsd(row.amount_usd) : "—"}</td>
    <td className="py-2 px-3 text-right">
      <Button variant="ghost" size="sm" className="text-rose-600" onClick={() => onDelete(row.id)} data-testid={`${section}-delete-${row.id}`}><Trash2 className="w-4 h-4" /></Button>
    </td>
  </tr>
);

export default function SectionLedger({ section, title, subtitle }) {
  const { activeStore, activeStoreId } = useStore();
  const [revision, setRevision] = useState(0);
  const refresh = () => setRevision((v) => v + 1);
  const { rows, loading } = useSectionRecords(activeStoreId, section, revision);
  const [deleting, setDeleting] = useState(null);

  const totals = useMemo(() => {
    let revenueUsd = 0, expenseUsd = 0, clicks = 0, impressions = 0, orders = 0;
    for (const r of rows) {
      const amt = r.amount_usd || 0;
      if (r.type === "income") revenueUsd += amt;
      else if (r.type === "expense") expenseUsd += amt;
      clicks += r.clicks || 0; impressions += r.impressions || 0; orders += r.orders_count || 0;
    }
    return { revenueUsd, expenseUsd, netUsd: revenueUsd - expenseUsd, clicks, impressions, orders };
  }, [rows]);

  const remove = async () => {
    if (!deleting) return;
    try { await api.delete(`/transactions/${deleting}`); toast.success("İşlem silindi"); setDeleting(null); refresh(); }
    catch { toast.error("Silinemedi"); }
  };

  return (
    <div className="space-y-6" data-testid={`${section}-page`}>
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <h1 className="font-display text-3xl sm:text-4xl font-extrabold">{title}</h1>
          <p className="mt-2 text-sm text-slate-500">{activeStore?.name || "Mağaza seçilmedi"} · {subtitle}</p>
        </div>
      </div>
      {!activeStoreId ? (
        <Link to="/stores" className="text-emerald-700 underline">Mağaza oluştur</Link>
      ) : (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3" data-testid={`${section}-kpis`}>
            <Metric label="Gelir (USD)" value={formatUsd(totals.revenueUsd)} tone="profit" />
            <Metric label="Gider (USD)" value={formatUsd(totals.expenseUsd)} tone="loss" />
            <Metric label="Net (USD)" value={formatUsd(totals.netUsd)} tone={totals.netUsd >= 0 ? "profit" : "loss"} />
            {section === "ppc" ? (
              <Metric label="CTR / ACoS" value={totals.impressions > 0 ? `${((totals.clicks / totals.impressions) * 100).toFixed(2)}% / ${totals.revenueUsd > 0 ? ((totals.expenseUsd / totals.revenueUsd) * 100).toFixed(1) + "%" : "—"}`: "—"} hint={`${totals.clicks} tıklama · ${totals.impressions} gösterim · ${totals.orders} sipariş`} />
            ) : (
              <Metric label="Kayıt Sayısı" value={rows.length} />
            )}
          </div>
          {section === "ppc" ? <PpcForm onSaved={refresh} /> : <GenericForm section={section} onSaved={refresh} />}
          <div className="border border-slate-200 rounded-xl bg-white overflow-x-auto">
            <table className="w-full text-sm" data-testid={`${section}-table`}>
              <thead className="bg-slate-50 text-xs uppercase text-slate-500">
                <tr>
                  <th className="py-2 px-3 text-left">Tarih</th>
                  <th className="py-2 px-3 text-left">Pazar</th>
                  <th className="py-2 px-3 text-left">Kategori</th>
                  {section === "ppc" && (
                    <>
                      <th className="py-2 px-3 text-left">Kampanya</th>
                      <th className="py-2 px-3 text-left">Reklam Tipi</th>
                      <th className="py-2 px-3 text-left">ASIN/SKU</th>
                      <th className="py-2 px-3 text-right">Tıklama</th>
                      <th className="py-2 px-3 text-right">Gösterim</th>
                      <th className="py-2 px-3 text-right">Sipariş</th>
                    </>
                  )}
                  <th className="py-2 px-3 text-right">Tutar</th>
                  <th className="py-2 px-3 text-right">USD</th>
                  <th className="py-2 px-3"></th>
                </tr>
              </thead>
              <tbody>
                {loading && <tr><td colSpan={section === "ppc" ? 12 : 6} className="text-center text-slate-500 py-4">Yükleniyor…</td></tr>}
                {!loading && rows.length === 0 && <tr><td colSpan={section === "ppc" ? 12 : 6} className="text-center text-slate-500 py-4" data-testid={`${section}-empty`}>Henüz kayıt yok</td></tr>}
                {rows.map((r) => <RowItem key={r.id} row={r} section={section} onDelete={setDeleting} />)}
              </tbody>
            </table>
          </div>
        </>
      )}
      <Dialog open={!!deleting} onOpenChange={(v) => !v && setDeleting(null)}>
        <DialogContent className="bg-white" data-testid={`${section}-delete-dialog`}>
          <DialogHeader><DialogTitle>Kayıt silinsin mi?</DialogTitle><DialogDescription>Seçili {section.toUpperCase()} kaydı kalıcı olarak kaldırılacak.</DialogDescription></DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleting(null)} data-testid={`${section}-delete-cancel`}>Vazgeç</Button>
            <Button variant="destructive" onClick={remove} data-testid={`${section}-delete-confirm`}>Sil</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
