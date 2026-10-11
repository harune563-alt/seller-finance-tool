import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import KpiCard from "@/components/KpiCard";
import { formatUsd } from "@/components/FxStatus";
import { FbaFilters } from "@/components/fba/FbaFilters";
import { SelectField, TextField, FormError, apiError } from "@/components/company/Fields";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter,
} from "@/components/ui/dialog";
import {
  Wallet, TrendingUp, TrendingDown, DollarSign, Landmark, Boxes, Package, Receipt,
  ArrowDownToLine, ArrowUpFromLine, Pencil, Trash2, Store as StoreIcon,
} from "lucide-react";
import { toast } from "sonner";

const EMPTY_MANUAL = { date: new Date().toISOString().slice(0, 10), store_id: "", marketplace: "", category: "", amount_usd: "", description: "" };

export default function CashFlow() {
  const { stores } = useStore();
  const [filters, setFilters] = useState({ preset: "all", start: "", end: "", marketplace: "ALL" });
  const [storeScope, setStoreScope] = useState("ALL");
  const [summary, setSummary] = useState(null);
  const [entries, setEntries] = useState([]);
  const [monthly, setMonthly] = useState([]);
  const [balances, setBalances] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [manualOpen, setManualOpen] = useState(false);
  const [manualDirection, setManualDirection] = useState("IN");
  const [editingEntry, setEditingEntry] = useState(null);
  const [manualForm, setManualForm] = useState(EMPTY_MANUAL);
  const [manualError, setManualError] = useState("");

  const [obOpen, setObOpen] = useState(false);
  const [obForm, setObForm] = useState({ store_id: "", amount_usd: "", note: "" });
  const [obError, setObError] = useState("");

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
      const [s, e, m, b] = await Promise.all([
        api.get("/cashflow/summary", { params }),
        api.get("/cashflow/entries", { params }),
        api.get("/cashflow/monthly", { params }),
        api.get("/cashflow/opening-balances"),
      ]);
      setSummary(s.data); setEntries(e.data.rows || []); setMonthly(m.data.months || []);
      setBalances(b.data.balances || []);
    } catch {
      setError("Nakit akışı yüklenemedi. Lütfen tekrar deneyin.");
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { load(); }, [stores.length, storeScope, filters]);

  const openManual = (direction, entry = null) => {
    setManualDirection(direction);
    setEditingEntry(entry);
    setManualError("");
    setManualForm(entry
      ? { date: entry.date, store_id: entry.store_id, marketplace: entry.marketplace || "", category: entry.category, amount_usd: String(entry.direction === "IN" ? entry.cash_in : entry.cash_out), description: entry.description || "" }
      : { ...EMPTY_MANUAL, store_id: storeScope !== "ALL" ? storeScope : (stores[0]?.id || "") });
    setManualOpen(true);
  };

  const submitManual = async (e) => {
    e.preventDefault();
    setManualError("");
    const payload = { ...manualForm, amount_usd: Number(manualForm.amount_usd), direction: manualDirection };
    if (!payload.store_id) { setManualError("Mağaza seçin"); return; }
    if (!payload.category.trim()) { setManualError("Kategori gerekli"); return; }
    if (!(payload.amount_usd > 0)) { setManualError("Tutar 0'dan büyük olmalı"); return; }
    try {
      if (editingEntry) {
        const { store_id, ...update } = payload;
        await api.put(`/cashflow/manual/${editingEntry.id}`, update);
        toast.success("Manuel kayıt güncellendi");
      } else {
        await api.post("/cashflow/manual", payload);
        toast.success(manualDirection === "IN" ? "Nakit girişi eklendi" : "Nakit çıkışı eklendi");
      }
      setManualOpen(false);
      load();
    } catch (err) { setManualError(apiError(err)); }
  };

  const removeManual = async (entry) => {
    if (!window.confirm("Bu manuel nakit kaydı silinecek. Emin misin?")) return;
    try { await api.delete(`/cashflow/manual/${entry.id}`); toast.success("Manuel kayıt silindi"); load(); }
    catch (err) { toast.error(apiError(err)); }
  };

  const openOb = () => {
    setObError("");
    setObForm({ store_id: storeScope !== "ALL" ? storeScope : (stores[0]?.id || ""), amount_usd: "", note: "" });
    setObOpen(true);
  };

  const submitOb = async (e) => {
    e.preventDefault();
    setObError("");
    if (!obForm.store_id) { setObError("Mağaza seçin"); return; }
    if (obForm.amount_usd === "" || Number(obForm.amount_usd) < 0) { setObError("Geçerli bir tutar girin"); return; }
    try {
      await api.put("/cashflow/opening-balance", { store_id: obForm.store_id, amount_usd: Number(obForm.amount_usd), note: obForm.note });
      toast.success("Açılış bakiyesi güncellendi");
      setObOpen(false);
      load();
    } catch (err) { setObError(apiError(err)); }
  };

  if (!stores.length) {
    return (
      <div className="rounded-2xl bg-white border border-slate-200 p-12 text-center" data-testid="cashflow-empty">
        <div className="mx-auto w-14 h-14 rounded-2xl bg-emerald-50 flex items-center justify-center text-emerald-600 mb-4"><StoreIcon className="w-7 h-7" /></div>
        <h2 className="font-display text-2xl font-extrabold text-slate-900">Önce mağaza oluştur</h2>
        <p className="text-sm text-slate-500 mt-2 max-w-md mx-auto">Nakit akışını takip etmek için bir mağaza eklemen gerekir.</p>
        <Link to="/stores"><Button className="mt-6 bg-slate-900 hover:bg-slate-800 text-white rounded-xl">Mağaza Ekle</Button></Link>
      </div>
    );
  }

  const s = summary || {};
  const manualStore = stores.find(x => x.id === manualForm.store_id);
  const obCurrent = balances.find(b => b.store_id === obForm.store_id);

  return (
    <div className="space-y-6" data-testid="cashflow-page">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="font-display text-3xl font-extrabold text-slate-900 tracking-tight">Nakit Akışı</h1>
          <p className="text-sm text-slate-500 mt-1" data-testid="cashflow-scope-label">
            Gerçek nakit hareketi — Kar/Zarar özetinden ayrıdır{loading && " · Yükleniyor…"}
          </p>
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button variant="outline" className="rounded-xl bg-white" onClick={openOb} data-testid="opening-balance-btn">
            <Landmark className="w-4 h-4 mr-2" /> Açılış Bakiyesi
          </Button>
          <Button variant="outline" className="rounded-xl bg-white text-emerald-700" onClick={() => openManual("IN")} data-testid="manual-cash-in-btn">
            <ArrowDownToLine className="w-4 h-4 mr-2" /> Manuel Nakit Girişi
          </Button>
          <Button variant="outline" className="rounded-xl bg-white text-rose-700" onClick={() => openManual("OUT")} data-testid="manual-cash-out-btn">
            <ArrowUpFromLine className="w-4 h-4 mr-2" /> Manuel Nakit Çıkışı
          </Button>
        </div>
      </div>

      <FbaFilters value={filters} onChange={setFilters} marketplaces={marketplaces} allTime>
        <div className="w-56">
          <SelectField label="Mağaza / Şirket" id="cashflow-store-filter" value={storeScope} onChange={setStoreScope}
            options={[{ value: "ALL", label: "Tüm Mağazalar" }, ...stores.map(x => ({ value: x.id, label: x.name }))]} />
        </div>
      </FbaFilters>
      {error && <p role="alert" data-testid="cashflow-error" className="text-sm text-rose-600">{error}</p>}

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4" data-testid="cashflow-summary-cards">
        <KpiCard testId="cf-opening" label="Açılış Nakit" accent="slate" icon={Landmark} value={formatUsd(s.opening_cash)} hint="Dönem başı bakiye" />
        <KpiCard testId="cf-in" label="Toplam Nakit Girişi" accent="emerald" icon={TrendingUp} value={formatUsd(s.cash_in)} hint="Amazon + manuel girişler" />
        <KpiCard testId="cf-out" label="Toplam Nakit Çıkışı" accent="rose" icon={TrendingDown} value={formatUsd(s.cash_out)} hint="Envanter, FBM maliyetleri, ekstra, manuel" />
        <KpiCard testId="cf-net" label="Net Nakit Akışı" accent="indigo" icon={DollarSign} value={formatUsd(s.net_cash_flow)} hint="Giriş − Çıkış" />
        <KpiCard testId="cf-closing" label="Kapanış Nakit" accent="amber" icon={Wallet} value={formatUsd(s.closing_cash)} hint="Açılış + Net Akış" />
        <KpiCard testId="cf-inv-purchases" label="Envanter Alımları" accent="rose" icon={Package} value={formatUsd(s.inventory_purchases)} hint="Dönem içi FBA lot maliyeti (ürün + inbound)" />
        <KpiCard testId="cf-capital-tied" label="FBA Envanterindeki Sermaye" accent="amazon" icon={Boxes} value={formatUsd(s.capital_tied_in_inventory)} hint="Kalan stok değeri — varlıktır, tekrar gider değildir" />
        <KpiCard testId="cf-realized" label="Gerçekleşen Envanter Maliyeti" accent="slate" icon={Receipt} value={formatUsd(s.realized_inventory_cost)} hint="Satılan birimlerin FIFO maliyeti — yalnızca K/Z'yi etkiler" />
      </div>

      {/* Entries table */}
      <div className="rounded-2xl bg-white border border-slate-200 overflow-hidden" data-testid="cashflow-table-card">
        <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
          <h2 className="font-display text-lg font-bold text-slate-900">Nakit Hareketleri</h2>
          <span className="text-xs text-slate-400" data-testid="cashflow-entry-count">{entries.length} kayıt</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[1000px]">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-slate-500 border-b border-slate-100">
                <th className="px-5 py-3">Tarih</th><th className="px-3 py-3">Mağaza</th><th className="px-3 py-3">Yön</th>
                <th className="px-3 py-3">Kategori</th><th className="px-3 py-3">Açıklama</th><th className="px-3 py-3">Kaynak</th>
                <th className="px-3 py-3">Sipariş / Lot</th><th className="px-3 py-3 text-right">Nakit Giriş</th>
                <th className="px-3 py-3 text-right">Nakit Çıkış</th><th className="px-5 py-3 text-right">Kalan Bakiye</th><th className="px-3 py-3"></th>
              </tr>
            </thead>
            <tbody>
              {entries.length === 0 && (
                <tr><td colSpan={11} className="px-5 py-8 text-center text-slate-400" data-testid="cashflow-empty-rows">Bu filtrelerle nakit hareketi yok</td></tr>
              )}
              {entries.map((r) => (
                <tr key={r.id} className="border-b border-slate-50 hover:bg-slate-50/60" data-testid={`cf-row-${r.id}`}>
                  <td className="px-5 py-2.5 font-mono-num text-slate-700 whitespace-nowrap">{r.date}</td>
                  <td className="px-3 py-2.5 text-slate-600">{r.store_name}</td>
                  <td className="px-3 py-2.5">
                    <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-semibold ${r.direction === "IN" ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"}`} data-testid={`cf-dir-${r.id}`}>
                      {r.direction === "IN" ? "Giriş" : "Çıkış"}
                    </span>
                  </td>
                  <td className="px-3 py-2.5 text-slate-700">{r.category}</td>
                  <td className="px-3 py-2.5 text-slate-500 max-w-[220px] truncate" title={r.description}>{r.description || "—"}</td>
                  <td className="px-3 py-2.5 text-slate-500 text-xs">{r.source_label}</td>
                  <td className="px-3 py-2.5 font-mono-num text-xs text-slate-500">{r.order_id || (r.lot_id ? `Lot ${r.lot_id.slice(0, 8)}` : "—")}</td>
                  <td className="px-3 py-2.5 text-right font-mono-num text-emerald-700">{r.cash_in != null ? formatUsd(r.cash_in) : ""}</td>
                  <td className="px-3 py-2.5 text-right font-mono-num text-rose-700">{r.cash_out != null ? formatUsd(r.cash_out) : ""}</td>
                  <td className="px-5 py-2.5 text-right font-mono-num font-semibold text-slate-900" data-testid={`cf-balance-${r.id}`}>{formatUsd(r.running_balance)}</td>
                  <td className="px-3 py-2.5 text-right whitespace-nowrap">
                    {r.is_manual && (
                      <>
                        <button className="text-slate-400 hover:text-slate-700 mr-2" onClick={() => openManual(r.direction, r)} data-testid={`cf-edit-${r.id}`}><Pencil className="w-4 h-4" /></button>
                        <button className="text-slate-400 hover:text-rose-600" onClick={() => removeManual(r)} data-testid={`cf-delete-${r.id}`}><Trash2 className="w-4 h-4" /></button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Monthly report */}
      <div className="rounded-2xl bg-white border border-slate-200 overflow-hidden" data-testid="cashflow-monthly-card">
        <div className="px-5 py-4 border-b border-slate-100">
          <h2 className="font-display text-lg font-bold text-slate-900">Aylık Nakit Akışı Raporu</h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm min-w-[1200px]">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wider text-slate-500 border-b border-slate-100">
                <th className="px-5 py-3">Ay</th><th className="px-3 py-3 text-right">Başlangıç</th>
                <th className="px-3 py-3 text-right">Amazon Giriş</th><th className="px-3 py-3 text-right">Diğer Giriş</th>
                <th className="px-3 py-3 text-right">Envanter Alımı</th><th className="px-3 py-3 text-right">FBA Inbound</th>
                <th className="px-3 py-3 text-right">FBM Ürün</th><th className="px-3 py-3 text-right">FBM Kargo</th>
                <th className="px-3 py-3 text-right">Ekstra</th><th className="px-3 py-3 text-right">Diğer Çıkış</th>
                <th className="px-3 py-3 text-right">Net Akış</th><th className="px-5 py-3 text-right">Kapanış</th>
              </tr>
            </thead>
            <tbody>
              {monthly.length === 0 && (
                <tr><td colSpan={12} className="px-5 py-8 text-center text-slate-400" data-testid="cashflow-empty-monthly">Aylık veri yok</td></tr>
              )}
              {monthly.map((m) => (
                <tr key={m.month} className="border-b border-slate-50 hover:bg-slate-50/60" data-testid={`cf-month-${m.month}`}>
                  <td className="px-5 py-2.5 font-semibold text-slate-800">{m.month}</td>
                  <td className="px-3 py-2.5 text-right font-mono-num text-slate-600">{formatUsd(m.beginning_cash)}</td>
                  <td className="px-3 py-2.5 text-right font-mono-num text-emerald-700">{formatUsd(m.amazon_cash_in)}</td>
                  <td className="px-3 py-2.5 text-right font-mono-num text-emerald-700">{formatUsd(m.other_cash_in)}</td>
                  <td className="px-3 py-2.5 text-right font-mono-num text-rose-700">{formatUsd(m.inventory_purchases)}</td>
                  <td className="px-3 py-2.5 text-right font-mono-num text-rose-700">{formatUsd(m.fba_inbound_shipping)}</td>
                  <td className="px-3 py-2.5 text-right font-mono-num text-rose-700">{formatUsd(m.fbm_product_costs)}</td>
                  <td className="px-3 py-2.5 text-right font-mono-num text-rose-700">{formatUsd(m.fbm_shipping_costs)}</td>
                  <td className="px-3 py-2.5 text-right font-mono-num text-rose-700">{formatUsd(m.extra_costs)}</td>
                  <td className="px-3 py-2.5 text-right font-mono-num text-rose-700">{formatUsd(m.other_cash_out)}</td>
                  <td className={`px-3 py-2.5 text-right font-mono-num font-semibold ${m.net_cash_flow >= 0 ? "text-emerald-700" : "text-rose-700"}`}>{formatUsd(m.net_cash_flow)}</td>
                  <td className="px-5 py-2.5 text-right font-mono-num font-semibold text-slate-900">{formatUsd(m.ending_cash)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Manual entry dialog */}
      <Dialog open={manualOpen} onOpenChange={setManualOpen}>
        <DialogContent className="bg-white max-w-lg" data-testid="cashflow-manual-dialog">
          <DialogHeader>
            <DialogTitle>{editingEntry ? "Manuel Kayıt Düzenle" : manualDirection === "IN" ? "Manuel Nakit Girişi" : "Manuel Nakit Çıkışı"}</DialogTitle>
            <DialogDescription>Bu kayıt yalnızca nakit akışını etkiler; Kar/Zarar hesabına dokunmaz.</DialogDescription>
          </DialogHeader>
          <form onSubmit={submitManual} className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <TextField label="Tarih" id="cf-manual-date" type="date" value={manualForm.date} onChange={v => setManualForm({ ...manualForm, date: v })} required />
              <TextField label="Tutar (USD)" id="cf-manual-amount" type="number" step="0.01" min="0.01" value={manualForm.amount_usd} onChange={v => setManualForm({ ...manualForm, amount_usd: v })} required />
            </div>
            {!editingEntry && (
              <SelectField label="Mağaza" id="cf-manual-store" value={manualForm.store_id} onChange={v => setManualForm({ ...manualForm, store_id: v, marketplace: "" })}
                options={stores.map(x => ({ value: x.id, label: x.name }))} />
            )}
            <SelectField label="Pazar Yeri (opsiyonel)" id="cf-manual-marketplace" value={manualForm.marketplace} onChange={v => setManualForm({ ...manualForm, marketplace: v === "NONE" ? "" : v })}
              options={[{ value: "NONE", label: "—" }, ...(manualStore?.marketplaces || []).map(c => ({ value: c, label: c }))]} />
            <TextField label="Kategori" id="cf-manual-category" value={manualForm.category} onChange={v => setManualForm({ ...manualForm, category: v })} placeholder="örn. Kargo ödemesi, Ortak çıkışı" required />
            <TextField label="Açıklama" id="cf-manual-description" value={manualForm.description} onChange={v => setManualForm({ ...manualForm, description: v })} placeholder="Opsiyonel" />
            <FormError error={manualError} id="cf-manual-error" />
            <DialogFooter>
              <Button type="submit" className={`rounded-xl text-white ${manualDirection === "IN" ? "bg-emerald-600 hover:bg-emerald-700" : "bg-rose-600 hover:bg-rose-700"}`} data-testid="cf-manual-submit">
                {editingEntry ? "Güncelle" : manualDirection === "IN" ? "Giriş Ekle" : "Çıkış Ekle"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* Opening balance dialog */}
      <Dialog open={obOpen} onOpenChange={setObOpen}>
        <DialogContent className="bg-white max-w-lg" data-testid="cashflow-opening-dialog">
          <DialogHeader>
            <DialogTitle>Açılış Bakiyesi</DialogTitle>
            <DialogDescription>Mağaza başına başlangıç nakdi. Her değişiklik denetim kaydına işlenir.</DialogDescription>
          </DialogHeader>
          <form onSubmit={submitOb} className="space-y-4">
            <SelectField label="Mağaza" id="cf-ob-store" value={obForm.store_id} onChange={v => setObForm({ ...obForm, store_id: v })}
              options={stores.map(x => ({ value: x.id, label: x.name }))} />
            {obCurrent && (
              <p className="text-xs text-slate-500" data-testid="cf-ob-current">
                Mevcut: <span className="font-mono-num font-semibold">{formatUsd(obCurrent.amount_usd)}</span>
                {obCurrent.history?.length > 0 && ` · ${obCurrent.history.length} değişiklik kaydı`}
              </p>
            )}
            <TextField label="Yeni Açılış Bakiyesi (USD)" id="cf-ob-amount" type="number" step="0.01" min="0" value={obForm.amount_usd} onChange={v => setObForm({ ...obForm, amount_usd: v })} required />
            <TextField label="Not" id="cf-ob-note" value={obForm.note} onChange={v => setObForm({ ...obForm, note: v })} placeholder="Opsiyonel açıklama" />
            <FormError error={obError} id="cf-ob-error" />
            <DialogFooter>
              <Button type="submit" className="bg-slate-900 hover:bg-slate-800 text-white rounded-xl" data-testid="cf-ob-submit">Kaydet</Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
      <Label className="hidden">cashflow</Label>
    </div>
  );
}
