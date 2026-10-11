import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import KpiCard from "@/components/KpiCard";
import { formatUsd } from "@/components/FxStatus";
import { FbaFilters } from "@/components/fba/FbaFilters";
import { SelectField, TextField, FormError, apiError } from "@/components/company/Fields";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import { Megaphone, TrendingUp, DollarSign, Target, Plus, Trash2, Store as StoreIcon } from "lucide-react";
import { toast } from "sonner";

const pct = v => v == null ? "—" : `${Number(v).toFixed(1)}%`;
const roasFmt = v => v == null ? "—" : `${Number(v).toFixed(2)}x`;

const STATUS_STYLES = {
  reconciled: "bg-emerald-50 text-emerald-700",
  pending_match: "bg-amber-50 text-amber-700",
  manual_ppc: "bg-indigo-50 text-indigo-700",
  unmatched: "bg-slate-100 text-slate-600",
};

const EMPTY = { date: new Date().toISOString().slice(0, 10), marketplace: "", campaign: "", asin: "", sku: "", ad_spend_usd: "", ppc_sales_usd: "", clicks: "", impressions: "", orders: "" };

export default function PpcAttribution() {
  const { stores } = useStore();
  const [filters, setFilters] = useState({ preset: "all", start: "", end: "", marketplace: "ALL" });
  const [storeScope, setStoreScope] = useState("ALL");
  const [data, setData] = useState(null);
  const [recon, setRecon] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState(EMPTY);
  const [formError, setFormError] = useState("");

  const marketplaces = useMemo(
    () => [...new Set(stores.filter(s => storeScope === "ALL" || s.id === storeScope).flatMap(s => s.marketplaces))],
    [stores, storeScope]);

  const load = async () => {
    if (!stores.length) return;
    const params = {
      ...(storeScope !== "ALL" && { store_id: storeScope }),
      ...(filters.marketplace !== "ALL" && { marketplace: filters.marketplace }),
      ...(filters.start && { start_date: filters.start }),
      ...(filters.end && { end_date: filters.end }),
    };
    setLoading(true); setError("");
    try {
      const [a, r] = await Promise.all([
        api.get("/ppc/attributions", { params }),
        api.get("/ppc/reconciliation", { params: { ...(storeScope !== "ALL" && { store_id: storeScope }), ...(filters.marketplace !== "ALL" && { marketplace: filters.marketplace }) } }),
      ]);
      setData(a.data); setRecon(r.data.rows || []);
    } catch { setError("PPC verileri yüklenemedi."); }
    finally { setLoading(false); }
  };
  useEffect(() => { load(); }, [stores.length, storeScope, filters]);

  const openCreate = () => {
    setFormError("");
    setForm({ ...EMPTY, marketplace: marketplaces[0] || "" });
    setOpen(true);
  };

  const submit = async (e) => {
    e.preventDefault();
    setFormError("");
    if (storeScope === "ALL") { setFormError("Önce tek bir mağaza seçin"); return; }
    if (!form.asin.trim() && !form.campaign.trim()) { setFormError("ASIN veya kampanya gerekli"); return; }
    if (!(Number(form.ad_spend_usd) >= 0)) { setFormError("Geçerli reklam harcaması girin"); return; }
    try {
      await api.post("/ppc/attributions", {
        store_id: storeScope, marketplace: form.marketplace, date: form.date,
        campaign: form.campaign, asin: form.asin, sku: form.sku,
        ad_spend_usd: Number(form.ad_spend_usd), ppc_sales_usd: Number(form.ppc_sales_usd) || 0,
        clicks: Number(form.clicks) || 0, impressions: Number(form.impressions) || 0, orders: Number(form.orders) || 0,
      });
      toast.success("PPC dağıtımı kaydedildi (finansal gider oluşturulmaz)");
      setOpen(false); load();
    } catch (err) { setFormError(apiError(err)); }
  };

  const remove = async (row) => {
    if (!window.confirm("Bu PPC dağıtım kaydı silinecek. Emin misin?")) return;
    try { await api.delete(`/ppc/attributions/${row.id}`); toast.success("PPC kaydı silindi"); load(); }
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

  const s = data?.summary || {};
  const rows = data?.rows || [];

  return (
    <div className="space-y-6" data-testid="ppc-page">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-extrabold text-slate-900 tracking-tight">PPC Reklam Attribution</h1>
          <p className="text-sm text-slate-500 mt-1" data-testid="ppc-subtitle">
            Finansal kaynak Amazon Payments hesabıdır; PPC yalnızca harcamayı ASIN/kampanyaya dağıtır — ikinci kez gider yazılmaz{loading && " · Yükleniyor…"}
          </p>
        </div>
        <Button onClick={openCreate} className="bg-pink-600 hover:bg-pink-700 text-white rounded-xl" data-testid="ppc-add-btn">
          <Plus className="w-4 h-4 mr-2" /> Manuel PPC Dağıtımı
        </Button>
      </div>

      <FbaFilters value={filters} onChange={setFilters} marketplaces={marketplaces} allTime>
        <div className="w-56">
          <SelectField label="Mağaza / Şirket" id="ppc-store-filter" value={storeScope} onChange={setStoreScope}
            options={[{ value: "ALL", label: "Tüm Mağazalar" }, ...stores.map(x => ({ value: x.id, label: x.name }))]} />
        </div>
      </FbaFilters>
      {error && <p role="alert" data-testid="ppc-error" className="text-sm text-rose-600">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4" data-testid="ppc-summary-cards">
        <KpiCard testId="ppc-financial" label="Finansal Reklam Gideri" accent="rose" icon={DollarSign} value={formatUsd(s.financial_ad_expense_usd)} hint="Amazon Payments'taki gerçek gider (tek kayıt)" />
        <KpiCard testId="ppc-attributed" label="Dağıtılan PPC Harcaması" accent="amber" icon={Megaphone} value={formatUsd(s.attributed_ad_spend_usd)} hint="ASIN/kampanyaya dağıtım — ekstra gider değil" />
        <KpiCard testId="ppc-sales" label="PPC Satışları" accent="emerald" icon={TrendingUp} value={formatUsd(s.attributed_ppc_sales_usd)} hint="Attributed satış" />
        <KpiCard testId="ppc-acos" label="ACoS / ROAS" accent="indigo" icon={Target} value={`${pct(s.acos_percent)} · ${roasFmt(s.roas)}`} hint="Harcama/Satış · Satış/Harcama" />
      </div>

      {/* Attribution table */}
      <div className="rounded-2xl bg-white border border-slate-200 overflow-hidden" data-testid="ppc-table-card">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <h2 className="font-display text-lg font-bold text-slate-900">PPC Dağıtım Kayıtları</h2>
          <span className="text-xs text-slate-400">{rows.length} kayıt</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[1100px]">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-slate-500 border-b border-slate-100">
                <th className="px-5 py-3">Tarih</th><th className="px-3 py-3">Pazar</th><th className="px-3 py-3">Kampanya</th>
                <th className="px-3 py-3">ASIN</th><th className="px-3 py-3">SKU</th>
                <th className="px-3 py-3 text-right">Reklam Harcaması</th><th className="px-3 py-3 text-right">PPC Satış</th>
                <th className="px-3 py-3 text-right">ACoS</th><th className="px-3 py-3 text-right">ROAS</th>
                <th className="px-3 py-3">Durum</th><th className="px-3 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {rows.length === 0 && <tr><td colSpan={11} className="px-5 py-8 text-center text-slate-400" data-testid="ppc-empty-rows">Bu filtrelerle PPC kaydı yok</td></tr>}
              {rows.map(r => (
                <tr key={r.id} className="border-b border-slate-50 hover:bg-slate-50/60" data-testid={`ppc-row-${r.id}`}>
                  <td className="px-5 py-2.5 font-mono-num text-slate-700 whitespace-nowrap">{r.date}</td>
                  <td className="px-3 py-2.5 text-slate-600">{r.marketplace || "—"}</td>
                  <td className="px-3 py-2.5 text-slate-700 max-w-[160px] truncate" title={r.campaign}>{r.campaign || "—"}</td>
                  <td className="px-3 py-2.5 font-mono text-xs">{r.asin || "—"}</td>
                  <td className="px-3 py-2.5 font-mono text-xs">{r.sku || "—"}</td>
                  <td className="px-3 py-2.5 text-right font-mono-num text-rose-700">{formatUsd(r.ad_spend_usd)}</td>
                  <td className="px-3 py-2.5 text-right font-mono-num text-emerald-700">{formatUsd(r.ppc_sales_usd)}</td>
                  <td className="px-3 py-2.5 text-right font-mono-num">{pct(r.acos_percent)}</td>
                  <td className="px-3 py-2.5 text-right font-mono-num">{roasFmt(r.roas)}</td>
                  <td className="px-3 py-2.5">
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-semibold ${STATUS_STYLES[r.reconciliation_status] || "bg-slate-100 text-slate-600"}`} data-testid={`ppc-status-${r.id}`}>
                      {r.reconciliation_label}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-right">
                    <button className="text-slate-400 hover:text-rose-600" onClick={() => remove(r)} data-testid={`ppc-delete-${r.id}`}><Trash2 className="w-4 h-4" /></button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Reconciliation by month */}
      <div className="rounded-2xl bg-white border border-slate-200 overflow-hidden" data-testid="ppc-recon-card">
        <div className="px-5 py-4 border-b border-slate-100">
          <h2 className="font-display text-lg font-bold text-slate-900">Amazon Payments Mutabakatı (Aylık)</h2>
          <p className="text-xs text-slate-500 mt-1">Finansal reklam gideri ile dağıtılan PPC harcamasının karşılaştırması. Fark, henüz dağıtılmamış harcamayı gösterir.</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[700px]">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-slate-500 border-b border-slate-100">
                <th className="px-5 py-3">Pazar</th><th className="px-3 py-3">Ay</th>
                <th className="px-3 py-3 text-right">Finansal Gider</th><th className="px-3 py-3 text-right">Dağıtılan</th>
                <th className="px-3 py-3 text-right">Dağıtılmayan</th><th className="px-3 py-3">Durum</th>
              </tr>
            </thead>
            <tbody>
              {recon.length === 0 && <tr><td colSpan={6} className="px-5 py-8 text-center text-slate-400" data-testid="ppc-recon-empty">Mutabakat verisi yok</td></tr>}
              {recon.map((r, i) => (
                <tr key={`${r.marketplace}-${r.month}`} className="border-b border-slate-50" data-testid={`ppc-recon-${i}`}>
                  <td className="px-5 py-2.5 text-slate-600">{r.marketplace || "—"}</td>
                  <td className="px-3 py-2.5 font-semibold text-slate-800">{r.month}</td>
                  <td className="px-3 py-2.5 text-right font-mono-num text-rose-700">{formatUsd(r.financial_ad_expense_usd)}</td>
                  <td className="px-3 py-2.5 text-right font-mono-num text-amber-700">{formatUsd(r.attributed_ad_spend_usd)}</td>
                  <td className="px-3 py-2.5 text-right font-mono-num text-slate-600">{formatUsd(r.unattributed_usd)}</td>
                  <td className="px-3 py-2.5 text-xs text-slate-500">{r.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Manual PPC dialog */}
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="bg-white max-w-lg" data-testid="ppc-dialog">
          <DialogHeader>
            <DialogTitle>Manuel PPC Dağıtımı</DialogTitle>
            <DialogDescription>Bu kayıt yalnızca ASIN/kampanya dağıtımıdır; finansal gider Amazon Payments hesabında kalır, ikinci kez yazılmaz.</DialogDescription>
          </DialogHeader>
          <form onSubmit={submit} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <TextField label="Tarih" id="ppc-f-date" type="date" value={form.date} onChange={v => setForm({ ...form, date: v })} required />
              <SelectField label="Pazar Yeri" id="ppc-f-marketplace" value={form.marketplace} onChange={v => setForm({ ...form, marketplace: v })}
                options={marketplaces.map(c => ({ value: c, label: c }))} />
            </div>
            <TextField label="Kampanya" id="ppc-f-campaign" value={form.campaign} onChange={v => setForm({ ...form, campaign: v })} placeholder="Kampanya adı" />
            <div className="grid grid-cols-2 gap-3">
              <TextField label="ASIN" id="ppc-f-asin" value={form.asin} onChange={v => setForm({ ...form, asin: v })} placeholder="örn. B0..." />
              <TextField label="SKU (opsiyonel)" id="ppc-f-sku" value={form.sku} onChange={v => setForm({ ...form, sku: v })} />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <TextField label="Reklam Harcaması (USD)" id="ppc-f-spend" type="number" step="0.01" min="0" value={form.ad_spend_usd} onChange={v => setForm({ ...form, ad_spend_usd: v })} required />
              <TextField label="PPC Satışı (USD)" id="ppc-f-sales" type="number" step="0.01" min="0" value={form.ppc_sales_usd} onChange={v => setForm({ ...form, ppc_sales_usd: v })} />
            </div>
            <div className="grid grid-cols-3 gap-3">
              <TextField label="Tıklama" id="ppc-f-clicks" type="number" min="0" value={form.clicks} onChange={v => setForm({ ...form, clicks: v })} />
              <TextField label="Gösterim" id="ppc-f-impressions" type="number" min="0" value={form.impressions} onChange={v => setForm({ ...form, impressions: v })} />
              <TextField label="Sipariş" id="ppc-f-orders" type="number" min="0" value={form.orders} onChange={v => setForm({ ...form, orders: v })} />
            </div>
            <FormError error={formError} id="ppc-f-error" />
            <DialogFooter>
              <Button type="submit" className="bg-pink-600 hover:bg-pink-700 text-white rounded-xl" data-testid="ppc-f-submit">Kaydet</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  );
}
