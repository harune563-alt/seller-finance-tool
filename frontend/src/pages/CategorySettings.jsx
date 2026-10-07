import { useState } from "react";
import { toast } from "sonner";
import { Archive, ArchiveRestore, Pencil, Plus, Trash2 } from "lucide-react";
import api from "@/lib/api";
import { useStore } from "@/contexts/StoreContext";
import { useCategories } from "@/hooks/useCategories";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";

const SECTIONS = [
  { value: "general", label: "Genel (Gelir/Gider)" },
  { value: "fba", label: "FBA" },
  { value: "ppc", label: "PPC Reklam" },
];
const TYPES = [
  { value: "income", label: "Gelir" },
  { value: "expense", label: "Gider" },
];

const blankForm = () => ({ name: "", type: "expense", section: "general", color: "#64748b", icon: "tag" });

const CategoryDialog = ({ open, onClose, onSaved, storeId, editing }) => {
  const [form, setForm] = useState(() => editing ? { ...editing } : blankForm());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (!form.name.trim()) { setError("İsim zorunlu"); return; }
    setSaving(true);
    try {
      if (editing) {
        await api.put(`/categories/${editing.id}`, { name: form.name, type: form.type, section: form.section, color: form.color, icon: form.icon });
      } else {
        await api.post("/categories", { ...form, store_id: storeId });
      }
      toast.success(editing ? "Kategori güncellendi" : "Kategori eklendi");
      onSaved();
    } catch (err) {
      setError(err?.response?.data?.detail || "Kaydedilemedi");
    } finally { setSaving(false); }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="bg-white" data-testid="category-dialog">
        <form onSubmit={submit}>
          <DialogHeader>
            <DialogTitle>{editing ? "Kategoriyi Düzenle" : "Yeni Kategori"}</DialogTitle>
            <DialogDescription>İsim, tür ve bölüm seçin. Renk/ikon görsel ipucudur.</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 py-4">
            <div className="sm:col-span-2">
              <Label htmlFor="cat-name">İsim</Label>
              <Input id="cat-name" data-testid="category-name-input" className="mt-2" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div>
              <Label>Tür</Label>
              <Select value={form.type} onValueChange={(v) => setForm({ ...form, type: v })}>
                <SelectTrigger className="mt-2" data-testid="category-type-select"><SelectValue /></SelectTrigger>
                <SelectContent>{TYPES.map((t) => <SelectItem key={t.value} value={t.value}>{t.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label>Bölüm</Label>
              <Select value={form.section} onValueChange={(v) => setForm({ ...form, section: v })}>
                <SelectTrigger className="mt-2" data-testid="category-section-select"><SelectValue /></SelectTrigger>
                <SelectContent>{SECTIONS.map((s) => <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>)}</SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="cat-color">Renk</Label>
              <Input id="cat-color" type="color" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })} className="mt-2 h-10" />
            </div>
            <div>
              <Label htmlFor="cat-icon">İkon anahtarı (opsiyonel)</Label>
              <Input id="cat-icon" value={form.icon} onChange={(e) => setForm({ ...form, icon: e.target.value })} className="mt-2" />
            </div>
          </div>
          {error && <p role="alert" className="text-sm text-rose-700 bg-rose-50 p-2 rounded" data-testid="category-error">{error}</p>}
          <DialogFooter className="mt-4">
            <Button type="button" variant="outline" onClick={onClose} data-testid="category-cancel">Vazgeç</Button>
            <Button type="submit" disabled={saving} className="bg-emerald-600 hover:bg-emerald-700 text-white" data-testid="category-save">
              {saving ? "Kaydediliyor…" : editing ? "Güncelle" : "Ekle"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
};

const CategoryRow = ({ cat, onEdit, onArchive, onDelete }) => (
  <div className="flex items-center gap-3 border border-slate-200 rounded-lg px-4 py-3 bg-white" data-testid={`category-row-${cat.id}`}>
    <span className="inline-block w-3 h-3 rounded-full" style={{ background: cat.color }} />
    <div className="flex-1 min-w-0">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="font-medium text-slate-900 truncate" data-testid={`category-name-${cat.id}`}>{cat.name}</span>
        {cat.is_system && <Badge variant="outline" className="text-[10px]">Sistem</Badge>}
        {cat.archived && <Badge variant="secondary" className="text-[10px]">Arşiv</Badge>}
      </div>
      <div className="text-xs text-slate-500 mt-1">
        {cat.type === "income" ? "Gelir" : "Gider"} · {SECTIONS.find((s) => s.value === cat.section)?.label}
      </div>
    </div>
    <Button variant="ghost" size="sm" onClick={() => onEdit(cat)} data-testid={`category-edit-${cat.id}`}><Pencil className="w-4 h-4" /></Button>
    <Button variant="ghost" size="sm" onClick={() => onArchive(cat)} data-testid={`category-archive-${cat.id}`}>
      {cat.archived ? <ArchiveRestore className="w-4 h-4" /> : <Archive className="w-4 h-4" />}
    </Button>
    <Button variant="ghost" size="sm" onClick={() => onDelete(cat)} className="text-rose-600" data-testid={`category-delete-${cat.id}`}><Trash2 className="w-4 h-4" /></Button>
  </div>
);

export default function CategorySettings() {
  const { activeStore, activeStoreId } = useStore();
  const { categories, loading, error, refresh } = useCategories(activeStoreId);
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editing, setEditing] = useState(null);
  const [deleting, setDeleting] = useState(null);

  const openCreate = () => { setEditing(null); setDialogOpen(true); };
  const openEdit = (c) => { setEditing(c); setDialogOpen(true); };
  const close = () => { setDialogOpen(false); setEditing(null); };
  const toggleArchive = async (c) => {
    try { await api.put(`/categories/${c.id}`, { archived: !c.archived }); toast.success(c.archived ? "Kategori geri alındı" : "Kategori arşivlendi"); refresh(); }
    catch (err) { toast.error(err?.response?.data?.detail || "İşlem başarısız"); }
  };
  const confirmDelete = async () => {
    if (!deleting) return;
    try { await api.delete(`/categories/${deleting.id}`); toast.success("Kategori silindi"); refresh(); setDeleting(null); }
    catch (err) { toast.error(err?.response?.data?.detail || "Silinemedi"); }
  };

  const grouped = SECTIONS.map((s) => ({ ...s, items: categories.filter((c) => c.section === s.value) }));

  return (
    <div className="space-y-6" data-testid="categories-page">
      <div className="flex items-end justify-between flex-wrap gap-4">
        <div>
          <h1 className="font-display text-3xl sm:text-4xl font-extrabold">Gelir / Gider Türleri</h1>
          <p className="mt-2 text-sm text-slate-500">
            {activeStore?.name || "Mağaza seçilmedi"} · Mağaza bazında özel kategoriler
          </p>
        </div>
        <Button onClick={openCreate} disabled={!activeStoreId} data-testid="category-add-btn" className="bg-emerald-600 hover:bg-emerald-700 text-white">
          <Plus className="w-4 h-4 mr-2" /> Yeni Kategori
        </Button>
      </div>
      {!activeStoreId && <p className="text-sm text-slate-500">Önce bir mağaza seçin.</p>}
      {error && <p role="alert" className="text-sm text-rose-700 bg-rose-50 p-3 rounded" data-testid="categories-error">{error}</p>}
      {loading && <p className="text-sm text-slate-500">Yükleniyor…</p>}
      {!loading && activeStoreId && grouped.map((group) => (
        <section key={group.value} data-testid={`category-section-${group.value}`} className="space-y-3">
          <h2 className="font-display font-semibold text-lg text-slate-900">{group.label}</h2>
          {group.items.length === 0 ? (
            <p className="text-xs text-slate-500">Bu bölümde henüz kategori yok.</p>
          ) : (
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
              {group.items.map((cat) => (
                <CategoryRow key={cat.id} cat={cat} onEdit={openEdit} onArchive={toggleArchive} onDelete={setDeleting} />
              ))}
            </div>
          )}
        </section>
      ))}

      {dialogOpen && (
        <CategoryDialog
          open={dialogOpen}
          onClose={close}
          onSaved={() => { close(); refresh(); }}
          storeId={activeStoreId}
          editing={editing}
        />
      )}
      <Dialog open={!!deleting} onOpenChange={(v) => !v && setDeleting(null)}>
        <DialogContent className="bg-white" data-testid="category-delete-dialog">
          <DialogHeader>
            <DialogTitle>Kategori silinsin mi?</DialogTitle>
            <DialogDescription>
              "{deleting?.name}" kategorisi kalıcı olarak kaldırılacak. Kategori kullanımda ise silme engellenir; önce arşivleyin.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleting(null)} data-testid="category-delete-cancel">Vazgeç</Button>
            <Button variant="destructive" onClick={confirmDelete} data-testid="category-delete-confirm">Sil</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
