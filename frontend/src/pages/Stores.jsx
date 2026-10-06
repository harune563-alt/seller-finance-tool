import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { MARKETPLACES, MP_BY_CODE } from "@/constants/marketplaces";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogTrigger, DialogFooter,
} from "@/components/ui/dialog";
import { Plus, Trash2, Pencil, Store as StoreIcon } from "lucide-react";
import { toast } from "sonner";

const CURRENCIES = ["USD", "CAD", "MXN", "GBP", "EUR", "AUD", "JPY", "AED", "SAR", "TRY", "SEK", "PLN"];

export default function Stores() {
  const { stores, refresh, setActiveStoreId } = useStore();
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [form, setForm] = useState({ name: "", marketplaces: ["US"], default_currency: "USD" });

  useEffect(() => { refresh(); }, [refresh]);

  const openCreate = () => {
    setEditing(null);
    setForm({ name: "", marketplaces: ["US"], default_currency: "USD" });
    setOpen(true);
  };

  const openEdit = (s) => {
    setEditing(s);
    setForm({ name: s.name, marketplaces: s.marketplaces || [], default_currency: s.default_currency });
    setOpen(true);
  };

  const toggleMp = (code) => {
    setForm((f) => ({
      ...f,
      marketplaces: f.marketplaces.includes(code)
        ? f.marketplaces.filter((c) => c !== code)
        : [...f.marketplaces, code],
    }));
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!form.name.trim()) { toast.error("Mağaza adı gerekli"); return; }
    if (form.marketplaces.length === 0) { toast.error("En az bir pazar yeri seçin"); return; }
    try {
      if (editing) {
        await api.put(`/stores/${editing.id}`, form);
        toast.success("Mağaza güncellendi");
      } else {
        const { data } = await api.post("/stores", form);
        toast.success("Mağaza oluşturuldu");
        setActiveStoreId(data.id);
      }
      setOpen(false);
      refresh();
    } catch {
      toast.error("Kayıt başarısız");
    }
  };

  const remove = async (s) => {
    if (!window.confirm(`"${s.name}" mağazası ve tüm işlemleri silinecek. Emin misin?`)) return;
    await api.delete(`/stores/${s.id}`);
    toast.success("Mağaza silindi");
    refresh();
  };

  const toggleSelected = id => setSelectedIds(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  const removeSelected = async () => {
    if (!selectedIds.size || !window.confirm(`${selectedIds.size} mağaza ve bağlı işlemler kalıcı olarak silinecek. Emin misin?`)) return;
    try { await api.post("/stores/bulk-delete", { ids: [...selectedIds] }); toast.success(`${selectedIds.size} mağaza silindi`); setSelectedIds(new Set()); refresh(); }
    catch (err) { toast.error(err.response?.data?.detail || "Mağazalar silinemedi"); }
  };

  return (
    <div className="space-y-6" data-testid="stores-page">
      <div className="flex items-end justify-between flex-wrap gap-3">
        <div>
          <h1 className="font-display text-3xl font-extrabold text-slate-900">Mağaza & Pazar Yeri Yönetimi</h1>
          <p className="text-sm text-slate-500 mt-1">Her Amazon satıcı hesabın için ayrı mağaza oluştur ve içindeki ülke pazarlarını seç.</p>
        </div>
        <Dialog open={open} onOpenChange={setOpen}>
          <DialogTrigger asChild>
            <Button onClick={openCreate} data-testid="new-store-button"
                    className="bg-slate-900 hover:bg-slate-800 text-white rounded-xl">
              <Plus className="w-4 h-4 mr-1" /> Yeni Mağaza
            </Button>
          </DialogTrigger>
          <DialogContent className="bg-white max-w-2xl" data-testid="store-dialog">
            <DialogHeader>
              <DialogTitle>{editing ? "Mağaza Düzenle" : "Yeni Mağaza"}</DialogTitle>
              <DialogDescription>Mağaza ve aktif pazar yerleri</DialogDescription>
            </DialogHeader>
            <form onSubmit={submit} className="space-y-4">
              <div>
                <Label className="text-xs font-semibold uppercase tracking-wider text-slate-600">Mağaza Adı</Label>
                <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                       required data-testid="store-name-input" placeholder="örn. Alfa Global EU" className="mt-1" />
              </div>
              <div>
                <Label className="text-xs font-semibold uppercase tracking-wider text-slate-600">Varsayılan Para Birimi</Label>
                <Select value={form.default_currency} onValueChange={(v) => setForm({ ...form, default_currency: v })}>
                  <SelectTrigger className="mt-1" data-testid="store-currency-select"><SelectValue /></SelectTrigger>
                  <SelectContent className="bg-white" data-testid="store-currency-options">
                    {CURRENCIES.map((c) => <SelectItem key={c} value={c} data-testid={`store-currency-${c.toLowerCase()}`}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs font-semibold uppercase tracking-wider text-slate-600 mb-2 block">
                  Aktif Pazar Yerleri ({form.marketplaces.length})
                </Label>
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2 max-h-72 overflow-y-auto">
                  {MARKETPLACES.map((m) => {
                    const checked = form.marketplaces.includes(m.code);
                    return (
                      <label key={m.code} data-testid={`mp-check-${m.code}`}
                             className={`flex items-center gap-2 px-3 py-2 rounded-xl border cursor-pointer transition-colors ${
                               checked ? "bg-emerald-50 border-emerald-300" : "bg-white border-slate-200 hover:border-slate-300"
                             }`}>
                        <Checkbox checked={checked} onCheckedChange={() => toggleMp(m.code)} data-testid={`store-marketplace-checkbox-${m.code.toLowerCase()}`} />
                        <span className="text-lg">{m.flag}</span>
                        <span className="text-xs font-semibold text-slate-700 flex-1 truncate">{m.code}</span>
                        <span className="text-[10px] text-slate-500">{m.currency}</span>
                      </label>
                    );
                  })}
                </div>
              </div>
              <DialogFooter>
                <Button type="submit" data-testid="store-submit-button"
                        className="bg-slate-900 hover:bg-slate-800 text-white">
                  {editing ? "Güncelle" : "Oluştur"}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {selectedIds.size > 0 && <div className="flex justify-end"><Button variant="destructive" onClick={removeSelected} data-testid="bulk-delete-stores">Seçilen mağazaları sil ({selectedIds.size})</Button></div>}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {stores.length === 0 && (
          <div className="col-span-full bg-white border border-dashed border-slate-300 rounded-2xl p-10 text-center">
            <StoreIcon className="w-10 h-10 text-slate-300 mx-auto mb-3" />
            <p className="text-slate-500 text-sm">Henüz mağaza eklenmemiş.</p>
          </div>
        )}
        {stores.map((s) => (
          <div key={s.id} className="bg-white border border-slate-200 rounded-2xl p-5 flex flex-col"
               data-testid={`store-card-${s.id}`}>
            <div className="flex items-start justify-between gap-2">
              <Checkbox checked={selectedIds.has(s.id)} onCheckedChange={() => toggleSelected(s.id)} aria-label={`${s.name} mağazasını seç`} data-testid={`select-store-${s.id}`} />
              <div className="flex items-center gap-2 flex-1 min-w-0">
                <div className="w-10 h-10 rounded-xl bg-slate-900 flex items-center justify-center"><StoreIcon className="w-5 h-5 text-amber-400" /></div>
                <div className="min-w-0"><div className="font-display font-bold text-slate-900 truncate">{s.name}</div><div className="text-xs text-slate-500">Varsayılan: {s.default_currency}</div></div>
              </div>
              <div className="flex gap-1">
                <Button variant="ghost" size="icon" onClick={() => openEdit(s)} data-testid={`edit-store-${s.id}`} className="text-slate-500 hover:text-slate-900"><Pencil className="w-4 h-4" /></Button>
                <Button variant="ghost" size="icon" onClick={() => remove(s)} data-testid={`delete-store-${s.id}`} className="text-slate-400 hover:text-rose-600 hover:bg-rose-50"><Trash2 className="w-4 h-4" /></Button>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-1.5">
              {s.marketplaces.map((c) => {
                const m = MP_BY_CODE[c];
                return (
                  <span key={c} className="inline-flex items-center gap-1 text-xs font-semibold bg-slate-100 text-slate-700 px-2 py-1 rounded-full">
                    {m?.flag} {c}
                  </span>
                );
              })}
            </div>
            <Button variant="outline" className="mt-4 rounded-xl bg-white" onClick={() => setActiveStoreId(s.id)}
                    data-testid={`activate-store-${s.id}`}>
              Bu mağazayı seç
            </Button>
          </div>
        ))}
      </div>
    </div>
  );
}
